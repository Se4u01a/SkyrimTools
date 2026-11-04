@echo off
rem pyghidra-mcp (headless Ghidra over MCP) with the Ghidra and JDK of the RE workspace.
rem   run_ghidra_mcp.cmd                    stdio, for Claude Code (SkyrimTools .mcp.json)
rem   run_ghidra_mcp.cmd <extra args>       e.g. -t streamable-http -p 8765
rem The workspace (Ghidra, JDK, venv, projects, bins) stays outside the repo. setup.ps1 -Ghidra builds it and sets
rem SKYRIM_RE_DIR; default %SKYRIM_TOOLS_HOME%\re, SKYRIM_TOOLS_HOME default %LOCALAPPDATA%\SkyrimTools.
setlocal
if not defined SKYRIM_TOOLS_HOME set "SKYRIM_TOOLS_HOME=%LOCALAPPDATA%\SkyrimTools"
if not defined SKYRIM_RE_DIR set "SKYRIM_RE_DIR=%SKYRIM_TOOLS_HOME%\re"
set "RE=%SKYRIM_RE_DIR%\"
if not exist "%RE%venv\Scripts\pyghidra-mcp.exe" goto missing
set "JAVA_HOME="
for /d %%D in ("%RE%jdk-*") do set "JAVA_HOME=%%~fD"
set "GHIDRA_INSTALL_DIR="
for /d %%D in ("%RE%ghidra_*_PUBLIC") do set "GHIDRA_INSTALL_DIR=%%~fD"
if not defined JAVA_HOME goto missing
if not defined GHIDRA_INSTALL_DIR goto missing
if not exist "%RE%projects" mkdir "%RE%projects"
set "PATH=%JAVA_HOME%\bin;%PATH%"
cd /d "%RE%"
"%RE%venv\Scripts\pyghidra-mcp.exe" --project-path "%RE%projects" --project-name skyrim %*
exit /b %errorlevel%

:missing
echo The Ghidra workspace is incomplete in "%RE%" - venv, jdk-*, ghidra_*_PUBLIC. Run: setup.cmd -Ghidra 1>&2
exit /b 1
