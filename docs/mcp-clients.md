# MCP servers in any client

`.mcp.json` in the repo root is the **Claude Code** form and is wired automatically by `setup.ps1`. It cannot be copied
to other clients: `${CLAUDE_PLUGIN_ROOT}` is a Claude Code variable. Every other client needs the same three stdio
servers with a literal launcher path (the third, `skylink`, is optional).

`scripts\agents\connect.ps1 -Client <name>` prints the exact block for this machine, filled in and escaped — prefer it
over hand-editing the snippets below.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\agents\connect.ps1 -Client codex   # or vscode|cursor|windsurf|cline|gemini|opencode|json
```

## What the servers are

All three are stdio MCP servers started by a `.cmd` wrapper that reads the `SKYRIM_*` environment variables, creates what it
can and fails with a readable message:

| Server | Launcher | Needs |
|---|---|---|
| `housecarl` | `<REPO>\scripts\run_housecarl.cmd` | `%HOUSECARL_EXE%` (default `%SKYRIM_TOOLS_HOME%\housecarl\server\housecarl-mcp.exe`) and .NET Runtime 10 x64 |
| `pyghidra-mcp` | `<REPO>\scripts\re\run_ghidra_mcp.cmd` | `%SKYRIM_RE_DIR%` with `venv\Scripts\pyghidra-mcp.exe`, `jdk-*`, `ghidra_*_PUBLIC` (`setup.cmd -Ghidra`) |
| `skylink` | `<REPO>\scripts\run_skylink.cmd` | optional: `%SKYLINK_EXE%` (default `%SKYRIM_TOOLS_HOME%\skylink\server\SkyrimMCP.exe`, `setup.cmd -SkyLink`); it starts without the game, but its tools answer only while Skyrim runs through SKSE with the `SkyLink AI` mod enabled |

Start the wrapper in a terminal first when something is wrong — it prints the reason (missing exe, missing runtime,
incomplete Ghidra workspace) and exits 1.

Because the wrappers are `.cmd`, every client must start them through `cmd.exe /c`. On a portable setup where
`SKYRIM_TOOLS_REPO` is set, `%SKYRIM_TOOLS_REPO%\scripts\run_housecarl.cmd` also works (cmd expands it); the absolute
path is the safe default and is what `connect.ps1` prints.

Give the JVM server a generous startup timeout: 20–60 s is normal, and the first analysis of `SkyrimSE.exe` takes tens
of minutes (then it is cached in the Ghidra project).

## Claude Code

Already done by `setup.cmd` (project `.mcp.json` + plugin registration). In-session: `/mcp`. To add it by hand:

```powershell
claude mcp add --transport stdio housecarl -- cmd.exe /c "<REPO>\scripts\run_housecarl.cmd"
claude mcp add --transport stdio pyghidra-mcp -- cmd.exe /c "<REPO>\scripts\re\run_ghidra_mcp.cmd"
claude mcp add --transport stdio skylink -- cmd.exe /c "<REPO>\scripts\run_skylink.cmd"
```

## Codex CLI / IDE (`~/.codex/config.toml`)

TOML literal strings (single quotes) keep the Windows backslashes readable:

```toml
[mcp_servers.housecarl]
command = "cmd.exe"
args = ["/c", '<REPO>\scripts\run_housecarl.cmd']
startup_timeout_sec = 120

[mcp_servers.pyghidra-mcp]
command = "cmd.exe"
args = ["/c", '<REPO>\scripts\re\run_ghidra_mcp.cmd']
startup_timeout_sec = 300

