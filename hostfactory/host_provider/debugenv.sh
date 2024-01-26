#!/bin/bash

export HF_TOP=$EGO_TOP/hostfactory
export HF_LOGDIR=$HF_TOP/log
export HF_CONFDIR=$HF_TOP/conf
export HF_WORKDIR=$HF_TOP/work

cat <<EOF >/tmp/input.json
{}
EOF

