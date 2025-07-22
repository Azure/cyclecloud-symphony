#!/bin/env python
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# Windows trickiness to make an executable script
# @setlocal enableextensions & python -x %~f0 %* & goto :EOF

import os
import sys
import math
import re
import subprocess
import time
import json

from datetime import datetime

# Assume symphony tasks are pretty fast
DEFAULT_EXPECTED_TASK_RUNTIME_SEC = 300

SESSION_COLS={'SESSION': 0,
              'STAT': 1,
              'PRI': 2,
              'DONE': 3,
              'RUN': 4,
              'ERR': 5,
              'CANL': 6,
              'PEND': 7,
              'CREATED': 8,
              'INST': 9 }

_username = os.environ.get('SOAM_USER')
_password = os.environ.get('SOAM_PASS')


def soamview(*args):
    cmd = ['soamview']
    cmd.extend(*args)
    cmd.extend(['-u', _username, '-x', _password])

    lines = []
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=-1)
    #lines = [line for line in iter(p.stdout.readline, b'')]
    #retcode = p.communicate()
    #return (p.returncode, lines, p.stderr.read())
    stdout, stderr = p.communicate()
    return (p.returncode, stdout, stderr)


def egosh(*args):
    cmd = ['egosh']
    cmd.extend(*args)

    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    retcode = p.wait()
    return (retcode, p.stdout.read(), p.stderr.read())


def list_apps():
    apps = []
    retcode, out, err = soamview(['app', '-s', 'enabled'])
    for line in out.split('\n'):
        cols =  line.split()
        if not cols:
            continue
        app = cols[0].strip()
        if app and not re.match(r'^APPLICATION', app):
            apps.append(app)
    return apps


def list_sessions(app_name, filters=None):
    sessions = []
    cmd = ['session', app_name]
    if filters:
        cmd.extend(filters)
    retcode, out, err = soamview(cmd)
    for line in out.split('\n'):
        # Do not split soam timestamps (they have a space after the comma)
        cols = [c.replace(',', ', ') for c in line.replace(', ', ',').split()]
        if not cols:
            continue
        first_col = cols[0].strip()
        if not first_col or re.match(r'^Application:', first_col) or re.match(r'^SESSION', first_col) or re.match(r'^No', first_col):
            # TODO: We could scan the SESSION line to find the cols we care about
            # TODO: for now, assume the columns are stable
            continue
        else:
            sessions.append(cols)
    return sessions


def list_tasks(app_name, session_id, filters=None):
    tasks = []
    cmd = ['task', '%s:%s' % (app_name, session_id)]
    if filters:
        cmd.extend(filters)
    retcode, out, err = soamview(cmd)
    for line in out.split('\n'):
        # Do not split soam timestamps (they have a space after the comma)
        cols = [c.replace(',', ', ') for c in line.replace(', ', ',').split()]
        if not cols:
            continue
        first_col = cols[0].strip()
        if not first_col or re.match(r'^Application:', first_col) or re.match(r'^TASK', first_col) or re.match(r'^No', first_col):
            # TODO: We could scan the SESSION line to find the cols we care about
            # TODO: for now, assume the columns are stable
            continue
        else:
            tasks.append(cols)
    return tasks

def get_resource_status():
    host_status = {}
    retcode, out, err = egosh(['resource', 'view'])
    hostname = None
    found_header = False
    for line in out.split('\n'):
        cols =  line.split()
        if not cols:
            continue
        first_col = cols[0].strip()
        if first_col:
            if re.match(r'^HOST_NAME:', first_col):
                hostname=cols[1].strip()
            elif re.match(r'^status', first_col):
                found_header = True
            elif found_header:
                host_status[hostname] = first_col.strip()
                hostname = None
                found_header = False

    return host_status


def close_host(hostname, reclaim=True, dry_run=False):
    if dry_run:
        print("Would Close host %s with reclaim %s" % (hostname, reclaim))
    else:
        print("Closing host %s with reclaim %s" % (hostname, reclaim))
        if reclaim:
            retcode, out, err = egosh(['resource', 'close', '-reclaim', hostname])
        else:
            retcode, out, err = egosh(['resource', 'close', hostname])
        print("Status: %s \n Out: %s \n Err: %s \n" % (retcode, out, err))


