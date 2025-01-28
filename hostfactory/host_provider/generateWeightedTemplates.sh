#!/bin/bash -e
TEMP_HF_LOGDIR=/tmp/log
export HF_LOGDIR=$TEMP_HF_LOGDIR
export HF_CONFDIR=$HF_TOP/conf
TEMP_HF_WORKDIR=/tmp/work
export HF_WORKDIR=$TEMP_HF_WORKDIR
mkdir -p $HF_LOGDIR
mkdir -p $HF_WORKDIR
cat <<EOF >/tmp/genTemplates.input.${USER}.json
{}
EOF
export PRO_LOG_DIR=${HF_LOGDIR}
export PRO_CONF_DIR=${HF_CONFDIR}/providers/azurecc
export PRO_DATA_DIR=${HF_WORKDIR}

venv_path=$HF_TOP/$HF_VERSION/providerplugins/azurecc/venv/bin
scriptDir=`dirname $0`
export PYTHONPATH=$PYTHONPATH:$scriptDir/src
. $venv_path/activate
$venv_path/python3 -m cyclecloud_provider generate_templates -f /tmp/genTemplates.input.${USER}.json
exit_status=$?
rm -rf $TEMP_HF_LOGDIR
rm -rf $TEMP_HF_WORKDIR
exit $exit_status