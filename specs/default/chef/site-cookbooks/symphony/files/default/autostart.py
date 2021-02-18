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
import jetpack.autoscale
import jetpack.config

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

BOOTSTRAP_DIR = jetpack.config.get("cyclecloud.bootstrap")

_username = 'Admin'
_password = 'Admin'


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
    demand_by_app = {}
    
    apps = list_apps()    
    for app in apps:
        all_tasks, running_tasks, pending_tasks = count_tasks(app)
        print("Tasks for %s :\t%s\t%s\t%s" % (app, all_tasks, running_tasks, pending_tasks))
        estimated_runtime = estimate_runtime_per_task(app)
        print("\nAvg runtime for %s = %s" % (app, estimated_runtime))
        
        # Max is 1 CPU per Task, but fit to expected Tasks per hour
        hours_per_task = float(estimated_runtime)/3600
        demand_by_app[app] = min(all_tasks, int(math.ceil(all_tasks * hours_per_task))) 
        print("Demand for %s = %s with %s tasks" % (app, demand_by_app[app], all_tasks))
        
        total_slots, free_slots = count_resources()
    print("Slots: %s free of %s" % (free_slots, total_slots))

    total_demand = 0
    if demand_by_app:
        total_demand = sum(d for app, d in demand_by_app.items())
    
    print("\nUnmet Demand = %s" % (max(0, total_demand - total_slots)))

    # TODO:  We need to take Dynamic Slot Requests into account (multi-slot or partial-slot tasks)
    cores_per_slot=1
    print("Requesting %i ideal %i-core slots from the cloud." % (total_demand, cores_per_slot))


    # TODO: We should allow each app (or maybe resource group?) to specify a slot_type
    slot_type = 'execute'
    slot_demand = total_demand * cores_per_slot

    # Autoscale request takes an array of slot_type to core_count maps
    autoscale_requests = [{
        'nodearray': slot_type,
        'request_cpus': slot_demand
    }]

    print("Requesting %d slots of type: %s" % (slot_demand, slot_type))
    jetpack.autoscale.scale_by_jobs(autoscale_requests)
    
    
if __name__ == "__main__":
    run(sys.argv[1:])
