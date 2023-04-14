#!/bin/bash

export HF_TOP=$( jetpack config symphony.hostfactory.top )
if [ -z "${HF_TOP}" ]; then
   # In Symphony 7.2 and earlier: HF_TOP=$EGO_TOP/eservice/hostfactory
   export HF_TOP=$EGO_TOP/hostfactory
fi
export HF_LOGDIR=$HF_TOP/log
export HF_CONFDIR=$HF_TOP/conf
export HF_WORKDIR=$HF_TOP/work

cat <<EOF >/tmp/input.json
{}
EOF

