#!/bin/bash
# see: https://www.ibm.com/support/knowledgecenter/SSZUMP_7.2.0/install/install_linux_compute.html
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

set -x

. /etc/profile.d/symphony.sh

SOAM_USER=$( jetpack config symphony.soam.user )
SOAM_PASSWORD=$( jetpack config symphony.soam.password )

set -e

su - -c "source /etc/profile.d/symphony.sh && yes | egoconfig join ${MASTER_ADDRESS}" egoadmin

# Enable automatic startup after reboot (TODO: might want to move restart to chef so volumes are mounted)
egosetrc.sh

# Grant sudoer access to egosudoers in file /etc/ego.sudoers (by default: egoadmin and root)
egosetsudoers.sh -f

su - -c "source /etc/profile.d/symphony.sh && egosh user logon -u ${SOAM_USER} -x ${SOAM_PASSWORD}" egoadmin
su - -c 'source /etc/profile.d/symphony.sh && egosh ego start' egoadmin


# Verify setup
# It takes a while for the node to be added
# Give the services 10 tries to start
counter=0
until su - -c 'source /etc/profile.d/symphony.sh && egosh resource list -l' egoadmin | tr '[:upper:]' '[:lower:]' | tee | grep -q $( hostname -s | tr '[:upper:]' '[:lower:]' ); do
    if [[ "$counter" -gt 10 ]]; then
	echo "Failed to add execute node to cluster after $counter retries.  Something is probably wrong."
	exit -1
    else
	counter=$((counter+1))
	sleep 12
	echo "Retry $counter..."
    fi
done

su - -c 'source /etc/profile.d/symphony.sh && egosh resource list -l' egoadmin
