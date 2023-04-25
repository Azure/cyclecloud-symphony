# coding: utf-8
#
# Cookbook Name:: symphony
# Recipe:: hostfactory
#
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

# NOTE : In Symphony 7.2 and earlier:
# $ tree -L 3 /opt/ibm/spectrumcomputing/eservice/hostfactory/
# /opt/ibm/spectrumcomputing/eservice/hostfactory/
# ├── conf
# │   ├── hostfactoryconf.json
# │   ├── hostfactoryconf.json.nonssl
# │   ├── hostfactoryconf.json.ssl
# │   ├── providers
# │   │   ├── aws
# │   │   ├── azure
# │   │   ├── hostProviders.json
# │   │   └── softlayer
# │   ├── requestors
# │   │   ├── cws
# │   │   ├── hostRequestors.json
# │   │   └── symA
# │   └── schema
# │       ├── provisioned_host.properties
# │       └── request.properties
# ├── db
# ├── log
# └── work

# $ tree -L 3 /opt/ibm/spectrumcomputing/3.8/hostfactory/
# /opt/ibm/spectrumcomputing/3.8/hostfactory/
# ├── providers
# │   ├── aws
# │   │   ├── lib
# │   │   ├── postprovision
# │   │   └── scripts
# │   ├── azure
# │   │   ├── lib
# │   │   ├── postprovision
# │   │   └── scripts
# │   ├── common
# │   │   └── lib
# │   └── softlayer
# │       ├── lib
# │       ├── postprovision
# │       └── scripts
# ├── requestors
# │   ├── cws
# │   │   └── scripts
# │   └── symA
# │       └── scripts
# └── samples
#     └── providers
#         └── custom

######################
# HostFactory Provider
# - will be installed by cluster-init for easy updates
######################

hostfactory_confdir="#{node['symphony']['hostfactory']['confdir']}"

# directory "#{hostfactory_confdir}/providers/azurecc/conf" do
#   recursive true
#   group "egoadmin"
#   owner "egoadmin"
# end

# directory "#{hostfactory_confdir}/providerplugins/azurecc/conf" do
#   recursive true
#   group "egoadmin"
#   owner "egoadmin"
# end

# directory "#{hostfactory_confdir}/requestors/symA/conf" do
#   recursive true
#   group "egoadmin"
#   owner "egoadmin"
# end

# template "#{hostfactory_confdir}/hostfactoryconf.json" do
#   source "#{node['symphony']['hostfactory']['templates_dir']}/hostfactoryconf.json.erb"
#   group "egoadmin"
#   owner "egoadmin"
#   not_if "grep -q AZURECC #{hostfactory_confdir}/hostfactoryconf.json"
# end

# template "#{hostfactory_confdir}/providerplugins/hostProviderPlugins.json" do
#   source "#{node['symphony']['hostfactory']['templates_dir']}/hostProviderPlugins.json.erb"
#   group "egoadmin"
#   owner "egoadmin"
#   not_if "grep -q azurecc #{hostfactory_confdir}/providerplugins/hostProviderPlugins.json"
# end

# template "#{hostfactory_confdir}/providers/hostProviders.json" do
#   source "#{node['symphony']['hostfactory']['templates_dir']}/hostProviders.json.erb"
#   group "egoadmin"
#   owner "egoadmin"
#   not_if "grep -q azurecc #{hostfactory_confdir}/providers/hostProviders.json"
# end

# template "#{hostfactory_confdir}/providers/azurecc/conf/azureccprov_config.json" do
#   action :create_if_missing
#   source "#{node['symphony']['hostfactory']['templates_dir']}/azureccprov_config.json.erb"
#   group "egoadmin"
#   owner "egoadmin"
# end

# template "#{hostfactory_confdir}/providers/azurecc/conf/azureccprov_templates.json" do
#   action :create_if_missing
#   source "#{node['symphony']['hostfactory']['templates_dir']}/azureccprov_templates.json.erb"
#   group "egoadmin"
#   owner "egoadmin"
# end

# template "#{hostfactory_confdir}/requestors/hostRequestors.json" do
#   source "#{node['symphony']['hostfactory']['templates_dir']}/hostRequestors.json.erb"
#   group "egoadmin"
#   owner "egoadmin"
#   not_if "grep -q azurecc #{hostfactory_confdir}/requestors/hostRequestors.json"
# end

# template "#{hostfactory_confdir}/requestors/symA/conf/symAreq_config.json" do
#   source "#{node['symphony']['hostfactory']['templates_dir']}/symAreq_config.json.erb"
#   group "egoadmin"
#   owner "egoadmin"
#   not_if "grep -q azurecc #{hostfactory_confdir}/requestors/symA/conf/symAreq_config.json"
# end

# template "#{hostfactory_confdir}/requestors/symA/conf/symAreq_policy_config.json" do
#   source "#{node['symphony']['hostfactory']['templates_dir']}/symAreq_policy_config.json.erb"
#   group "egoadmin"
#   owner "egoadmin"
#   not_if "grep -q azurecc #{hostfactory_confdir}/requestors/symA/conf/symAreq_policy_config.json"
# end

jetpack_download "symphony/#{node['symphony']['pkg_plugin']}" do
    project "symphony"
end 
bash "Unzip symphony project..." do
  code <<-EOH
  cd #{node['jetpack']['downloads']}
  unzip #{node['symphony']['pkg_plugin']} -d /tmp
  chown -R egoadmin:egoadmin /tmp/hostfactory
  EOH
  user "root"
  group "root"
end
bash 'Installing HostFactory...' do
  code <<-EOH
  cd #{node['jetpack']['downloads']}
  unzip #{node['symphony']['pkg_plugin']} -d /tmp
  cd /tmp/hostfactory
  chmod +x install.sh
  ./install.sh
  EOH
  user "root"
  group "root"
end

defer_block 'Defer start of HostFactory service until ego is started' do
  bash 'Starting HostFactory...' do
    code <<-EOH
    set -x
    . /etc/profile.d/symphony.sh
    set -e

    egosh user logon -u #{node['symphony']['soam']['user']} -x #{node['symphony']['soam']['password']}
    set +e
    egosh service stop HostFactory
    set -e
    # Sleep to wait for DEALLOCATING state
    sleep 5
    egosh service start HostFactory
    EOH
    user "egoadmin"
    group "egoadmin"
  end
end
