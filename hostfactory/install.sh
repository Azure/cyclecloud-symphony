#!/bin/bash
if [[ ! -d $EGO_TOP ]] ; then
     export EGO_TOP="/opt/ibm/spectrumcomputing"  
     mkdir -p $EGO_TOP
     echo $EGO_TOP
fi 
# In Symphony 7.2 and earlier: HF_TOP=$EGO_TOP/eservice/hostfactory
if [[ ! -d $HF_TOP ]] ; then
     export HF_TOP="$EGO_TOP/hostfactory"  
     mkdir -p $HF_TOP
fi 

if [[  -z $HF_CONFDIR ]] ; then
     export HF_CONFDIR="$EGO_TOP/hostfactory/conf"  
fi 

if [[  -z $HF_WORKDIR ]] ; then
     export HF_WORKDIR="$EGO_TOP/hostfactory/work"  
fi 

if [[  -z $HF_LOGDIR ]] ; then
     export HF_LOGDIR="$EGO_TOP/hostfactory/log"  
fi 

if [[ -z $HF_VERSION ]] ; then
     export HF_VERSION="1.1"
fi 

pluginSrcPath=$HF_TOP/$HF_VERSION/providerplugins/azurecc
providerConfPath=$HF_TOP/conf/providers
azureccProviderConfPath=$HF_TOP/conf/providers/azurecc/conf/
providerPluginsConfPath=$HF_TOP/conf/providerplugins
requestorConfPath=$HF_TOP/conf/requestors

venv_path=$pluginSrcPath/venv

function Generate-Provider-Config {
    echo "Generating default azurecc conf files"
    hostProvidersJson="{ 
    \"version\": 2, 
    \"providers\":[
	{
            \"name\": \"azurecc\",
            \"enabled\": 1,
            \"plugin\": \"azurecc\",
            \"confPath\": \"${HF_CONFDIR}/providers/azurecc/conf\",
            \"workPath\": \"${HF_WORKDIR}/providers/azurecc\",
            \"logPath\": \"${HF_LOGDIR}/\"
        }
      ]
    }"
    if [ ! -e $providerConfPath ]
    then
       mkdir -p  $providerConfPath
    fi
    echo "$hostProvidersJson" > "$providerConfPath/hostProviders.json"

    azureccprov_config_json="{
    \"log_level\": \"debug\",
    \"cyclecloud\": {
        \"cluster\": {
            \"name\": \"$cluster\"
        },
        \"config\": {
            \"username\": \"$username\",
            \"password\": \"$password\",
            \"web_server\": \"$web_server\"
        }
      }
   }"
   if [ ! -e $azureccProviderConfPath ]
   then
      mkdir -p  $azureccProviderConfPath
   fi
   echo "$azureccprov_config_json" > "$azureccProviderConfPath/azureccprov_config.json"


}

function Generate-Provider-Plugins-Config
{
    echo "Generating default host provider plugins conf file"
    hostProviderPluginsJson="{
    \"version\": 2,
    \"providerplugins\":[
        {
            \"name\": \"azurecc\",
            \"enabled\": 1,
            \"scriptPath\": \"$HF_TOP/$HF_VERSION/providerplugins/azurecc/scripts\"
        }
    ]
    }"
    if [ ! -e $providerPluginsConfPath ]
    then
      mkdir -p  $providerPluginsConfPath
    fi
    echo "$hostProviderPluginsJson" > "$providerPluginsConfPath/hostProviderPlugins.json"

}

