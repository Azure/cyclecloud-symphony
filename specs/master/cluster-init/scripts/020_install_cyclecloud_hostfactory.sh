#!/bin/bash

. /etc/profile.d/symphony.sh

SOAM_USER=$( jetpack config symphony.soam.user )
SOAM_PASSWORD=$( jetpack config symphony.soam.password )


USE_HOSTFACTORY=$( jetpack config symphony.host_factory.enabled )
if [ "${USE_HOSTFACTORY,,}" != "true"]; then
    echo "Skipping Host Factory configuration: symphony.host_factory.enabled = ${USE_HOSTFACTORY,,}"
    exit 0
fi
HF_TOP=$( jetpack config symphony.hostfactory.top )
if [ -z "${HF_TOP}" ]; then
   # In Symphony 7.2 and earlier: HF_TOP=$EGO_TOP/eservice/hostfactory
   HF_TOP=$EGO_TOP/hostfactory
fi

HF_VERSION=$( jetpack config symphony.hostfactory.version )
if [ -z "${HF_VERSION}" ]; then
    HF_VERSION="1.1"
fi

set -e
set -x


# For now...
# Just link the files directory from the Symphony install to make it easy to update the factory

chmod 775 ${HF_TOP}/conf
chmod 775 ${CYCLECLOUD_SPEC_PATH}/files/host_provider/*.sh

# Symphony 7.2 and earlier
mkdir -p ${EGO_TOP}/${EGO_VERSION}/hostfactory/providers/azurecc
ln -sf ${CYCLECLOUD_SPEC_PATH}/files/host_provider ${EGO_TOP}/${EGO_VERSION}/hostfactory/providers/azurecc/scripts

# Symphony 7.3 and later
mkdir -p ${HF_TOP}/${HF_VERSION}/providerplugins/azurecc
ln -sf ${CYCLECLOUD_SPEC_PATH}/files/host_provider ${HF_TOP}/${HF_VERSION}/providerplugins/azurecc/scripts



set +e
# for jetpack log access
usermod -a -G cyclecloud egoadmin
set -e


# echo "TEMPORARY: Patching symA Requestor..."
# sed -i.orig '/#status 1: Ready with no load, add all allocated hosts as candidates for removal/a\
#         # PATCH azurecc\
#         if "allocated_hosts" not in j:\
#             j["allocated_hosts"] = []' ${EGO_TOP}/${EGO_VERSION}/hostfactory/requestors/symA/scripts/Main.py

#moved this to install scalelib sript
# echo "Starting HostFactory..."
# sudo -i -u egoadmin bash << EOF
# . /etc/profile.d/symphony.sh
# egosh user logon -u ${SOAM_USER} -x ${SOAM_PASSWORD}
# egosh service stop HostFactory
# egosh service start HostFactory
# egosh service view HostFactory
# EOF



