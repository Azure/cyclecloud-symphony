@echo off
::xcopy /S /Q /Y /F %2 %TEMP%\getReturnReq.input.json
:: copy second argument to tmp folder
set dirname=%~dp0
"%dirname%invoke_provider.bat" get_return_requests %*

set ret=%errorlevel%
exit /b %ret%