function Update-Requestors-Config
{
    if [ ! -e $requestorConfPath ]
    then
      mkdir -p  $requestorConfPath
    fi
    hostRequestorsJson="{
    \"version\": 2,
    \"requestors\":[
        {
            \"name\": \"symAinst\",
            \"enabled\": 1,
            \"plugin\": \"symA\",
            \"confPath\": \"${HF_CONFDIR}/requestors/symAinst/\",
            \"workPath\": \"${HF_WORKDIR}/requestors/symAinst/\",
            \"logPath\": \"${HF_LOGDIR}/\",
            \"providers\": [\"azurecc\"],
            \"requestMode\": \"POLL\",
            \"resourceRequestParameters\": {
                \"hostSelectionPolicy\": \"rank\",
                \"typicalHostRetentionTimeMinutes\": 60,
                \"fulfillmentType\": \"partial\"
            }
        },
        {   
            \"name\": \"admin\",
            \"enabled\": 1,
            \"providers\": [\"awsinst\",\"azureinst\",\"ibmcloudinst\"],
            \"requestMode\": \"REST_MANUAL\",
            \"resourceRequestParameters\": {
                \"hostSelectionPolicy\": \"rank\",
                \"typicalHostRetentionTimeMinutes\": 43200,
                \"fulfillmentType\": \"partial\"
            }
        }
    ]
}"
echo "$hostRequestorsJson" > "$requestorConfPath/hostRequestors.json"

}

function UpdateSymAReturnPolicy
{
    jq '.host_return_policy = "immediate"' "$requestorConfPath/symAinst/symAinstreq_config.json" > temp.json && mv temp.json "$requestorConfPath/symAinst/symAinstreq_config.json"

}
function Install-Python-Packages
{
    echo "Installing python packages..."
    PKG_NAME=$( jetpack config symphony.pkg_plugin )
    cd /tmp
    mkdir -p $pluginSrcPath/scripts
    cp -r /tmp/hostfactory/host_provider/* $pluginSrcPath/scripts
    chmod a+x $pluginSrcPath/scripts/*.sh # Ensure scripts are executable
    
    VENV=$pluginSrcPath/venv
    # remove jetpack python from PATH so default python3 is used.
    export PATH=$(echo $PATH | sed -e 's/\/opt\/cycle\/jetpack\/system\/embedded\/bin://g' | sed -e 's/:\/opt\/cycle\/jetpack\/system\/embedded\/bin//g')
    export PATH=$PATH:/root/bin:/usr/bin

    python3 -m virtualenv --version 2>&1 > /dev/null
    if [ $? != 0 ]; then
        python3 -m pip install virtualenv || exit 1
    fi
    set -e
    echo "venv path"
    echo $VENV
    python3 -m virtualenv $VENV
    source $VENV/bin/activate
    pip install --upgrade packages/*
    if [ -f $PKG_NAME ]; then
        rm -f $PKG_NAME
        rm -rf packages
        rm -rf hostfactory
    fi
    echo "Python plugin virtualenv created at $VENV"
}

function Generate-Template
{
    cd $pluginSrcPath/scripts
    echo "In scripts dir at $pluginSrcPath/scripts"
    output=$(./generateWeightedTemplates.sh)
    echo $output
    echo $output > $azureccProviderConfPath/azureccprov_templates.json
    # as this will be updated by HF we need to change user to egoadmin
    chown egoadmin:egoadmin $azureccProviderConfPath/azureccprov_templates.json
}
# check for command line argument for generate_config
if [ $# -gt 1 ]; then
    if [ $1 == "generate_config" ]; then
        echo "Parsing parameters for generating config files"
        if [ $2 == "--cluster" ]; then
            cluster=$3
        else
            echo "Cluster name is required"
        fi
        if [ $4 == "--username" ]; then
            username=$5
        else
            echo "Username is required"
        fi
        if [ $6 == "--password" ]; then
            password=$7
        else
            echo "Password is required"
        fi
        if [ $8 == "--web_server" ]; then
            web_server=$9
        else
            echo "Web server is required"
        fi
        Generate-Provider-Config
        Generate-Provider-Plugins-Config
        Update-Requestors-Config
        UpdateSymAReturnPolicy
        Install-Python-Packages
        Generate-Template
    else
        echo "Argument $1 is invalid"
    fi

else
    Install-Python-Packages
fi