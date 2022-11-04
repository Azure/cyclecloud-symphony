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

remote_file "/etc/#{node['symphony']['license_file']}" do 
  source "file://#{node['jetpack']['downloads']}/#{node['symphony']['license_file']}"
  owner 'root'
  group 'root'
  mode 0644
end
  

# Get the current Master and Management node list
mgmt_hosts = []
if node['symphony']['master_host'].nil?
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
  master_host = master_node['cyclecloud']['instance']['hostname']
  mgmt_hosts = mgmt_nodes.map { |n|
    n['cyclecloud']['instance']['hostname']
  }
  mgmt_hosts = mgmt_hosts.sort {|a,b| a[1] <=> b[1]}
  Chef::Log.info("Found master: #{master_host} and Management Nodes: #{mgmt_hosts}.")
  
else

  master_host = node['symphony']['master_host']
  mgmt_hosts = node['symphony']['management_hosts']
  if !mgmt_hosts.kind_of?(Array)
    mgmt_hosts = mgmt_hosts.split(",")
  end
  mgmt_hosts = mgmt_hosts.sort {|a,b| a[1] <=> b[1]}
  Chef::Log.info("Using configured master: #{master_host} and Management Nodes: #{mgmt_hosts}.")
  
end

mgmt_hosts_shortnames = mgmt_hosts.map { |fqdn|
  fqdn.split(".", 2)[0]
}

Chef::Log.info("Management Node short names: #{mgmt_hosts_shortnames}  ( #{mgmt_hosts} )")

# TODO: Do we need to be able to configure a separate DB Host?
derby_db_node=master_host
  
file '/etc/symphony_mgmt_hosts' do
  content mgmt_hosts.join('\n')
  mode '0644'
  owner 'root'
  group 'root'
end
  
file '/etc/symphony_master_node' do
  content master_host
  mode '0644'
  owner 'root'
  group 'root'
end


# Install dependencies
%w{ net-tools which gettext }.each do |pkg|
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
* soft nproc 65536
* hard nproc 65536
* soft nofile 65536
* soft nofile 65536
root soft nproc unlimited
root hard nproc unlimited
root soft nofile unlimited
root soft nofile unlimited
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

  . /etc/profile.d/jdk.sh

  export MASTER_ADDRESS=#{master_host}
  export CLUSTERADMIN=#{node['symphony']['admin']['user']}
  export CLUSTERNAME=#{node['cyclecloud']['cluster']['name']}
  export SIMPLIFIEDWEM=#{node['symphony']['simplifiedwem']}
  export BASEPORT=#{node['symphony']['baseport']}
  export DISABLESSL=#{node['symphony']['disablessl'] ? 'Y' : 'N'}
  export SHARED_FS_INSTALL=#{node['symphony']['shared_fs_install'] ? 'Y' : 'N'}

  # Use the default derby db
  export DERBY_DB_HOST=#{derby_db_node}

  # Accept license terms for silent install
  export IBM_SPECTRUM_SYMPHONY_LICENSE_ACCEPT=Y

  export EGO_TOP=#{node['symphony']['ego_top']}
  . $EGO_TOP/profile.platform

  EOH
  owner 'root'
  group 'root'
  mode 0755
end

# Base install dir should generally be /opt/ibm and may already be a mounted share
ego_top_basedir = File.dirname(node['symphony']['ego_top'])
directory ego_top_basedir do
  owner "root"
  group "root"
  mode "0755"
  recursive true
  not_if { ::File.exist?(ego_top_basedir) }
end



# EGO conf for Mgmt and Exec nodes is different, so place on local drive
template "/etc/ego.conf" do
  source "ego.conf.erb"
  group "egoadmin"
  owner "egoadmin"

  # master_list should be a comma-separated string here
  variables(:master_list => master_host)  
end



# If performing a shared install, install only on master and to a shared directory  
# Perform the actual install (either locally on all instances OR to shared drive on Master ONLY)
if node['symphony']['shared_fs_install'] == false or node['symphony']['is_master'] == true

  jetpack_download "symphony/#{node['symphony']['pkg']['linux']}" do
    project "symphony"
    not_if { ::File.exists?("#{node['jetpack']['downloads']}/#{node['symphony']['pkg']['linux']}") or
             ::File.exists?("#{node['symphony']['ego_confdir']}/profile.ego") }
    
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

  bash "Ensure EGO MASTER list (#{master_host})..." do
    code "sed -i '/^EGO_MASTER_LIST=/c\EGO_MASTER_LIST=#{master_host}' #{node['symphony']['ego_confdir']}/ego.conf"
  end

  template "#{node['symphony']['ego_confdir']}/ego.cluster.#{node['cyclecloud']['cluster']['name']}" do  
    source "ego.cluster.erb"
    group "egoadmin"
    owner "egoadmin"

    # master_list should be an array here
    variables(:mgmt_list => mgmt_hosts_shortnames)  
  end

  template "#{node['symphony']['ego_confdir']}/ResourceGroups.xml" do  
    source "ResourceGroups.xml.erb"
    group "egoadmin"
    owner "egoadmin"

    # master_list should be an array here
    variables(:mgmt_list => mgmt_hosts_shortnames)  
  end

end

bash "Link ego.conf to local drive" do
  code <<-EOH
  set -x
  set -e
  rm -f #{node['symphony']['ego_confdir']}/ego.conf
  ln -sf /etc/ego.conf #{node['symphony']['ego_confdir']}/ego.conf
  chown egoadmin:egoadmin #{node['symphony']['ego_confdir']}/ego.conf
  EOH
  not_if "test -h #{node['symphony']['ego_confdir']}/ego.conf"
end


