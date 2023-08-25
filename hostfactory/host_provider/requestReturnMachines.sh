#!/bin/bash -e

cp $2 /tmp/reqRetMach.input.json

scriptDir=$(dirname $0)
$scriptDir/./invoke_provider.sh terminate_machines $@ | tee -a /tmp/reqRetMach.output.json
exit $?
