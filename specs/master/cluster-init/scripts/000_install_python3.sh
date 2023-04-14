#!/bin/bash
if [ $(whoami) != root ]; then
  echo "Please run as root"
  exit 1
fi
export PATH=$PATH:/root/bin
# remove jetpack's python3 from the path
export PATH=$(echo $PATH | sed -e 's/\/opt\/cycle\/jetpack\/system\/embedded\/bin://g' | sed -e 's/:\/opt\/cycle\/jetpack\/system\/embedded\/bin//g')
which python3 > /dev/null;
if [ $? != 0 ]; then
    if [[ "$(cat /etc/os-release)" == *"Ubuntu"* ]]; then
      apt install -y python3 
    elif [[ "$(cat /etc/os-release)" == *"CentOS"* ]]; then
      yum install -y python3
    else
      echo "Unknown distribution"
    fi
fi