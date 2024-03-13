#!/bin/bash

. /etc/profile.d/symphony.sh

SOAM_USER=$( jetpack config symphony.soam.user )
SOAM_PASSWORD=$( jetpack config symphony.soam.password )


USE_HOSTFACTORY=$( jetpack config symphony.host_factory.enabled )
if [ "${USE_HOSTFACTORY,,}" != "true"]; then
    echo "Skipping Host Factory configuration: symphony.host_factory.enabled = ${USE_HOSTFACTORY,,}"
    exit 0
fi

SYM_VERSION=$( jetpack config symphony.version )
HF_TOP=$( jetpack config symphony.hostfactory.top )
if [ -z "${HF_TOP}" ]; then
   # In Symphony 7.2 and earlier: HF_TOP=$EGO_TOP/eservice/hostfactory
   if [ $SYM_VERSION == "7.2"* ]; then
      HF_TOP=$EGO_TOP/eservice/hostfactory
   else
      HF_TOP=$EGO_TOP/hostfactory
    fi
fi

HF_VERSION=$( jetpack config symphony.hostfactory.version )


set -e
set -x


# For now...
# Just link the files directory from the Symphony install to make it easy to update the factory

chmod 775 ${HF_TOP}/conf
chmod 775 /tmp/hostfactory/host_provider/*.sh

#Check if SYM_VERSION is 7.2 or earlier
if [ $SYM_VERSION == "7.2"* ]; then
    mkdir -p ${EGO_TOP}/${EGO_VERSION}/hostfactory/providers/azurecc
    ln -sf /tmp/hostfactory/host_provider ${EGO_TOP}/${EGO_VERSION}/hostfactory/providers/azurecc/scripts
else
    mkdir -p ${HF_TOP}/${HF_VERSION}/providerplugins/azurecc
    ln -sf /tmp/hostfactory/host_provider ${HF_TOP}/${HF_VERSION}/providerplugins/azurecc/scripts
fi

set +e
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
egosh user logon -u ${SOAM_USER} -x ${SOAM_PASSWORD}
egosh service stop HostFactory
egosh service start HostFactory
egosh service view HostFactory
EOF



