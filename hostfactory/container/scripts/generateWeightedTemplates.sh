#!/bin/bash -e
cat <<EOF >/tmp/genTemplates.input.${USER}.json
{}
EOF

scriptDir=$(dirname $0)
$scriptDir/./invoke_provider.sh generate_templates -f /tmp/genTemplates.input.${USER}.json
exit $?
