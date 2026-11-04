@echo off
rem houseCARL MCP server, stdio, for the SkyrimTools plugin (.mcp.json). setup.ps1 installs it and writes the variables:
rem   SKYRIM_TOOLS_HOME    install root                 default %LOCALAPPDATA%\SkyrimTools
rem   HOUSECARL_EXE        the server                   default %SKYRIM_TOOLS_HOME%\housecarl\server\housecarl-mcp.exe
rem   HOUSECARL_DATA_DIR   its saved settings           default %SKYRIM_TOOLS_HOME%\housecarl-data
rem   SKYRIM_MO2_DIR       MO2 instance, the folder with ModOrganizer.ini; optional, houseCARL asks on first use
setlocal
if not defined SKYRIM_TOOLS_HOME set "SKYRIM_TOOLS_HOME=%LOCALAPPDATA%\SkyrimTools"
if not defined HOUSECARL_EXE set "HOUSECARL_EXE=%SKYRIM_TOOLS_HOME%\housecarl\server\housecarl-mcp.exe"
if not defined HOUSECARL_DATA_DIR set "HOUSECARL_DATA_DIR=%SKYRIM_TOOLS_HOME%\housecarl-data"
if defined SKYRIM_MO2_DIR set "HouseCarl__Mo2InstanceDir=%SKYRIM_MO2_DIR%"
if not exist "%HOUSECARL_EXE%" goto missing
if not exist "%HOUSECARL_DATA_DIR%" mkdir "%HOUSECARL_DATA_DIR%"
"%HOUSECARL_EXE%" %*
exit /b %errorlevel%

:missing
echo houseCARL not found at "%HOUSECARL_EXE%". Run setup.cmd in the SkyrimTools folder, then restart Claude Code. 1>&2
exit /b 1
