#
# Cookbook Name:: symphony
# Recipe:: autostart
#
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

if node['symphony']['host_factory']['enabled']
  # HostFactory is in charge of autostop
  return
end

if node['os'] == 'windows'

  cookbook_file "#{node[:cyclecloud][:bootstrap]}\\autostop.py" do
    source 'autostart.py'
  end

  cookbook_file "#{node[:cyclecloud][:bootstrap]}\\autostop.bat" do
    source 'autostop.bat'
  end

  windows_task 'autostop_symphony' do
    user 'system'
    frequency :minute
    frequency_modifier 1
    command "#{node[:cyclecloud][:bootstrap]}\\autostop.bat"
    only_if { node[:cyclecloud][:cluster][:autoscale][:stop_enabled] }
  end

else # linux

  cookbook_file "#{node[:cyclecloud][:bootstrap]}/autostop.py" do
    source 'autostop.py'
    owner 'root'
    group 'root'
    mode '0750'
    action :create
  end

  scaleup_interval = '*'
  cron 'autostop' do
    minute scaleup_interval
    command "#{node[:cyclecloud][:bootstrap]}/cron_wrapper.sh #{node[:cyclecloud][:bootstrap]}/autostop.py > #{node[:cyclecloud][:bootstrap]}/autostop.log 2>&1"
    only_if { node[:cyclecloud][:cluster][:autoscale][:stop_enabled] }
  end
end
