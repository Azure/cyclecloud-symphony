#!/bin/bash

set -e

export HF_TOP=${HF_TOP:-/opt/ibm/spectrumcomputing/hostfactory}
export HF_CONFDIR=${HF_CONFDIR:-${HF_TOP}/conf}
export HF_LOGDIR=${HF_LOGDIR:-${HF_TOP}/log}
export HF_WORKDIR=${HF_WORKDIR:-${HF_TOP}/work}

export PRO_SCRIPTDIR=${HF_TOP}/1.1/providerplugins/azurecc/scripts
export PRO_CONFDIR=${HF_CONFDIR}/providers/azurecc/conf

DEPLOY_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

if ! groups egoadmin | grep -q docker; then
    echo "Adding egoadmin to docker group..."
    usermod -aG docker egoadmin
    newgrp docker
fi

cat <<EOF > /etc/profile.d/azurecc.sh
#!/bin/bash

export PRO_IMAGE_TAG="${PRO_IMAGE_TAG}"

EOF

echo "Copying scripts to ${PRO_SCRIPTDIR}..."
rm -rf ${PRO_SCRIPTDIR}
mkdir -p ${PRO_SCRIPTDIR}
cp -a ${DEPLOY_DIR}/scripts/* ${PRO_SCRIPTDIR}/

echo "Generating initial HostFactory templates..."
mkdir -p ${PRO_CONFDIR}
sudo -u egoadmin -i ${PRO_SCRIPTDIR}/generateWeightedTemplates.sh > ${PRO_CONFDIR}/azureccprov_templates.json

chown -R egoadmin:egoadmin ${PRO_SCRIPTDIR}
chown -R egoadmin:egoadmin ${HF_CONFDIR}
chown -R egoadmin:egoadmin ${HF_LOGDIR}
chown -R egoadmin:egoadmin ${HF_WORKDIR}

