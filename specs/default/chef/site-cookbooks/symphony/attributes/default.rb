
default['symphony']['version'] = "7.3.2.0"
default['symphony']['eval'] = true
default['symphony']['pkg']['linux'] = "sym-#{node['symphony']['version']}_x86_64.bin"
default['symphony']['pkg']['windows'] = "sym-#{node['symphony']['version']}.exe"
default['symphony']['pkg_plugin'] = "cyclecloud-symphony-pkg-3.0.0.zip"
default['symphony']['simplifiedwem'] = 'N'
# TODO: Test with std license (binaries are specific to the license type as well)
default['symphony']['license_file'] = "sym_adv_entitlement.dat"
if node['symphony']['eval'] == true
  default['symphony']['pkg']['linux'] = "symeval-#{node['symphony']['version']}_x86_64.bin"
  default['symphony']['pkg']['windows'] = "symeval-#{node['symphony']['version']}.exe"
  default['symphony']['license_file'] = "sym.entitlement.keys.eval"
  default['symphony']['simplifiedwem'] = 'Y'
end

default['symphony']['baseport'] = 14899
default['symphony']['lim_port'] = node['symphony']['baseport']
default['symphony']['kd_port'] = node['symphony']['baseport'] + 1
default['symphony']['pem_port'] = node['symphony']['baseport'] + 2
default['symphony']['snmp_port'] = node['symphony']['baseport'] + 14
default['symphony']['disablessl'] = true

# Symphony will be installed to EGO_TOP=/opt/ibm/spectrumcomputing/, so mount at /opt/ibm (or symlink)
default['symphony']['shared_fs_install'] = false

default['symphony']['admin']['user'] = 'egoadmin'
default['symphony']['admin']['uid'] = '1001' # 61111
default['symphony']['admin']['gid'] = '1002' # 61111
default['symphony']['admin']['home'] = "#{node['cuser']['base_home_dir']}/#{node['symphony']['admin']['user']}"
default['symphony']['soam']['user'] = 'Admin'
default['symphony']['soam']['password'] = 'Admin'

default['symphony']['is_master'] = false
default['symphony']['is_management'] = false

default['symphony']['ego_top'] = '/opt/ibm/spectrumcomputing'
default['symphony']['ego_version'] = '3.8'
default['symphony']['ego_confdir'] = "#{node['symphony']['ego_top']}/kernel/conf"



# Auto-scaling configuration

# Use hostfactory? (Else use legacy autoscale.py)
default['symphony']['host_factory']['enabled'] = true

# Hostfactory location has changed in Symphony 7.3+
if (Gem::Version.new(node['symphony']['version']) >= Gem::Version.new('7.3.0'))
  default['symphony']['hostfactory']['top'] = "#{node['symphony']['ego_top']}/hostfactory"
  default['symphony']['hostfactory']['templates_dir'] = 'hostfactory/7.3'
else
  default['symphony']['hostfactory']['top'] = "#{node['symphony']['ego_top']}/eservice/hostfactory"
  default['symphony']['hostfactory']['templates_dir'] = 'hostfactory/7.2'
end
default['symphony']['hostfactory']['confdir'] = "#{node['symphony']['hostfactory']['top']}/conf"
default['symphony']['hostfactory']['version'] = "1.2"

# IP or Hostname for REST API URLs
default['symphony']['hostfactory']['rest_address'] = '127.0.0.1'

default['symphony']['hostfactory']['HF_LOGLEVEL'] = 'LOG_DEBUG'
default['symphony']['hostfactory']['HF_REQUESTOR_POLL_INTERVAL'] = 30
default['symphony']['hostfactory']['HF_HOUSEKEEPING_LOOP_INTERVAL'] = 30
default['symphony']['hostfactory']['HF_REST_TRANSPORT'] = 'TCPIPv4'
default['symphony']['hostfactory']['HF_REST_LISTEN_PORT'] = 9080
default['symphony']['hostfactory']['HF_REQUESTOR_ACTION_TIMEOUT'] = 240
default['symphony']['hostfactory']['HF_PROVIDER_ACTION_TIMEOUT'] = 300
default['symphony']['hostfactory']['HF_DB_HISTORY_DURATION'] = 90
default['symphony']['hostfactory']['HF_REST_RESULT_DEFAULT_PAGESIZE'] = 2000
default['symphony']['hostfactory']['HF_REST_RESULT_MAX_PAGESIZE'] = 10000


# symA requestor params
default['symphony']['hostfactory']['requestors']['symA']['cloud_apps']['symping']['name'] = 'symping7.3'
default['symphony']['hostfactory']['requestors']['symA']['scaling_policy']['warmup_time'] = 1
default['symphony']['hostfactory']['requestors']['symA']['scaling_policy']['history_expiry_time'] = 10
default['symphony']['hostfactory']['requestors']['symA']['scaling_policy']['active_task_moving_avg']  = 3
default['symphony']['hostfactory']['requestors']['symA']['scaling_policy']['startup_cores_if_no_history'] = 1
default['symphony']['hostfactory']['requestors']['symA']['scaling_policy']['desired_task_complete_duration'] = 1
default['symphony']['hostfactory']['requestors']['symA']['scaling_policy']['ego_host_startup_time'] = 5
default['symphony']['hostfactory']['requestors']['symA']['scaling_policy']['ego_failover_timeout'] = 10
default['symphony']['hostfactory']['requestors']['symA']['host_return_policy']['name'] = 'immediate'
# Billing interval MUST be >= Return Interval (required by SymA requestor)
default['symphony']['hostfactory']['requestors']['symA']['host_return_policy']['billing_interval'] = 2
default['symphony']['hostfactory']['requestors']['symA']['host_return_policy']['return_interval'] = 2
default['symphony']['hostfactory']['requestors']['symA']['host_return_policy']['force_return_interval'] = 5
default['symphony']['hostfactory']['requestors']['symA']['host_return_policy']['return_idle_only'] = true

#attributes for sethostname
default[:symphony][:ensure_waagent_monitor_hostname] = true
default[:symphony][:use_nodename_as_hostname] = false

default[:symphony][:enable_weighted_templates] = true
default[:symphony][:ncpus_use_vcpus] = true