::xcopy /S /Q /Y /F %2 %TEMP%\reqMach.input.json
:: copy second argument to tmp folder
set dirname=%~dp0
"%dirname%invoke_provider.bat" create_machines %*

set ret=%errorlevel%
exit /b %ret%