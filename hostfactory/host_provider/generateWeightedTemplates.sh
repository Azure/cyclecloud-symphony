#!/bin/bash -e
#TODO: Change path so it does not mess with permissions
export HF_LOGDIR=/tmp/log
export HF_CONFDIR=$HF_TOP/conf
export HF_WORKDIR=/tmp/work
mkdir -p $HF_LOGDIR
mkdir -p $HF_WORKDIR
cat <<EOF >/tmp/input.json
{}
EOF
export PRO_LOG_DIR=${HF_LOGDIR}
export PRO_CONF_DIR=${HF_CONFDIR}/providers/azurecc
export PRO_DATA_DIR=${HF_WORKDIR}

env > /tmp/invoke2.env
venv_path=/opt/ibm/spectrumcomputing/hostfactory/1.1/providerplugins/azurecc/venv/bin
scriptDir=`dirname $0`
export PYTHONPATH=$PYTHONPATH:$scriptDir/src
# $scriptDir/./invoke_provider.sh generate_template $@
. $venv_path/activate
$venv_path/python3 -m cyclecloud_provider generate_template -f /tmp/input.json 2>> /tmp/template_generate.out
if [ $? != 0 ]; then
    echo "Template generation failed check logs in /tmp/template_generate.out"
fi
rm -rf $HF_LOGDIR
rm -rf $HF_WORKDIR
exit 0