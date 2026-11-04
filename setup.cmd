@echo off
rem SkyrimTools setup: double-click, or run with options, e.g. setup.cmd -Ghidra / setup.cmd -Uninstall (see setup.ps1).
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
set "RC=%errorlevel%"
if "%~1"=="" pause
exit /b %RC%
