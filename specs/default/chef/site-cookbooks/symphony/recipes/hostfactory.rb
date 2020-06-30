# coding: utf-8
#
# Cookbook Name:: symphony
# Recipe:: hostfactory
#
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.


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

hostfactory_confdir="#{node['symphony']['ego_top']}/eservice/hostfactory/conf"

directory "#{hostfactory_confdir}/providers/azurecc/conf" do
  recursive true
  group "egoadmin"
  owner "egoadmin"
end

directory "#{hostfactory_confdir}/requestors/symA/conf" do
  recursive true
  group "egoadmin"
  owner "egoadmin"
end

template "#{hostfactory_confdir}/hostfactoryconf.json" do
  source "hostfactory/hostfactoryconf.json.erb"
  group "egoadmin"
  owner "egoadmin"
  not_if "grep -q AZURECC #{hostfactory_confdir}/hostfactoryconf.json"
end

template "#{hostfactory_confdir}/providers/hostProviders.json" do
  source "hostfactory/hostProviders.json.erb"
  group "egoadmin"
  owner "egoadmin"
  not_if "grep -q azurecc #{hostfactory_confdir}/providers/hostProviders.json"
end

template "#{hostfactory_confdir}/providers/azurecc/conf/azureccprov_config.json" do
  action :create_if_missing
  source "hostfactory/azureccprov_config.json.erb"
  group "egoadmin"
  owner "egoadmin"
end

template "#{hostfactory_confdir}/providers/azurecc/conf/azureccprov_templates.json" do
  action :create_if_missing
  source "hostfactory/azureccprov_templates.json.erb"
  group "egoadmin"
  owner "egoadmin"
end

template "#{hostfactory_confdir}/requestors/hostRequestors.json" do
  source "hostfactory/hostRequestors.json.erb"
  group "egoadmin"
  owner "egoadmin"
  not_if "grep -q azurecc #{hostfactory_confdir}/requestors/hostRequestors.json"
end

template "#{hostfactory_confdir}/requestors/symA/conf/symAreq_config.json" do
  source "hostfactory/symAreq_config.json.erb"
  group "egoadmin"
  owner "egoadmin"
  not_if "grep -q azurecc #{hostfactory_confdir}/requestors/symA/conf/symAreq_config.json"
end

template "#{hostfactory_confdir}/requestors/symA/conf/symAreq_policy_config.json" do
  source "hostfactory/symAreq_policy_config.json.erb"
  group "egoadmin"
  owner "egoadmin"
  not_if "grep -q azurecc #{hostfactory_confdir}/requestors/symA/conf/symAreq_policy_config.json"
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
