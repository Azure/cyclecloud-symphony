Param(
    [parameter(HelpMessage="Installs the azurecc HostFactory Provider plugin for Symphony 7.3 and later.")]
    [switch]$help = $false,
    [parameter(HelpMessage="Cyclecloud Cluster Name.")]
    [String]$cluster = "symphony-test",
    [parameter(HelpMessage="Cyclecloud URL (default: https://127.0.0.1:9443).")]
    [String]$cc_url = "https://127.0.0.1:9443",
    [parameter(HelpMessage="Cyclecloud Username")]
    [String]$cc_user = "cyclecloud_access",
    [parameter(HelpMessage="Cyclecloud Password")]
    [String]$cc_pass = "DGn298QMq.n0GC",
    [parameter(HelpMessage="Fake installation")]
    [switch]$dryrun = $false

)


function Write-Log
{
    $level = $args[0].ToUpper()
    $message = $args[1..($args.Length)]
    $date = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $output = "$date [$level] $message"

    if ($level -eq "ERROR")
    {
        Write-Host -ForegroundColor Red $output
    }
    elseif (($level -eq "WARNING") -Or ($level -eq "WARN"))
    {
        Write-Host -ForegroundColor Magenta $output
    }
    elseif ($level -eq "INFO")
    {
        Write-Host -ForegroundColor Green $output
    }
    else
    {
        Write-Host $output
    }
}

$startTime = $(get-date -f yyyyMMddhhmm)

# Set vars
$EGO_TOP = $env:EGO_TOP
if (-not $EGO_TOP)
{
    $EGO_TOP = "C:\\Progra~1\\IBM\\SpectrumComputing\\kernel"
}
########################
# DRY-RUN
if ($dryrun -eq $true) {
    Write-Log WARN "Dry-Run installation test"
    $FakeEgoTop = ".\\Temp\\kernel"
    if (Test-Path -Path $FakeEgoTop) {
        Remove-Item -Recurse -Force $FakeEgoTop
    }
    New-Item -Type Directory -Path $FakeEgoTop
    $EGO_TOP = $FakeEgoTop    
}
########################

$HF_TOP = $env:HF_TOP
if (-not $HF_TOP)
{
    $HF_TOP = "$EGO_TOP\\..\\hostfactory"
}

$HF_VERSION = $env:HF_VERSION
if (-not $HF_VERSION)
{
    $HF_VERSION = "1.2"
}

$pluginSrcPath = "$HF_TOP\\$HF_VERSION\\providerplugins\\azurecc"
$providerConfPath = "$HF_TOP\\conf\\providers"
$azureccProviderConfPath = "$HF_TOP\\conf\\providers\\azurecc\\conf"
$providerPluginsConfPath = "$HF_TOP\\conf\\providerplugins"
$requestorConfPath = "$HF_TOP\\conf\\requestors"

$venv_path = "$pluginSrcPath\\.venv\\azurecc"


