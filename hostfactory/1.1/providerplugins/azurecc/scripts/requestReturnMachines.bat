@echo off
::xcopy /S /Q /Y /F %2 %TEMP%\reqRetMach.input.json
:: copy second argument to tmp folder
set dirname=%~dp0
cmd /c "%dirname%invoke_provider.bat" terminate_machines %*

set ret=%errorlevel%
exit /b %ret%