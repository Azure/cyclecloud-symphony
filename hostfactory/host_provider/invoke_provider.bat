@echo off
set PRO_NAME=azurecc
set PRO_LOG_DIR=%HF_LOGDIR%
set PRO_CONF_DIR=%HF_CONFDIR%\providers\%PRO_NAME%
set PRO_DATA_DIR=%HF_WORKDIR%
set STDERR_FILE=%HF_LOGDIR%\%PRO_NAME%_invoke.err
set dirname=%~dp0
if exist "%dirname%\..\.venv\" (
    call "%dirname%\..\.venv\%PRO_NAME%\Scripts\activate.bat"
    set embedded_python="%dirname%\..\.venv\%PRO_NAME%\Scripts\python.exe" 
) else (
    set embedded_python=C:\cycle\jetpack\system\embedded\python\python.exe
)
set PYTHONPATH=%PYTHONPATH%;%dirname%\src
SET > %TEMP%\invoke.log
echo >>  %TEMP%\invoke.log
echo "%embedded_python% -m cyclecloud_provider %* " >>  %TEMP%\invoke.log
cmd /c "%embedded_python% -m cyclecloud_provider %*" > %TEMP%\%PRO_NAME%_invoke.out.log 2>%TEMP%\%PRO_NAME%.log
type %TEMP%\%PRO_NAME%_invoke.out.log 
exit /b 0