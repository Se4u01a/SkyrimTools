# skyrim-gateway

The SkyrimTools MCP facade, **phase 0** of [docs/design/gateway.md](../docs/design/gateway.md): one MCP server that
fronts houseCARL, pyghidra-mcp and SkyLink AI. The existing `.cmd` launchers and `.mcp.json` keep working; the gateway
is opt-in until phase 1.

## What phase 0 does

- **One entry for the client.** `skyrim-gateway.exe` (no arguments) is a stdio MCP server; it relays bytes to a per-user
  daemon over the named pipe `\\.\pipe\skyrim-gateway-<user>` (DACL: this user only), starting the daemon when none runs.
- **One process per backend for every session.** Two agent sessions share one houseCARL, one Ghidra JVM, one SkyLink
  pipe client. This matters: SkyLink's plugin serves one pipe client at a time, and a Ghidra project opens in one
  process only.
- **The backends' own tool names** (`housecarl_records`, `decompile_function`, SkyLink's), because the skills cite
  them, plus `gateway_status` and `gateway_restart`; every description starts with `[backend]`. A name two backends
  share is exposed as `<backend>_<name>` for the second one. Prefixes (`Prefix`/`Strip` in a `--config` spec) and
  the curated names come with phase 1. Arguments and results pass through unchanged; progress notifications are
  forwarded to the session that made the call.
- **Lazy start.** Tool schemas are cached in `%SKYRIM_TOOLS_HOME%\gateway\schemas\`. With a cache, `tools/list` starts
  nothing and a backend starts on its first call; without one (first run), the daemon lists every backend once, waiting
  up to 20 s for the quick ones (houseCARL, SkyLink) and letting Ghidra finish in the background. After every start the
  tool list is re-read and reconciled, so a backend update does not leave a stale cache.
- **Idle stop.** A backend stops after 30 min without calls (Ghidra: 60); the daemon exits after 30 min with no
  session and no running backend (`--idle-exit`).
- **Structured errors** in the tool result (`isError: true`, JSON body with `code`, `message`, `remedy`, `detail`):
  `NOT_INSTALLED`, `BACKEND_LOCKED` (Ghidra project held by another process), `BACKEND_FAILED`,
  `BACKEND_START_TIMEOUT`, `GAME_NOT_RUNNING`, `CANCELLED`, `UNKNOWN_TOOL`. Three failed starts in a row put a backend
  in a 60 s cooldown; `gateway_restart` clears it.
- **Current variables.** Backends get the user's variables from `HKCU\Environment` laid over the daemon's environment
  (PATH excepted), so a client started before `setup.cmd` changed them still runs the right paths.

Not in phase 0: the curated core API, `gateway_discover` / `enable` / `call`, permission classes and plan/apply,
`setup`/`doctor`/`connect` in the exe. See the design document.

## Build and run

```powershell
cd gateway
go build -o bin\skyrim-gateway.exe .\cmd\skyrim-gateway
go test ./...
```

`bin\` is gitignored; the repo ships no binaries. The exe finds the repo through `SKYRIM_TOOLS_REPO` or by walking up
from its own folder to `.claude-plugin\plugin.json`.

```powershell
bin\skyrim-gateway.exe status     # gateway_status of the running daemon (exit 1 when none runs)
bin\skyrim-gateway.exe stop       # stop the daemon and its backends
bin\skyrim-gateway.exe daemon     # run the daemon in the foreground (log also on stderr)
```

Log: `%SKYRIM_TOOLS_HOME%\gateway\gateway.log`. Flags: `--pipe NAME`, `--config FILE` (JSON array of backend specs,
see `internal/backend.Spec`), `--idle-exit DURATION`.

### In Claude Code

The plugin's `.mcp.json` starts `scripts\run_gateway.cmd`, which runs the first exe it finds
(`SKYRIM_GATEWAY_EXE`, `<repo>\gateway\bin\`, `%SKYRIM_TOOLS_HOME%\gateway\`), builds it with Go on the first start
when there is none, and without Go falls back to houseCARL alone (warning on stderr). After switching, run
`/plugin marketplace update skyrim-tools` and start a new session: an old session's own `pyghidra-mcp` keeps the
Ghidra project locked until it ends (`gateway_status` shows `locked`).

Rebuilding while a daemon runs fails (Windows locks a running exe): `bin\skyrim-gateway.exe stop` first.

## Layout

| Path | What |
|---|---|
| `cmd/skyrim-gateway` | CLI: shim (default), `daemon`, `status`, `stop`, `version`; detached daemon spawn |
| `internal/daemon` | the shared MCP server: sessions, routes, prefixes, schema cache, progress forwarding, idle exit |
| `internal/backend` | one child MCP server: start/stop, idle timer, crash restart, failure cooldown, error mapping |
| `internal/config` | repo/home resolution, the built-in backend table (wraps `scripts\*.cmd`) |
| `internal/pipe` | per-user named pipe (go-winio) |
| `internal/winenv` | user variables from the registry |

Tests (`internal/daemon/daemon_test.go`) run the test binary itself as a fake MCP backend over a real named pipe:
shared process across sessions, cache-driven lazy start, not installed, lock, crash and restart, progress forwarding,
game not running, single daemon per pipe.
