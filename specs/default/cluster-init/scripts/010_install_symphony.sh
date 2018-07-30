#!/bin/bash
# see: https://www.ibm.com/support/knowledgecenter/SSZUMP_7.2.0/install/install_linux.html
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

# set -x

# source ~/.bash_profile

# MASTER_ADDRESS=$( cat /etc/symphony_master_node | tr -d '[:space:]' )
# SYM_ENTITLEMENT_FILE="${CYCLECLOUD_SPEC_PATH}/files/sym_adv_ev_entitlement.dat"

# export CLUSTERADMIN=egoadmin
# export CLUSTERNAME=$( jetpack config cyclecloud.cluster.name )
# export SIMPLIFIEDWEM=N
# export BASEPORT=14899

# # TEMPORARY: Disable HTTPS for webservers until we have a cert
# # Web server    With SSL    Without SSL
# # Web server for the cluster management console    8443    8080
# # REST web server    8543    8180
# # ascd web server    8643    8280
# export DISABLESSL=Y

# export JAVA_HOME=/usr/lib/jvm/java-openjdk

# export DERBY_DB_HOST=${MASTER_ADDRESS}

# # Install the Prod version of Symphony
# # SYMPHONY_PKG=sym-7.2.0.0_x86_64.bin
# # Install the Eval version of Symphony
# SYMPHONY_PKG=symeval-7.2.0.0_x86_64.bin

# set -e

# cp ${SYM_ENTITLEMENT_FILE} /etc/sym_adv_ev_entitlement.dat

# cd /tmp

# jetpack download ${SYMPHONY_PKG} /tmp/${SYMPHONY_PKG}
# chmod a+x ./${SYMPHONY_PKG}
# ./${SYMPHONY_PKG} --quiet

# export EGO_TOP=/opt/ibm/spectrumcomputing
# sed -i '/.*"Cannot get binary type.*/a     export EGO_BINARY_TYPE="linux-x86_64"' $EGO_TOP/kernel/conf/profile.ego
# sed -i '/export EGO_BINARY_TYPE="linux-x86_64"/a     echo "Forcing EGO binary type: $EGO_BINARY_TYPE"' $EGO_TOP/kernel/conf/profile.ego

# set +e
# . $EGO_TOP/profile.platform
# set -e

# # Create symphony environment profile
# cat <<EOF > /etc/profile.d/symphony.sh
# #!/bin/bash

# export MASTER_ADDRESS=${MASTER_ADDRESS}
# export CLUSTERADMIN=${CLUSTERADMIN}
# export CLUSTERNAME=${CLUSTERNAME}
# export SIMPLIFIEDWEM=${SIMPLIFIEDWEM}
# export BASEPORT=${BASEPORT}
# export DISABLESSL=${DISABLESSL}

# export JAVA_HOME=${JAVA_HOME}

# # Use the default derby db
# export DERBY_DB_HOST=${DERBY_DB_HOST}


# export EGO_TOP=${EGO_TOP}
# . \$EGO_TOP/profile.platform

# EOF
# chmod a+rx /etc/profile.d/symphony.sh


# # Use SSH rather than RSH for inter-node communication

# cat <<EOF >> ${EGO_CONFDIR}/ego.conf

# EGO_RSH="ssh -oPasswordAuthentication=no -oStrictHostKeyChecking=no"

# EOF
