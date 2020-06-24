
default['symphony']['version'] = "7.3.0.0"
default['symphony']['eval'] = false
default['symphony']['pkg']['linux'] = "sym-#{node['symphony']['version']}_x86_64.bin"
default['symphony']['pkg']['windows'] = "sym-#{node['symphony']['version']}.exe"
# TODO: Test with std license (binaries are specific to the license type as well)
default['symphony']['license_file'] = "sym_adv_entitlement.dat"
if node['symphony']['eval'] == true
  default['symphony']['pkg']['linux'] = "symeval-#{node['symphony']['version']}_x86_64.bin"
  default['symphony']['pkg']['windows'] = "symeval-#{node['symphony']['version']}.exe"
  default['symphony']['license_file'] = "sym_adv_ev_entitlement.dat"
end

default['symphony']['simplifiedwem'] = 'N'
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


default['symphony']['is_master'] = false
default['symphony']['is_management'] = false

default['symphony']['ego_top'] = '/opt/ibm/spectrumcomputing'
default['symphony']['ego_version'] = '3.8'
default['symphony']['ego_confdir'] = "#{node['symphony']['ego_top']}/kernel/conf"



# Auto-scaling configuration

# Use hostfactory? (Else use legacy autoscale.py)
default['symphony']['host_factory']['enabled'] = true

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

