@echo off
rem pyghidra-mcp (headless Ghidra over MCP) with the Ghidra and JDK of the RE workspace.
rem   run_ghidra_mcp.cmd                    stdio, for Claude Code (SkyrimTools .mcp.json)
rem   run_ghidra_mcp.cmd <extra args>       e.g. -t streamable-http -p 8765
rem The workspace (Ghidra, JDK, venv, projects, bins) stays in SKYRIM_RE_DIR.
rem Default %SKYRIM_TOOLS_HOME%\re or the repo root's re\ folder.
setlocal
if not defined SKYRIM_TOOLS_HOME set "SKYRIM_TOOLS_HOME=%LOCALAPPDATA%\SkyrimTools"
if not defined SKYRIM_RE_DIR set "SKYRIM_RE_DIR=%SKYRIM_TOOLS_HOME%\re"
set "RE=%SKYRIM_RE_DIR%\"
rem Fallback: a workspace in the repo root's re\ (gitignored). The path must be absolute and free of "..": Ghidra
rem rejects a project path with a "." element.
for %%I in ("%~dp0..\..\re") do set "REPO_RE=%%~fI"
if not exist "%RE%venv\Scripts\pyghidra-mcp.exe" if exist "%REPO_RE%\venv\Scripts\pyghidra-mcp.exe" (
    set "SKYRIM_RE_DIR=%REPO_RE%"
    set "RE=%REPO_RE%\"
)
if not exist "%RE%venv\Scripts\pyghidra-mcp.exe" goto missing
set "JAVA_HOME="
for /d %%D in ("%RE%jdk-*") do set "JAVA_HOME=%%~fD"
set "GHIDRA_INSTALL_DIR="
for /d %%D in ("%RE%ghidra_*_PUBLIC") do set "GHIDRA_INSTALL_DIR=%%~fD"
if not defined JAVA_HOME goto missing
if not defined GHIDRA_INSTALL_DIR goto missing
if not exist "%RE%projects" mkdir "%RE%projects"
set "PATH=%JAVA_HOME%\bin;%PATH%"
set "GDT_ARGS="
if exist "%RE%gdt\CommonLibSSE_SE_b93280e.gdt" (
    set GDT_ARGS=--gdt "%RE%gdt\CommonLibSSE_SE_b93280e.gdt"
)
cd /d "%RE%"
"%RE%venv\Scripts\pyghidra-mcp.exe" %GDT_ARGS% --project-path "%RE%projects" --project-name skyrim %*
exit /b %errorlevel%

:missing
echo The Ghidra workspace is incomplete in "%RE%" - venv, jdk-*, ghidra_*_PUBLIC. Run: setup.cmd -Ghidra 1>&2
exit /b 1
