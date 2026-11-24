@echo off
rem SkyLink AI MCP server, stdio, for the SkyrimTools plugin (.mcp.json). Installed by setup.cmd -SkyLink:
rem   SKYRIM_TOOLS_HOME   install root          default %LOCALAPPDATA%\SkyrimTools
rem   SKYLINK_EXE         server override       default %SKYRIM_TOOLS_HOME%\skylink\server\SkyrimMCP.dll
rem --check-install [root] [server override] prints the resolved path without starting the server.
rem Live tools need Skyrim running through SKSE with the "SkyLink AI" mod enabled in MO2.
setlocal
if "%~1"=="--check-install" if not "%~2"=="" set "SKYRIM_TOOLS_HOME=%~2"
if "%~1"=="--check-install" if not "%~3"=="" set "SKYLINK_EXE=%~3"
if not defined SKYRIM_TOOLS_HOME set "SKYRIM_TOOLS_HOME=%LOCALAPPDATA%\SkyrimTools"
set "SERVER="
if defined SKYLINK_EXE if exist "%SKYLINK_EXE%" set "SERVER=%SKYLINK_EXE%"
for %%D in ("%SKYRIM_TOOLS_HOME%" "%LOCALAPPDATA%\SkyrimTools") do (
    if not defined SERVER if exist "%%~fD\skylink\server\SkyrimMCP.dll" set "SERVER=%%~fD\skylink\server\SkyrimMCP.dll"
    if not defined SERVER if exist "%%~fD\skylink\server\SkyrimMCP.exe" set "SERVER=%%~fD\skylink\server\SkyrimMCP.exe"
)
if not defined SERVER goto missing
if "%~1"=="--check-install" (
    echo("%SERVER%"
    exit /b 0
)
for %%I in ("%SERVER%") do if /i "%%~xI"==".dll" goto assembly
"%SERVER%" %*
exit /b %errorlevel%

:assembly
set "DOTNET=dotnet.exe"
if exist "%USERPROFILE%\.dotnet\dotnet.exe" set "DOTNET=%USERPROFILE%\.dotnet\dotnet.exe"
if exist "%ProgramFiles%\dotnet\dotnet.exe" set "DOTNET=%ProgramFiles%\dotnet\dotnet.exe"
"%DOTNET%" "%SERVER%" %*
exit /b %errorlevel%

:missing
if "%~1"=="--check-install" exit /b 1
echo SkyLink AI not found under "%SKYRIM_TOOLS_HOME%\skylink\server". Optional: run setup.cmd -SkyLink, then restart the client. 1>&2
exit /b 1
