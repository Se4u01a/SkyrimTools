@echo off
rem SkyLink AI MCP server, stdio, for the SkyrimTools plugin (.mcp.json). Installed by setup.cmd -SkyLink:
rem   SKYRIM_TOOLS_HOME   install root          default %LOCALAPPDATA%\SkyrimTools
rem   SKYLINK_EXE         the server            default %SKYRIM_TOOLS_HOME%\skylink\server\SkyrimMCP.exe
rem The server starts without the game; its tools answer only while Skyrim runs through SKSE with the
rem "SkyLink AI" mod (SKSE\Plugins\SkyrimMCPPlugin.dll, pipe \.\pipe\SkyrimMCP) enabled in MO2.
setlocal
if not defined SKYRIM_TOOLS_HOME set "SKYRIM_TOOLS_HOME=%LOCALAPPDATA%\SkyrimTools"
if not defined SKYLINK_EXE set "SKYLINK_EXE=%SKYRIM_TOOLS_HOME%\skylink\server\SkyrimMCP.exe"
if not exist "%SKYLINK_EXE%" if exist "%LOCALAPPDATA%\SkyrimTools\skylink\server\SkyrimMCP.exe" (
    set "SKYLINK_EXE=%LOCALAPPDATA%\SkyrimTools\skylink\server\SkyrimMCP.exe"
)
if not exist "%SKYLINK_EXE%" goto missing
"%SKYLINK_EXE%" %*
exit /b %errorlevel%

:missing
echo SkyLink AI not found at "%SKYLINK_EXE%". Optional: run setup.cmd -SkyLink in the SkyrimTools folder, then restart the client. 1>&2
exit /b 1
