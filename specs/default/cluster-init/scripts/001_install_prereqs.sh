#!/bin/bash
# see: https://www.ibm.com/support/knowledgecenter/SSZUMP_7.2.0/install/install_linux_management.html
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

# set -x

# yum install -y gettext net-tools which
# yum install -y java-1.8.0-openjdk-devel
# # apt-get install -y gettext lib32z1
# # apt-get install -y openjdk-8-jdk 
# # apt-get install -y rpm

# BASE_HOME=$( jetpack config cuser.base_home_dir )
# USER_HOME=${BASE_HOME}/egoadmin

# useradd -m -d ${USER_HOME} egoadmin

# cat <<EOF >> /etc/security/limits.conf
# egoadmin soft nproc 65536
# egoadmin hard nproc 65536
# egoadmin soft nofile 65536
# egoadmin hard nofile 65536
# EOF

# # Allow passwordless ssh within the cluster
# sudo -u egoadmin -E -s mkdir -p ${USER_HOME}/.ssh
# sudo -u egoadmin -E -s chmod 700 ${USER_HOME}/.ssh
# if ! test -f ${USER_HOME}/.ssh/id_rsa; then
#     sudo -u egoadmin -E -s bash -c "ssh-keygen -t rsa -q -N '' -f ${USER_HOME}/.ssh/id_rsa"
#     cat ${USER_HOME}/.ssh/id_rsa.pub | sudo -u egoadmin -E -s tee -a ${USER_HOME}/.ssh/authorized_keys
# fi

