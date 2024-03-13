#!/bin/bash
if [[ ! -d $EGO_TOP ]] ; then
     EGO_TOP="/opt/ibm/spectrumcomputing"  
     mkdir -p $EGO_TOP
     echo $EGO_TOP
fi 
# In Symphony 7.2 and earlier: HF_TOP=$EGO_TOP/eservice/hostfactory
if [[ ! -d $HF_TOP ]] ; then
     HF_TOP="$EGO_TOP/hostfactory"  
     mkdir -p $HF_TOP
fi 

if [[  -z $HF_CONFDIR ]] ; then
     HF_CONFDIR="$EGO_TOP/hostfactory/conf"  
fi 

if [[  -z $HF_WORKDIR ]] ; then
     HF_WORKDIR="$EGO_TOP/hostfactory/work"  
fi 

if [[  -z $HF_LOGDIR ]] ; then
     HF_LOGDIR="$EGO_TOP/hostfactory/log"  
fi 

if [[ -z $HF_VERSION ]] ; then
     HF_VERSION="1.2"
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
            \"name\": \"$(jetpack config cyclecloud.cluster.name)\"
        },
        \"config\": {
            \"username\": \"$(jetpack config cyclecloud.config.username)\",
            \"password\": \"$(jetpack config cyclecloud.config.password)\",
            \"web_server\": \"$(jetpack config cyclecloud.config.web_server)\"
        }
      }
   }"
   if [ ! -e $azureccProviderConfPath ]
   then
      mkdir -p  $azureccProviderConfPath
   fi
   echo "$azureccprov_config_json" > "$azureccProviderConfPath/azureccprov_config.json"

   azureccprov_template_json='{"message" : "Get available templates success.",
    "templates" : [
    {
        "templateId" : "executestandardf2sv2",
        "maxNumber" : 10,
        "attributes" : {
            "nram" : [ "Numeric", "1024" ],
            "ncpus" : [ "Numeric", "1" ],
            "ncores" : [ "Numeric", "1" ],
            "type" : [ "String", "X86_64" ],
            "nodearray" : [ "String", "execute" ],
            "machinetypefull" : ["String", "Standard_F2s_v2"]
        }
    } ]
    }'
    if [ ! -e $azureccProviderConfPath ]
    then
      mkdir -p  $azureccProviderConfPath
    fi
    echo "$azureccprov_template_json" > "$azureccProviderConfPath/azureccprov_templates.json"
    #as this will be updated by HF we need to change user to egoadmin
    chown egoadmin:egoadmin $azureccProviderConfPath/azureccprov_templates.json

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
function Install-Python-Packages
{
    echo "Installing python packages..."
    PKG_NAME=$( jetpack config symphony.pkg_plugin )
    cd /tmp
    pluginSrcPath=$HF_TOP/$HF_VERSION/providerplugins/azurecc
    mkdir -p $pluginSrcPath
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
#check for command line argument for generate_config
if [ $# -eq 1 ]; then
    if [ $1 == "generate_config" ]; then
        Generate-Provider-Config
        Generate-Provider-Plugins-Config
        Update-Requestors-Config
    else
        echo "Argument $1 is invalid"
    fi
else
    Install-Python-Packages
fi