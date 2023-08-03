#!/bin/bash
HF_TOP=$( jetpack config symphony.hostfactory.top )
if [ -z "${HF_TOP}" ]; then
   # In Symphony 7.2 and earlier: HF_TOP=$EGO_TOP/eservice/hostfactory
    HF_TOP=$EGO_TOP/hostfactory
fi

HF_VERSION=$( jetpack config symphony.hostfactory.version )
if [ -z "${HF_VERSION}" ]; then
    HF_VERSION="1.2"
fi

PKG_NAME=$( jetpack config symphony.pkg_plugin )

cd /tmp
pluginSrcPath=$HF_TOP/$HF_VERSION/providerplugins/azurecc
VENV=$pluginSrcPath/venv
export PATH=$(echo $PATH | sed -e 's/\/opt\/cycle\/jetpack\/system\/embedded\/bin://g' | sed -e 's/:\/opt\/cycle\/jetpack\/system\/embedded\/bin//g')
export PATH=$PATH:/root/bin:/usr/bin

python3 -m virtualenv --version 2>&1 > /dev/null
if [ $? != 0 ]; then
    python3 -m pip install virtualenv || exit 1
fi
set -e
echo "venv path"
echo $VENV
python3 -m virtualenv $VENV
source $VENV/bin/activate
pip install --upgrade packages/*
rsync -av -r --exclude '*.bat' --include '*.sh|*.py'  hostfactory/1.2/providerplugins/azurecc/scripts  $pluginSrcPath

if [ -f $PKG_NAME ]; then
    rm -f $PKG_NAME
    rm -rf packages
    rm -rf hostfactory
fi
SOAM_USER=$( jetpack config symphony.soam.user )
SOAM_PASSWORD=$( jetpack config symphony.soam.password )
echo "Starting HostFactory..."
sudo -i -u egoadmin bash << EOF
. /etc/profile.d/symphony.sh
egosh user logon -u ${SOAM_USER} -x ${SOAM_PASSWORD}
egosh service stop HostFactory
egosh service start HostFactory
egosh service view HostFactory
EOF