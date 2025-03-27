#!/bin/bash

# HF_ variables should come from Symphony environment (defaults provided for debugging)
export HF_TOP=${HF_TOP:-/opt/ibm/spectrumcomputing/hostfactory}
export HF_LOGDIR=${HF_LOGDIR:-${HF_TOP}/log}
export HF_CONFDIR=${HF_CONFDIR:-${HF_TOP}/conf}
export HF_WORKDIR=${HF_WORKDIR:-${HF_TOP}/work}

export PRO_IMAGE_TAG=${PRO_IMAGE_TAG:-azurecc:latest}
export PRO_HF_TOP=/opt/ibm/spectrumcomputing/hostfactory
export PRO_SCRIPTDIR=${PRO_HF_TOP}/1.1/providerplugins/azurecc/scripts
export PRO_HF_LOGDIR=${PRO_HF_TOP}/log
export PRO_HF_CONFDIR=${PRO_HF_TOP}/conf
export PRO_HF_WORKDIR=${PRO_HF_TOP}/work

if [ -f "/etc/profile.d/azurecc.sh" ]; then
	source /etc/profile.d/azurecc.sh
fi

# copy input file into container mounted folder
export HF_INPUT_DIR=${HF_WORKDIR}/inputs
mkdir -p ${HF_INPUT_DIR}
PLUGIN_ACTION=${1}
PRO_INPUT_FILE=${HF_INPUT_DIR}/${PLUGIN_ACTION}.${USER}.json
cp "${3}" "${PRO_INPUT_FILE}"

echo `date` "  Invoking:" >> /tmp/invoke_provider_container.${USER}.log
exec {BASH_XTRACEFD}>>/tmp/invoke_provider_container.${USER}.log # redirect bash echo / xtrace
set -x

scriptDir=`dirname $0`
export PYTHONPATH=$PYTHONPATH:$scriptDir
venv_path=${DOCKER_VENV_PATH}

if [ -z "$venv_path" ]; then
	venv_path=$scriptDir/venv
	python3 -m venv $venv_path
	. $venv_path/bin/activate
	pip install docker
	deactivate
fi

if [ -e $venv_path ]; then
	. $venv_path/bin/activate
	$venv_path/bin/python3 -m docker_exec.py ${PLUGIN_ACTION} -f ${PRO_INPUT_FILE} 2>>/tmp/invoke_provider_container.${USER}.log
	exit $?
else
	echo "ERROR: Could not find venv at $venv_path"
	exit 1
fi