def close_unavail_hosts(host_status, dry_run=False):
    for h, status in host_status.items():
        if status.lower() == "unavail":
            if dry_run:
                print("Would Close unavail host %s with status %s" % (h, status))
            else:
                close_host(h, reclaim=False, dry_run=dry_run)


def remove_hosts(host_status, dry_run=False):
    for h, status in host_status.items():
         if dry_run:
             print("Would Remove host %s with status %s" % (h, status))
         else:
             print("Removing host %s with status %s" % (h, status))
             close_host(h, reclaim=True, dry_run=dry_run)
             retcode, out, err = egosh(['resource', 'remove', h])
             print("Status: %s \n Out: %s \n Err: %s \n" % (retcode, out, err))
                 

def remove_unavail_hosts(host_status, dry_run=False):
    close_unavail_hosts(host_status, dry_run=dry_run)
    for h, status in host_status.items():
        if status.lower() == "unavail":
            if dry_run:
                print("Would unavail Remove host %s with status %s" % (h, status))
            else:
                print("Removing unavail host %s with status %s" % (h, status))
                retcode, out, err = egosh(['resource', 'remove', h])
                print("Status: %s \n Out: %s \n Err: %s \n" % (retcode, out, err))


def count_tasks(app_name):
    all_tasks = 0
    running_tasks = 0
    pending_tasks = 0
    sessions = list_sessions(app_name, ['-s', 'open'])
    for cols in sessions:
        running = int(cols[SESSION_COLS['RUN']].strip())
        pending = int(cols[SESSION_COLS['PEND']].strip())
        running_tasks = running_tasks + running
        pending_tasks = pending_tasks + pending
        all_tasks = all_tasks + running + pending
            
    return all_tasks, running_tasks, pending_tasks


def count_resources():
    total_slots = 0
    free_slots = 0
    retcode, out, err = egosh(['rg'])
    for line in out.split('\n'):
        cols =  line.split()
        if not cols:
            continue
        first_col = cols[0].strip()
        # For now, just look at the ComputeHosts group (later we may autoscale different groups)
        if first_col and re.match(r'^ComputeHosts', first_col):
            total_slots = total_slots + int(cols[2].strip())
            free_slots = free_slots + int(cols[3].strip())
    return total_slots, free_slots


def convert_soam_time(soam_timestamp):
    # To get time delta in sec: (dt_1 - dt_0).total_seconds()
    # dt = datetime.strptime(soam_timestamp, '%b %d %H:%M:%S')
    dt = datetime.strptime(soam_timestamp, '%m/%d, %H:%M:%S')
    dt.replace(year=datetime.now().year)
    return dt

def convert_soam_time_to_sec(soam_timestamp):
    dt = convert_soam_time(soam_timestamp)
    ts = time.mktime(dt.timetuple())
    return ts


def estimate_runtime_per_task(app_name):
    # Get the list of up to N tasks completed in the last X hours
    # If none, just use the default runtime estimate
    time_range = '.-2:,' # last 2 hours
    num_tasks = '100'
    
    runtimes = []
    sessions = list_sessions(app_name, ['-c', time_range, '-s', 'all'])
    for cols in sessions:
        session_id = cols[SESSION_COLS['SESSION']].strip()
        tasks = list_tasks(app_name, session_id, ['-c', time_range, '-s', 'done', '-n', num_tasks])
        for task in tasks:
            start_time = convert_soam_time(task[3])
            end_time = convert_soam_time(task[4])
            runtimes.append(max(0.5, (end_time - start_time).total_seconds()))

    # If no job history, assume the running tasks will take the default time
    estimated_runtime = DEFAULT_EXPECTED_TASK_RUNTIME_SEC
    if runtimes:
        estimated_runtime = sum(runtimes) / len(runtimes)
    return estimated_runtime


def run(args):
    r_status = get_resource_status()
    print("Current Resource states: ")
    print(r_status)
    remove_unavail_hosts(r_status)
    
    
if __name__ == "__main__":
    run(sys.argv[1:])

