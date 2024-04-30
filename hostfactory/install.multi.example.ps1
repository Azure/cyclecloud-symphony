Param(
    [parameter(HelpMessage="Installs the azurecc HostFactory Provider plugin for Symphony 7.3 and later.")]
    [switch]$help = $false,
    [parameter(HelpMessage="Cyclecloud Cluster Name.")]
    [String]$cluster = "symphony-test",
    [parameter(HelpMessage="Cyclecloud Cluster Name 2.")]
    [String]$cluster2 = "symphony-test2",
    [parameter(HelpMessage="Cyclecloud URL (default: https://127.0.0.1:9443).")]
    [String]$cc_url = "https://127.0.0.1:9443",
    [parameter(HelpMessage="Cyclecloud Username")]
    [String]$cc_user = "cyclecloud_access",
    [parameter(HelpMessage="Cyclecloud Password")]
    [String]$cc_pass = "test",
    [parameter(HelpMessage="Fake installation")]
    [switch]$dryrun = $false,
    [parameter(HelpMessage="Install provider")]
    [switch]$install_pro=$false
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

$pluginSrcPath1 = "$HF_TOP\\$HF_VERSION\\providerplugins\\azurecc1"
$pluginSrcPath2 = "$HF_TOP\\$HF_VERSION\\providerplugins\\azurecc2"
$providerConfPath = "$HF_TOP\\conf\\providers"
$azureccProviderConfPath1 = "$HF_TOP\\conf\\providers\\azurecc1"
$azureccProviderConfPath2 = "$HF_TOP\\conf\\providers\\azurecc2"
$providerPluginsConfPath = "$HF_TOP\\conf\\providerplugins"
$requestorConfPath = "$HF_TOP\\conf\\requestors"

$venv_path1 = "$pluginSrcPath1\\.venv\\azurecc1"
$venv_path2 = "$pluginSrcPath2\\.venv\\azurecc2"


function Generate-Provider-Config
{
    Write-Log INFO "Generating default azurecc1 conf files"
    if (!(Test-Path -Path "$azureccProviderConfPath1")) {
        New-Item -Type Directory -Path "$azureccProviderConfPath1"
    }
    Write-Log INFO "Generating default azurecc2 conf files"
    if (!(Test-Path -Path "$azureccProviderConfPath2")) {
        New-Item -Type Directory -Path "$azureccProviderConfPath2"
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
            "name": "azurecc1",
            "enabled": 1,
            "plugin": "azurecc1",
            "confPath": "${HF_CONFDIR}\\providers\\azurecc1",
            "workPath": "${HF_WORKDIR}\\providers\\azurecc1",
            "logPath": "${HF_LOGDIR}\\"
        },
        {
            "name": "azurecc2",
            "enabled": 1,
            "plugin": "azurecc2",
            "confPath": "${HF_CONFDIR}\\providers\\azurecc2",
            "workPath": "${HF_WORKDIR}\\providers\\azurecc2",
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
"@ | Set-Content "$azureccProviderConfPath1\\azurecc1prov_config.json"
@"
{
    `"log_level`": `"info`",
    `"cyclecloud`": {
        `"cluster`": {
            `"name`": `"$cluster2`"
        },
        `"config`": {
            `"username`": `"$cc_user`",
            `"password`": `"$cc_pass`",
            `"web_server`": `"$cc_url`"
        }
    }
}
"@ | Set-Content "$azureccProviderConfPath2\\azurecc2prov_config.json"

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
'@ | Set-Content "$azureccProviderConfPath1\\azurecc1prov_templates.json"
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
'@ | Set-Content "$azureccProviderConfPath2\\azurecc2prov_templates.json"

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
            "name": "azurecc1",
            "enabled": 1,
            "scriptPath": "${HF_TOP}\\${HF_VERSION}\\providerplugins\\azurecc1\\scripts\\"
        },
        {
            "name": "azurecc2",
            "enabled": 1,
            "scriptPath": "${HF_TOP}\\${HF_VERSION}\\providerplugins\\azurecc2\\scripts\\"
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
            "providers": ["azurecc1"],
            "requestMode": "POLL",
            "resourceRequestParameters": {
                "hostSelectionPolicy": "rank",
                "typicalHostRetentionTimeMinutes": 60,
                "fulfillmentType": "partial"
            }
        },{
            "name": "symAinst2",
            "enabled": 1,
            "plugin": "symA",
            "confPath": "${HF_CONFDIR}\\requestors\\symAinst\\",
            "workPath": "${HF_WORKDIR}\\requestors\\symAinst\\",
            "logPath": "${HF_LOGDIR}\\",
            "providers": ["azurecc2"],
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
function Replace-Line {
    param(
        [Parameter(Mandatory=$true)]
        [string]$filePath,

        [Parameter(Mandatory=$true)]
        [string]$lineToReplace,

        [Parameter(Mandatory=$true)]
        [string]$newLine
    )

    # Read all lines from the file
    $content = Get-Content $filePath

    # Replace the line
    for ($i = 0; $i -lt $content.Length; $i++) {
        if ($content[$i] -eq $lineToReplace) {
            $content[$i] = $newLine
        }
    }

    # Write the content back to the file
    $content | Out-File $filePath -Encoding ASCII
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
    if (!(Test-Path -Path "$pluginSrcPath1")) {
        New-Item -Type Directory -Path "$pluginSrcPath1"
    }
    if (!(Test-Path -Path "$pluginSrcPath2")) {
        New-Item -Type Directory -Path "$pluginSrcPath2"
    }
    Write-Log INFO "Copying default azurecc provider plugin files"
    Copy-Item .\\host_provider\\* -Destination "$pluginSrcPath1" -Recurse -Force
    Copy-Item .\\host_provider\\* -Destination "$pluginSrcPath2" -Recurse -Force

    Write-Log INFO "Updating invoke provider file for azurecc1"
    Replace-Line -filePath "$pluginSrcPath1\\scripts\\invoke_provider.bat" -lineToReplace "set PRO_NAME=azurecc" -newLine "set PRO_NAME=azurecc1"
    
    Write-Log INFO "Updating invoke provider file for azurecc2"
    Replace-Line -filePath "$pluginSrcPath2\\scripts\\invoke_provider.bat" -lineToReplace "set PRO_NAME=azurecc" -newLine "set PRO_NAME=azurecc2"

}

function Install-Python-Packages {
    Write-Log INFO "Installing Python virtualenv at $venv_path1"
    python -m venv $venv_path1
    . $venv_path1\Scripts\Activate.ps1 
    Get-ChildItem ..\packages\ | 
      ForEach-Object{
         pip install $_.FullName
      }
      Write-Log INFO "Installing Python virtualenv at $venv_path2"
      python -m venv $venv_path2
    . $venv_path2\Scripts\Activate.ps1 
    Get-ChildItem ..\packages\ | 
      ForEach-Object{
         pip install $_.FullName
      }
}
if ($install_pro -eq $true){
    Install-Provider
}
Install-Python-Packages