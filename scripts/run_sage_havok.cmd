@echo off
rem SageHavokEditor - Visual editor for Skyrim Havok behaviors (.hkx), state machines, and animations.
rem Upstream: https://github.com/TheSageLenny/Sage-Havok-Editor
setlocal
set "SAGE_DIR=%~dp0..\tools\SageHavokEditor"
if not exist "%SAGE_DIR%\SageHavokEditor.exe" (
    echo SageHavokEditor not found in "%SAGE_DIR%". Run setup or check tools\SageHavokEditor. 1>&2
    exit /b 1
)
start "" "%SAGE_DIR%\SageHavokEditor.exe" %*
exit /b 0