function Generate-Provider-Config
{
    Write-Log INFO "Generating default azurecc conf files"
    if (!(Test-Path -Path "$azureccProviderConfPath")) {
        New-Item -Type Directory -Path "$azureccProviderConfPath"
    }

# TODO: We should load the JSON, Insert our conf and spit out the updated JSON    
if (Test-Path -Path "$providerConfPath\\hostProviders.json") {
    Copy-Item "$providerConfPath\\hostProviders.json" -Destination "$providerConfPath\\hostProviders.$startTime.json"
}
@'
{
    "version": 2,
    "providers":[
	{
            "name": "azurecc",
            "enabled": 1,
            "plugin": "azurecc",
            "confPath": "${HF_CONFDIR}\\providers\\azurecc",
            "workPath": "${HF_WORKDIR}\\providers\\azurecc",
            "logPath": "${HF_LOGDIR}\\"
        }
    ]
}
'@  | Set-Content "$providerConfPath\\hostProviders.json"

@"
{
    `"log_level`": `"info`",
    `"cyclecloud`": {
        `"cluster`": {
            `"name`": `"$cluster`"
        },
        `"config`": {
            `"username`": `"$cc_user`",
            `"password`": `"$cc_pass`",
            `"web_server`": `"$cc_url`"
        }
    }
}
"@ | Set-Content "$azureccProviderConfPath\\azureccprov_config.json"

@'
{
    "message" : "Get available templates success.",
    "templates" : [
    {
        "templateId" : "executestandardf2sv2",
        "maxNumber" : 10,
        "attributes" : {
            "nram" : [ "Numeric", "1024" ],
            "ncpus" : [ "Numeric", "1" ],
            "ncores" : [ "Numeric", "1" ],
            "type" : [ "String", "X86_64" ]
        }
    } ]
}
'@ | Set-Content "$azureccProviderConfPath\\azureccprov_templates.json"

}

function Generate-Provider-Plugins-Config
{
    
    Write-Log INFO "Generating default host provider plugins conf file"
    if (!(Test-Path -Path $providerPluginsConfPath)) {
        New-Item -Type Directory -Path "$providerPluginsConfPath"
    }

# TODO: We should load the JSON, Insert our conf and spit out the updated JSON
if (Test-Path -Path "$providerPluginsConfPath\\hostProviderPlugins.json") {
    Copy-Item "$providerPluginsConfPath\\hostProviderPlugins.json" -Destination "$providerPluginsConfPath\\hostProviderPlugins.$startTime.json"
}
@'
{
    "version": 2,
    "providerplugins":[
        {
            "name": "azurecc",
            "enabled": 1,
            "scriptPath": "${HF_TOP}\\${HF_VERSION}\\providerplugins\\azurecc\\scripts\\"
        }
    ]
}
'@ | Set-Content "$providerPluginsConfPath\\hostProviderPlugins.json"
}


function Update-Requestors-Config
{
    
    if (!(Test-Path -Path $requestorConfPath)) {
        New-Item -Type Directory -Path "$requestorConfPath"
    }

# TODO: We should load the JSON, Insert our conf and spit out the updated JSON
if (Test-Path -Path "$requestorConfPath\\hostRequestors.json") {
    Copy-Item "$requestorConfPath\\hostRequestors.json" -Destination "$requestorConfPath\\hostRequestors.$startTime.json"
} else {
    Write-Log WARNING "Expected default host requestors conf file!   Will generate, but this may indicate a failure..."
@'
{
    "version": 2,
    "requestors":[
        {
            "name": "symAinst",
            "enabled": 1,
            "plugin": "symA",
            "confPath": "${HF_CONFDIR}\\requestors\\symAinst\\",
            "workPath": "${HF_WORKDIR}\\requestors\\symAinst\\",
            "logPath": "${HF_LOGDIR}\\",
            "providers": ["azurecc"],
            "requestMode": "POLL",
            "resourceRequestParameters": {
                "hostSelectionPolicy": "rank",
                "typicalHostRetentionTimeMinutes": 60,
                "fulfillmentType": "partial"
            }
        },
        {   
            "name": "admin",
            "enabled": 1,
            "providers": ["awsinst","azureinst","ibmcloudinst"],
            "requestMode": "REST_MANUAL",
            "resourceRequestParameters": {
                "hostSelectionPolicy": "rank",
                "typicalHostRetentionTimeMinutes": 43200,
                "fulfillmentType": "partial"
            }
        }
    ]
}
'@ | Set-Content "$requestorConfPath\\hostRequestors.json"
    }

    Write-Log INFO "Replacing azureinst provider with azurecc provider"
    ((Get-Content -path "$requestorConfPath\\hostRequestors.json" -Raw) -replace 'azureinst','azurecc') | Set-Content -Path "$requestorConfPath\\hostRequestors.json"

}

function Install-Provider
{
    Generate-Provider-Config
    Generate-Provider-Plugins-Config
    Update-Requestors-Config

    Write-Log INFO "Copying default azurecc provider files"
    if (!(Test-Path -Path "$HF_TOP\\$HF_VERSION\\providerplugins")) {
        New-Item -Type Directory -Path "$HF_TOP\\$HF_VERSION\\providerplugins"
    }
    if (!(Test-Path -Path "$HF_TOP\\$HF_VERSION\\providerplugins")) {
        New-Item -Type Directory -Path "$HF_TOP\\$HF_VERSION\\providerplugins"
    }
    Copy-Item .\\$HF_VERSION\\providerplugins\\azurecc -Destination "$HF_TOP\\$HF_VERSION\\providerplugins\\" -Recurse -Force

}

function Install-Python-Packages {
    Write-Log INFO "Installing Python virtualenv at $venv_path"
    python -m venv $venv_path
    . $venv_path\Scripts\Activate.ps1 
    Get-ChildItem ..\packages\ | 
      ForEach-Object{
         pip install $_.FullName
      }
}
Install-Provider
Install-Python-Packages