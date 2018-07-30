
default['symphony']['version'] = "7.2.0.0"
default['symphony']['pkg']['linux'] = "symeval-#{node['symphony']['version']}_x86_64.bin"
default['symphony']['pkg']['windows'] = "symeval-#{node['symphony']['version']}.exe"
default['symphony']['license_file'] = "sym_adv_ev_entitlement.dat"

default['symphony']['simplifiedwem'] = 'N'
default['symphony']['baseport'] = 14899
default['symphony']['disablessl'] = true

# Symphony will be installed to EGO_TOP=/opt/ibm/spectrumcomputing/
# If node['symphony']['shared_fs_install'],
# Then /opt/ibm -> #{node['symphony']['shared_fs_mountpoint']}/spectrumcomputing
default['symphony']['shared_fs_mountpoint'] = '/shared'

default['symphony']['admin']['user'] = 'egoadmin'
default['symphony']['admin']['uid'] = '61111'
default['symphony']['admin']['gid'] = '61111'
default['symphony']['admin']['home'] = "#{node['cuser']['base_home_dir']}/#{node['symphony']['admin']['user']}"


default['symphony']['is_master'] = false
default['symphony']['is_management'] = false
