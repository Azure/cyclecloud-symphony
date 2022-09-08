::xcopy /S /Q /Y /F %2 %TEMP%\getReqStatus.input.json
:: copy second argument to tmp folder
set dirname=%~dp0
"%dirname%invoke_provider.bat" create_status %*

set ret=%errorlevel%
exit /b %ret%