set PRO_LOG_DIR=%HF_LOGDIR%
set PRO_CONF_DIR=%HF_CONFDIR%\providers\azurecc
set PRO_DATA_DIR=%HF_WORKDIR%
set STDERR_FILE=%HF_LOGDIR%\azurecc_invoke.err
set dirname=%~dp0

set PYTHONPATH=%PYTHONPATH%;%dirname%\src

set embedded_python=C:\cycle\jetpack\system\embedded\python\python.exe
SET > %TEMP%\invoke.log
echo >>  %TEMP%\invoke.log
echo "%embedded_python% -m cyclecloud_provider %* " >>  %TEMP%\invoke.log
%embedded_python% -m cyclecloud_provider %* > %TEMP%\azurecc_invoke.out.log 2>%TEMP%\azurecc_invoke.err.log
type %TEMP%\azurecc_invoke.out.log 
exit /b 0