#!/bin/bash -e
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

# default create machines request
cat << EOF > /tmp/create_input.json
{
 "template": {
     "machineCount": 1000,
     "templateId": "execute"
 },
 "user_data": {}
}
EOF


venv_path=$HF_TOP/$HF_VERSION/providerplugins/azurecc/venv/bin
scriptDir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
export PYTHONPATH=$PYTHONPATH:$scriptDir/src
source "${venv_path}/activate"
if [ $1 == "validate_templates" ]; then
    "${venv_path}/python3" -m cyclecloud_provider validate_templates -f /tmp/input.json 2> /tmp/dry_run.out
elif [ $1 == "create_machines" ]; then
    if [ -z $2 ]; then
        cp /tmp/create_input.json /tmp/reqMachine.dry_run.json
    else
        cp $2 /tmp/reqMachine.dry_run.json
    fi
    "${venv_path}/python3" -m cyclecloud_provider create_machines -f /tmp/reqMachine.dry_run.json 2> /tmp/dry_run.out
fi
if [ $? != 0 ]; then
    echo "$1 failed check dry_run.out"
fi
rm -rf $HF_LOGDIR
rm -rf $HF_WORKDIR
exit 0