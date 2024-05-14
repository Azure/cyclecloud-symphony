import sys
import datetime

now = datetime.datetime.now()
seconds = int(sys.argv[1])
status_updated_time = now - datetime.timedelta(seconds=seconds)
expiration_time = now + datetime.timedelta(hours=1)

def format_time(timestamp):
    return datetime.datetime.strftime(timestamp, "%Y-%m-%d %H:%M:%S.%f-05:00")

account_name = sys.argv[2]
region_name = sys.argv[3]
machine_name = sys.argv[4]
print(f'''
AdType = "Cloud.Capacity"
ExpirationTime = `{format_time(expiration_time)}`
AccountName = "{account_name}"
StatusUpdatedTime = `{format_time(status_updated_time)}`
Region = "{region_name}"
HasCapacity = {seconds <= 0}
Provider = "azure"
Name = "region/{account_name}/{region_name}/{machine_name}"
MachineType = "{machine_name}" ''')

file = open('/tmp/test.dat', 'w')
file.write(f'''AdType = "Cloud.Capacity"
ExpirationTime = `{format_time(expiration_time)}`
AccountName = "{account_name}"
StatusUpdatedTime = `{format_time(status_updated_time)}`
Region = "{region_name}"
HasCapacity = {seconds <= 0}
Provider = "azure"
Name = "region/{account_name}/{region_name}/{machine_name}"
MachineType = "{machine_name}"''')
file.close()