[mcp_servers.skylink]
command = "cmd.exe"
args = ["/c", '<REPO>\scripts\run_skylink.cmd']
startup_timeout_sec = 60
```

Codex reads `AGENTS.md` from the working directory upward, so opening this repo (or a mod project) picks the guide up
automatically. Skills are read from `~\.codex\skills\<name>\SKILL.md` — link them with `connect.ps1 -Client codex
-LinkSkills`.

## VS Code / GitHub Copilot (`.vscode/mcp.json`)

The repo ships this file; add the same block to another workspace by copying it.

```json
{
  "servers": {
    "housecarl": {
      "type": "stdio",
      "command": "cmd.exe",
      "args": ["/c", "<REPO>\\scripts\\run_housecarl.cmd"]
    },
    "pyghidra-mcp": {
      "type": "stdio",
      "command": "cmd.exe",
      "args": ["/c", "<REPO>\\scripts\\re\\run_ghidra_mcp.cmd"]
    },
    "skylink": {
      "type": "stdio",
      "command": "cmd.exe",
      "args": ["/c", "<REPO>\\scripts\\run_skylink.cmd"]
    }
  }
}
```

Commands: **MCP: Open User Configuration** / **MCP: List Servers**; Copilot reads
`.github/copilot-instructions.md` in this repo automatically. Note the key is `servers`, not `mcpServers`.

## Cursor (`~/.cursor/mcp.json` or `.cursor/mcp.json` in a project)

```json
{
  "mcpServers": {
    "housecarl": {
      "command": "cmd.exe",
      "args": ["/c", "<REPO>\\scripts\\run_housecarl.cmd"]
    },
    "pyghidra-mcp": {
      "command": "cmd.exe",
      "args": ["/c", "<REPO>\\scripts\\re\\run_ghidra_mcp.cmd"]
    },
    "skylink": {
      "command": "cmd.exe",
      "args": ["/c", "<REPO>\\scripts\\run_skylink.cmd"]
    }
  }
}
```

Cursor picks up `.cursor/rules/skyrim-tools.mdc` from this repo automatically.

## Windsurf (`%USERPROFILE%\.codeium\windsurf\mcp_config.json`)

Same `mcpServers` shape as Cursor. Project rules: `.windsurf/rules/skyrim-tools.md`.

## Cline / Roo Code

MCP Servers → **Configure MCP Servers** (writes `cline_mcp_settings.json` in the extension's global storage); same
`mcpServers` shape as Cursor. Workspace rules: `.clinerules/skyrim-tools.md`.

## Gemini CLI (`~/.gemini/settings.json`)

```json
{
  "mcpServers": {
    "housecarl": {
      "command": "cmd.exe",
      "args": ["/c", "<REPO>\\scripts\\run_housecarl.cmd"],
      "timeout": 120000
    },
    "pyghidra-mcp": {
      "command": "cmd.exe",
      "args": ["/c", "<REPO>\\scripts\\re\\run_ghidra_mcp.cmd"],
      "timeout": 300000
    },
    "skylink": {
      "command": "cmd.exe",
      "args": ["/c", "<REPO>\\scripts\\run_skylink.cmd"],
      "timeout": 60000
    }
  }
}
```

`command` is executed without a shell, so do not use `%VAR%` in the path. `GEMINI.md` in this repo is read as context.

## opencode (`opencode.json`)

```json
{
  "mcp": {
    "housecarl": {
      "type": "local",
      "command": ["cmd.exe", "/c", "<REPO>\\scripts\\run_housecarl.cmd"],
      "enabled": true
    },
    "pyghidra-mcp": {
      "type": "local",
      "command": ["cmd.exe", "/c", "<REPO>\\scripts\\re\\run_ghidra_mcp.cmd"],
      "enabled": true
    },
    "skylink": {
      "type": "local",
      "command": ["cmd.exe", "/c", "<REPO>\\scripts\\run_skylink.cmd"],
      "enabled": true
    }
  }
}
```

## Any other client

Each is an ordinary stdio server: `command` = `cmd.exe`, `args` = `["/c", "<REPO>\\scripts\\run_housecarl.cmd"]` (or another launcher), no env,
no URL. Clients that call the section `context_servers` (Zed) or use a YAML file (Continue) take the same three values.
`connect.ps1 -Client json` prints a client-neutral block to adapt.

## HTTP mode, for tools that cannot spawn a process

`run_ghidra_mcp.cmd -t streamable-http -p 8765` starts the Ghidra server on `http://127.0.0.1:8765/mcp`; then:

```powershell
$re = "$env:SKYRIM_RE_DIR"
& "$re\venv\Scripts\python.exe" "$env:SKYRIM_TOOLS_REPO\scripts\re\mcp_call.py" --url http://127.0.0.1:8765/mcp tools
& "$re\venv\Scripts\python.exe" "$env:SKYRIM_TOOLS_REPO\scripts\re\decomp.py" --url http://127.0.0.1:8765/mcp SkyrimSE.exe 0x37B26A
```

houseCARL has no HTTP mode in the installed release; use the stdio wrapper.

## Checks and pitfalls

- **`/mcp` says failed / the client shows the server as crashed.** Run the `.cmd` in a terminal: the wrapper names the
  missing piece. `scripts\agents\doctor.ps1` checks the same paths against the environment variables.
- **`skylink` connects but every tool fails.** Its server starts without the game; the tools answer only while Skyrim runs through SKSE with the `SkyLink AI` mod enabled in MO2 (pipe `\\.\pipe\SkyrimMCP`).
- **Environment variables were set after the client started.** GUI clients inherit the environment of their parent
  process; restart the client (or sign out and back in) after `setup.cmd`.
- **Two agents, one load order.** Several clients may keep a houseCARL instance each — reading is harmless, but do not
  let two agents write mod folders at the same time, and never while the user is mid-way through an MO2 change.
- **AE 1.6.x.** All three servers start fine; only the RE scripts assume 1.5.97, and SkyLink AI is unverified on 1.5.97.
