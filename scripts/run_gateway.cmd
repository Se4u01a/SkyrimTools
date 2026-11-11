@echo off
rem skyrim-gateway, the MCP facade over houseCARL, pyghidra-mcp and SkyLink AI (gateway\README.md), for .mcp.json.
rem stdout is the MCP channel: nothing but the gateway may print to it.
rem The exe, first found wins:
rem   SKYRIM_GATEWAY_EXE                          explicit path
rem   %SKYRIM_TOOLS_REPO%\gateway\bin\skyrim-gateway.exe
rem   <this repo>\gateway\bin\skyrim-gateway.exe
rem   %SKYRIM_TOOLS_HOME%\gateway\skyrim-gateway.exe
rem None found and Go on PATH: build it into <repo>\gateway\bin (once; the first build downloads Go modules).
rem No Go either: fall back to houseCARL alone (scripts\run_housecarl.cmd), with a warning on stderr.
setlocal
if not defined SKYRIM_TOOLS_HOME set "SKYRIM_TOOLS_HOME=%LOCALAPPDATA%\SkyrimTools"
for %%I in ("%~dp0..") do set "HERE=%%~fI"
set "GW="
if defined SKYRIM_GATEWAY_EXE if exist "%SKYRIM_GATEWAY_EXE%" set "GW=%SKYRIM_GATEWAY_EXE%"
if not defined GW if defined SKYRIM_TOOLS_REPO if exist "%SKYRIM_TOOLS_REPO%\gateway\bin\skyrim-gateway.exe" set "GW=%SKYRIM_TOOLS_REPO%\gateway\bin\skyrim-gateway.exe"
if not defined GW if exist "%HERE%\gateway\bin\skyrim-gateway.exe" set "GW=%HERE%\gateway\bin\skyrim-gateway.exe"
if not defined GW if exist "%SKYRIM_TOOLS_HOME%\gateway\skyrim-gateway.exe" set "GW=%SKYRIM_TOOLS_HOME%\gateway\skyrim-gateway.exe"
if not defined GW call :build
if not defined GW goto fallback
"%GW%" %*
exit /b %errorlevel%

:build
where go >nul 2>nul || exit /b 1
set "SRC="
if defined SKYRIM_TOOLS_REPO if exist "%SKYRIM_TOOLS_REPO%\gateway\go.mod" set "SRC=%SKYRIM_TOOLS_REPO%\gateway"
if not defined SRC if exist "%HERE%\gateway\go.mod" set "SRC=%HERE%\gateway"
if not defined SRC exit /b 1
echo skyrim-gateway: building %SRC%\bin\skyrim-gateway.exe (first start only) ... 1>&2
pushd "%SRC%"
go build -trimpath -o bin\skyrim-gateway.exe .\cmd\skyrim-gateway 1>&2
popd
if exist "%SRC%\bin\skyrim-gateway.exe" set "GW=%SRC%\bin\skyrim-gateway.exe"
exit /b 0

:fallback
echo skyrim-gateway: no skyrim-gateway.exe and no Go to build it (https://go.dev/dl/, then restart the client). 1>&2
echo skyrim-gateway: falling back to houseCARL alone; Ghidra and SkyLink are unavailable in this session. 1>&2
call "%~dp0run_housecarl.cmd" %*
exit /b %errorlevel%
