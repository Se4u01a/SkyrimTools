@echo off
rem pyghidra-mcp (headless Ghidra over MCP) with the Ghidra and JDK of the RE workspace.
rem   run_ghidra_mcp.cmd                    stdio, for Claude Code (SkyrimTools .mcp.json)
rem   run_ghidra_mcp.cmd <extra args>       e.g. -t streamable-http -p 8765
rem The workspace (Ghidra, JDK, venv, projects, bins) stays outside SkyrimTools: SKYRIM_RE_DIR, default D:\Games\Issen\re
if not defined SKYRIM_RE_DIR set "SKYRIM_RE_DIR=D:\Games\Issen\re"
set "RE=%SKYRIM_RE_DIR%\"
set "JAVA_HOME=%RE%jdk-25.0.5+8"
set "GHIDRA_INSTALL_DIR=%RE%ghidra_12.2_PUBLIC"
set "PATH=%JAVA_HOME%\bin;%PATH%"
cd /d "%RE%"
"%RE%venv\Scripts\pyghidra-mcp.exe" --project-path "%RE%projects" --project-name skyrim %*
