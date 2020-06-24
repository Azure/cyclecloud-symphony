#!/bin/bash

. /etc/profile.d/symphony.sh

USE_HOSTFACTORY=$( jetpack config symphony.host_factory.enabled )
if [ "${USE_HOSTFACTORY,,}" != "true"]; then
    echo "Skipping Host Factory configuration: symphony.host_factory.enabled = ${USE_HOSTFACTORY,,}"
    exit 0
fi

set -e
set -x


# For now...
# Just link the files directory from the Symphony install to make it easy to update the factory

chmod 775 /opt/ibm/spectrumcomputing/eservice/hostfactory/conf
chmod 775 ${CYCLECLOUD_SPEC_PATH}/files/host_provider/*.sh

mkdir -p ${EGO_TOP}/${EGO_VERSION}/hostfactory/providers/azurecc
ln -sf ${CYCLECLOUD_SPEC_PATH}/files/host_provider ${EGO_TOP}/${EGO_VERSION}/hostfactory/providers/azurecc/scripts


set +e
# for jetpack log access
usermod -a -G cyclecloud egoadmin
set -e


# echo "TEMPORARY: Patching symA Requestor..."
# sed -i.orig '/#status 1: Ready with no load, add all allocated hosts as candidates for removal/a\
#         # PATCH azurecc\
#         if "allocated_hosts" not in j:\
#             j["allocated_hosts"] = []' ${EGO_TOP}/${EGO_VERSION}/hostfactory/requestors/symA/scripts/Main.py


echo "Starting HostFactory..."
sudo -i -u egoadmin bash << EOF
. /etc/profile.d/symphony.sh
egosh user logon -u Admin -x Admin
egosh service stop HostFactory
egosh service start HostFactory
egosh service view HostFactory
EOF



