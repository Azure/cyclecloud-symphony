#!/bin/bash
export PRO_LOG_DIR=${HF_LOGDIR}
export PRO_CONF_DIR=${HF_CONFDIR}/providers/azurecc
export PRO_DATA_DIR=${HF_WORKDIR}

export STDERR_FILE=${HF_LOGDIR}/azurecc_invoke.err


scriptDir=`dirname $0`
export PYTHONPATH=$PYTHONPATH:$scriptDir/src

env > /tmp/invoke.env

embedded_python=/opt/cycle/jetpack/system/embedded/bin/python
venv_path=/opt/ibm/spectrumcomputing/hostfactory/1.1/providerplugins/azurecc/venv/bin


if [ -e $venv_path ]; then
   # Check group membership
	touch /opt/cycle/jetpack/logs/jetpack.log 1>&2 2> /dev/null
	
	if [ $? == 0 ]; then
	    . $venv_path/activate
		$venv_path/python3 -m cyclecloud_provider $@ 2>>$STDERR_FILE
		exit $?
	else
		groups $(whoami) | grep -q cyclecloud
		if [ $? != 0 ]; then
			echo $(whoami) must be added to the cyclecloud group.
			exit 1
		else 
			args=$@
			sg cyclecloud ". $venv_path/activate"
			sg cyclecloud "$venv_path/python3 -m cyclecloud_provider $args 2>>$STDERR_FILE"
			exit $?
		fi
	fi
elif [ -e $embedded_python ]; then
   # Check group membership
	touch /opt/cycle/jetpack/logs/jetpack.log 1>&2 2> /dev/null
	
	if [ $? == 0 ]; then
		$embedded_python -m cyclecloud_provider $@ 2>>$STDERR_FILE
		exit $?
	else
		groups $(whoami) | grep -q cyclecloud
		if [ $? != 0 ]; then
			echo $(whoami) must be added to the cyclecloud group.
			exit 1
		else 
			args=$@
			sg cyclecloud "/opt/cycle/jetpack/system/embedded/bin/python -m cyclecloud_provider $args 2>>$STDERR_FILE"
			exit $?
		fi
	fi
else
	# you'll need requests==2.5.1 installed.
	# > virtualenv ~/.venvs/azurecc
	# > source ~/venvs/azurecc/bin/activate
	# > pip install requests==2.5.1
	python2 -m cyclecloud_provider $@ 2>>$STDERR_FILE
	exit $?
fi