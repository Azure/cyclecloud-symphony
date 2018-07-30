#!/bin/bash
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

# USER=$( jetpack config cyclecloud.cluster.user.name 2> /dev/null )
# PUB_KEY=$( jetpack config cyclecloud.cluster.user.public_key 2> /dev/null )

# if [ -n "$PUB_KEY" ]; then
#     USER_HOME=$( jetpack config cuser.home_dir 2> /dev/null )
    
#     sudo -u ${USER} -E -s mkdir -p ${USER_HOME}/.ssh
#     sudo -u ${USER} -E -s chmod 700 ${USER_HOME}/.ssh
#     echo ${PUB_KEY} | sudo -u ${USER} -E -s tee -a ${USER_HOME}/.ssh/authorized_keys
# fi

