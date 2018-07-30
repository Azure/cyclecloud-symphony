#
# Cookbook Name:: symphony
# Recipe:: default
#
# see: https://www.ibm.com/support/knowledgecenter/SSZUMP_7.2.0/install/install_linux.html
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

include_recipe "jdk::default"

# This is not really overridable yet
# https://www.ibm.com/support/knowledgecenter/SSZUMP_7.1.2/shared_files/envars_ego.html
# If using shared install, then EGO_CONFDIR="#{node['symphony']['shared_dir']}/kernel/conf"
node.default['symphony']['ego_top'] = '/opt/ibm/spectrumcomputing'
node.default['symphony']['ego_confdir'] = "#{node['symphony']['ego_top']}/kernel/conf"

# TODO: For some reason shared installs fail
node.default['symphony']['shared_fs_install'] = false

# To set slot count set EGO_DEFINE_NCPUS


jetpack_download "symphony/#{node['symphony']['license_file']}" do
  project "symphony"
end

remote_file '/etc/sym_adv_ev_entitlement.dat' do 
  source "file://#{node['jetpack']['downloads']}/#{node['symphony']['license_file']}"
  owner 'root'
  group 'root'
  mode 0644
end
  

# Get the current Master and Management node list
mgmt_nodes = []
master_nodes = Symphony::Helpers.wait_for_master(30) do
  mgmt_nodes = cluster.search(:clusterUID => node['cyclecloud']['cluster']['id']).select { |n|
    if not n['symphony'].nil?
      Chef::Log.info("#{n['cyclecloud']['instance']['ipv4']} mgmt: #{n['symphony']['is_management'] == true}  master: #{n['symphony']['is_master'] == true}")
    end
    if not n['symphony'].nil? and n['symphony']['is_management'] == true
      mgmt_nodes << n
    end
    # Return the master node
    if not n['symphony'].nil? and n['symphony']['is_master'] == true
      n
    end
  }
end

master_node = master_nodes[0]
mgmt_nodes = mgmt_nodes.sort {|a,b| a[1] <=> b[1]}
Chef::Log.info("Found master: #{master_node['cyclecloud']['instance']['ipv4']} and #{mgmt_nodes.length} Management Nodes.")

mgmt_hosts = mgmt_nodes.map { |n|
  n['cyclecloud']['instance']['hostname']
}

# TODO: Do we need to be able to configure a separate DB Host?
derby_db_node=master_node
  
file '/etc/symphony_mgmt_nodes' do
  content mgmt_hosts.join('\n')
  mode '0644'
  owner 'root'
  group 'root'
end



file '/etc/symphony_master_node' do
  content master_node['cyclecloud']['instance']['hostname']
  mode '0644'
  owner 'root'
  group 'root'
end


# Install dependencies
%w{ net-tools which }.each do |pkg|
  package pkg
end
if node['platform_family'] == "debian"
  %w{ lib32z1, rpm }.each do |pkg|
    package pkg
  end
end

# Configure egoadmin

# If user already exists, usermod returns exit code 12 if the new homedir exists.
# Setting manage_home to false runs usermod without the "-m" flag and usermod exits cleanly

manageHome = true
ruby_block "set #{node['symphony']['admin']['user']} manageHome param" do
  block do
    manageHome = false
  end
  only_if "getent passwd #{node['symphony']['admin']['user']}"
end

group node['symphony']['admin']['user'] do
  gid node['symphony']['admin']['gid'].to_i
  not_if "grep #{node['symphony']['admin']['user']} /etc/group --quiet"
end

  log "Create user #{node['symphony']['admin']['user']} with uid: #{node['symphony']['admin']['uid']} and gid #{node['symphony']['admin']['gid']}"


user node['symphony']['admin']['user'] do
  uid node['symphony']['admin']['uid'].to_i
  gid node['symphony']['admin']['user']
  home node['symphony']['admin']['home']
  shell '/bin/bash'
  manage_home manageHome
end

directory node['symphony']['admin']['home'] do
    if not node['os'] == "windows"
      owner node['symphony']['admin']['user']
      group node['symphony']['admin']['user']
      mode "0755"
    end
    recursive true
end

directory "#{node['symphony']['admin']['home']}/.ssh" do
  owner node['symphony']['admin']['user']
  group node['symphony']['admin']['user']
  mode "0700"
  recursive true
end 

directory "/etc/security/limits.d" do
  recursive true
end

file "/etc/security/limits.d/#{node['symphony']['admin']['user']}.conf" do
  content <<-EOH
  #{node['symphony']['admin']['user']} soft nproc 65536
  #{node['symphony']['admin']['user']} hard nproc 65536
  #{node['symphony']['admin']['user']} soft nofile 65536
  #{node['symphony']['admin']['user']} soft nofile 65536
  EOH
end

bash "generate keypair for #{node['symphony']['admin']['user']}" do
  code <<-EOH
  ssh-keygen -f #{node['symphony']['admin']['home']}/.ssh/id_rsa -N ""
  chmod 600 #{node['symphony']['admin']['home']}/.ssh/id_rsa
  chown #{node['symphony']['admin']['user']}:#{node['symphony']['admin']['user']} #{node['symphony']['admin']['home']}/.ssh/id_rsa
  chown #{node['symphony']['admin']['user']}:#{node['symphony']['admin']['user']} #{node['symphony']['admin']['home']}/.ssh/id_rsa.pub
  cat #{node['symphony']['admin']['home']}/.ssh/id_rsa.pub >> #{node['symphony']['admin']['home']}/.ssh/authorized_keys
  chmod 0644 #{node['symphony']['admin']['home']}/.ssh/authorized_keys
  chown #{node['symphony']['admin']['user']}:#{node['symphony']['admin']['user']} #{node['symphony']['admin']['home']}/.ssh/authorized_keys
  EOH
  creates "#{node['symphony']['admin']['home']}/.ssh/id_rsa"
