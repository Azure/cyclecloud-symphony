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
import jetpack.config

from datetime import datetime

# Arguments
AUTOSTOP_ENABLED = jetpack.config.get('cyclecloud.cluster.autoscale.stop_enabled') is True

# Short-circuit without error if not enabled
if not AUTOSTOP_ENABLED:
    sys.exit(0)

IDLE_TIME_AFTER_JOBS = int(jetpack.config.get('cyclecloud.cluster.autoscale.idle_time_after_jobs'))
IDLE_TIME_BEFORE_JOBS = int(jetpack.config.get('cyclecloud.cluster.autoscale.idle_time_before_jobs'))

# Checks to see if we should shutdown
idle_long_enough = false


def is_active():
    return true
    
    
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


def run(args):
    return is_active()
    
if __name__ == "__main__":
    run(sys.argv[1:])
