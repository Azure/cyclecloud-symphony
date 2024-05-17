#!/bin/bash
export PRO_LOG_DIR=${HF_LOGDIR}
export PRO_CONF_DIR=${HF_CONFDIR}/providers/azurecc
export PRO_DATA_DIR=${HF_WORKDIR}

export STDERR_FILE=${HF_LOGDIR}/azurecc_invoke.err


scriptDir=`dirname $0`
export PYTHONPATH=$PYTHONPATH:$scriptDir/src

env > /tmp/invoke.env

venv_path=$HF_TOP/$HF_VERSION/providerplugins/azurecc/venv/bin

if [ -e $venv_path ]; then
	args=$@
	. $venv_path/activate
	$venv_path/python3 -m cyclecloud_provider $args 2>>$STDERR_FILE
	exit $?
else
	echo "ERROR: Could not find venv at $venv_path"
	exit 1
fi