end

file "/etc/profile.d/symphony.sh" do
  content <<-EOH
  #!/bin/bash

  . /etc/profile.d/java.sh

  export MASTER_ADDRESS=#{master_node['cyclecloud']['instance']['hostname']}
  export CLUSTERADMIN=#{node['symphony']['admin']['user']}
  export CLUSTERNAME=#{node['cyclecloud']['cluster']['name']}
  export SIMPLIFIEDWEM=#{node['symphony']['simplifiedwem']}
  export BASEPORT=#{node['symphony']['baseport']}
  export DISABLESSL=#{node['symphony']['disablessl'] ? 'Y' : 'N'}
  export SHARED_FS_INSTALL=#{node['symphony']['shared_fs_install'] ? 'Y' : 'N'}

  # Use the default derby db
  export DERBY_DB_HOST=#{derby_db_node['cyclecloud']['instance']['hostname']}


  export EGO_TOP=#{node['symphony']['ego_top']}
  . $EGO_TOP/profile.platform

  EOH
  owner 'root'
  group 'root'
  mode 0755
end

ego_top_basedir = File.dirname(node['symphony']['ego_top'])
directory ego_top_basedir do
  owner "root"
  group "root"
  mode "0755"
  recursive true
end


# If performing a shared install, install only on master and to a shared directory
if node['symphony']['shared_fs_install'] == true
  ego_shared_dir=File.join(node['symphony']['shared_fs_mountpoint'], File.basename(node['symphony']['ego_top']))
  directory ego_shared_dir do
    owner node['symphony']['admin']['user']
    group node['symphony']['admin']['user']
    mode "0755"
    recursive true
    only_if { node['symphony']['is_master'] == true }
  end
  
  link node['symphony']['ego_top'] do
    to ego_shared_dir
  end

end  

  
# Perform the actual install (either locally on all instances OR to shared drive on Master ONLY)
if node['symphony']['shared_fs_install'] == false or node['symphony']['is_master'] == true


  jetpack_download "symphony/#{node['symphony']['pkg']['linux']}" do
    project "symphony"
  end


  bash "installing Symphony using: #{node['symphony']['pkg']['linux']}" do
    code <<-EOH
    set -x
    . /etc/profile.d/symphony.sh
    set -e

    chmod a+x #{node['jetpack']['downloads']}/#{node['symphony']['pkg']['linux']}
    #{node['jetpack']['downloads']}/#{node['symphony']['pkg']['linux']} --quiet
    EOH
    creates "#{node['symphony']['ego_confdir']}/profile.ego"
  end


  ruby_block "force EGO binary type for unrecognized linux variants" do
    block do
      file = Chef::Util::FileEdit.new("#{node['symphony']['ego_confdir']}/profile.ego")
      file.insert_line_after_match('/.*"Cannot get binary type.*/', '     export EGO_BINARY_TYPE="linux-x86_64"')
      file.insert_line_after_match('/export EGO_BINARY_TYPE="linux-x86_64"/', '     echo "Forcing EGO binary type: $EGO_BINARY_TYPE"')    
      file.write_file
    end
    not_if "grep -q 'Forcing EGO binary type' #{node['symphony']['ego_confdir']}/profile.ego"
  end

  bash "use ssh for ego communication" do
    code <<-EOH

    echo >> #{node['symphony']['ego_confdir']}/ego.conf
    echo 'EGO_RSH="ssh -oPasswordAuthentication=no -oStrictHostKeyChecking=no"' >> #{node['symphony']['ego_confdir']}/ego.conf

    EOH
    not_if "grep -q 'EGO_RSH=\"ssh -oPasswordAuthentication=no -oStrictHostKeyChecking=no\"' #{node['symphony']['ego_confdir']}/ego.conf"
  end

  # EGO conf for Mgmt and Exec nodes is different (mgmt nodes don't seem to accept the `EGO_GET_CONF=LIM` setting needed by execs)
  if node['symphony']['shared_fs_install'] == true
    ruby_block "Split ego.conf for management and exec nodes" do
      block do
        ::FileUtils.cp("#{node['symphony']['ego_confdir']}/ego.conf", "#{node['symphony']['ego_confdir']}/ego.exec.conf")
        ::FileUtils.mv("#{node['symphony']['ego_confdir']}/ego.conf", "#{node['symphony']['ego_confdir']}/ego.mgmt.conf")
        if node['symphony']['is_management'].nil? or node['symphony']['is_management'] != true
          ::FileUtils.ln_sf("#{node['symphony']['ego_confdir']}/ego.exec.conf", "#{node['symphony']['ego_confdir']}/ego.conf")
        else
          ::FileUtils.ln_sf("#{node['symphony']['ego_confdir']}/ego.mgmt.conf", "#{node['symphony']['ego_confdir']}/ego.conf")
        end        
      end
      not_if { ::File.exist?("#{node['symphony']['ego_confdir']}/ego.mgmt.conf") }
    end
  end

end

