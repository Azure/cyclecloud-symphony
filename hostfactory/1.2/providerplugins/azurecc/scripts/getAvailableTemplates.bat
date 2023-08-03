@echo off
SET > %TEMP%\TemplateEnv.log
echo %* >> %TEMP%\GetAvail.log
::robocopy "%2" "%TEMP%"\toto\

:: copy second argument to tmp folder
set dirname=%~dp0
echo "%dirname%\invoke_provider.bat templates %*" >> %TEMP%\GetAvail.log

:: REAL - use cmd /c to work around spaces in the path
cmd /c "%dirname%\invoke_provider.bat" templates %* > %TEMP%\GetAvail.out

type "%TEMP%\GetAvail.out"
exit /b 0
::set ret=%errorlevel%
::exit /b %ret%