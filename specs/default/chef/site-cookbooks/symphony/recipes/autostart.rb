#
# Cookbook Name:: symphony
# Recipe:: autostart
#
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

if node['symphony']['host_factory']['enabled'] && node['cyclecloud']['cluster']['autoscale']['start_enabled']
  include_recipe "symphony::hostfactory"
end

if node['os'] == 'windows'

  cookbook_file "#{node['cyclecloud']['bootstrap']}\\autostart.py" do
    source 'autostart.py'
    not_if { node['symphony']['host_factory']['enabled'] }
  end

  cookbook_file "#{node['cyclecloud']['bootstrap']}\\autostart.bat" do
    source 'autostart.bat'
    not_if { node['symphony']['host_factory']['enabled'] }
  end

  cookbook_file "#{node['cyclecloud']['bootstrap']}\\symphony_control.py" do
    source 'symphony_control.py'
  end

  cookbook_file "#{node['cyclecloud']['bootstrap']}\\symphony_control.bat" do
    source 'symphony_control.bat'
  end

  windows_task 'autostart_symphony' do
    user 'system'
    frequency :minute
    frequency_modifier 1
    command "#{node['cyclecloud']['bootstrap']}\\autostart.bat"
    only_if { node['cyclecloud']['cluster']['autoscale']['start_enabled'] }
    not_if { node['symphony']['host_factory']['enabled'] }
  end

  windows_task 'cleanup_symphony' do
    user 'system'
    frequency :minute
    frequency_modifier 5
    command "#{node['cyclecloud']['bootstrap']}\\symphony_control.bat"
  end

else # linux

  cookbook_file "#{node['cyclecloud']['bootstrap']}/autostart.py" do
    source 'autostart.py'
    owner 'root'
    group 'root'
    mode '0750'
    action :create
    not_if { node['symphony']['host_factory']['enabled'] }
  end

  cookbook_file "#{node['cyclecloud']['bootstrap']}/symphony_control.py" do
    source 'symphony_control.py'
    owner 'root'
    group 'root'
    mode '0750'
    action :create
  end

  scaleup_interval = '*'
  cron 'autostart' do
    minute scaleup_interval
    command "#{node['cyclecloud']['bootstrap']}/cron_wrapper.sh #{node['cyclecloud']['bootstrap']}/autostart.py > #{node['cyclecloud']['bootstrap']}/autostart.log 2>&1"
    only_if { node['cyclecloud']['cluster']['autoscale']['start_enabled'] }
    not_if { node['symphony']['host_factory']['enabled'] }
  end

  cron 'cleanup' do
    minute '*/5'
    command "#{node[:cyclecloud][:bootstrap]}/cron_wrapper.sh #{node[:cyclecloud][:bootstrap]}/symphony_control.py > #{node[:cyclecloud][:bootstrap]}/symphony_control.log 2>&1"
  end

  
end


