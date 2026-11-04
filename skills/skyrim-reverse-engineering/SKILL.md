---
name: skyrim-reverse-engineering
description: >-
  Reverse-engineer Skyrim SE 1.5.97 and its SKSE plugin DLLs on this machine: read a freeze or crash stack
  ("SkyrimSE.exe+XXXX", "SomeMod.dll+XXXX"), map offsets to Address Library REL::IDs and back, snapshot the threads of
  the running (or hung) game, name a DLL's functions from its .pdb, disassemble at an address, and decompile with Ghidra
  through the pyghidra-mcp MCP server (or its CLI when the server is not loaded). Use when the game hangs or crashes and
  a log names addresses, when a hook site / function / vtable slot must be found or checked before writing SKSE code,
  when another mod's DLL behaviour must be understood, or when an IDA reference in a comment must be verified.
---

# Skyrim reverse engineering (local)

The scripts and the ID name table are in SkyrimTools (git, `D:\Games\SkyrimTools`); the heavy workspace stays in
`D:\Games\Issen\re\` (env `SKYRIM_RE_DIR`; outside every git repo, nothing there is shipped):

| Path | What |
|---|---|
| `re\ghidra_12.2_PUBLIC\` | Ghidra 12.2 (official NSA build, SHA-256 checked) |
| `re\jdk-25.0.5+8\` | Temurin JDK 25 (Ghidra 12.2 needs Java 25) |
| `re\venv\` | Python 3.13 venv: `pyghidra-mcp` 0.3.0, `pyghidra`, `capstone`-free; the MCP client SDK |
| `re\bins\skyrim\SkyrimSE.exe` | a copy of the 1.5.97 exe (the game folder's may change; analyse the copy) |
| `re\bins\<mod>\` | copies of DLLs (+ their .pdb) taken for analysis |
| `re\projects\` | Ghidra projects (`skyrim.gpr` = the main one) and pyghidra-mcp's cache |
| `SkyrimTools\scripts\re\run_ghidra_mcp.cmd` | starts pyghidra-mcp with that JDK / Ghidra, project `projects\skyrim.gpr` |
| `SkyrimTools\scripts\re\` | the scripts below (`skyrim_paths.py` = where the workspace is) |
| `SkyrimTools\data\se_id_names.tsv` | REL::ID -> name, from every source we have (`build_id_names.py`) |

## Quick tools (no Ghidra needed, seconds)

All are plain `python` (system Python has `capstone`, `pefile`); run from `D:\Games\SkyrimTools\scripts\re`.

- **Offset <-> ID**: `python addrlib.py off 6D4B6F SkyrimSE.exe+37B26A` -> `ID 40293 +0x7F ...` and the function's name
  when CommonLibSSE-NG / our plugins use that ID. `python addrlib.py id 37996` -> offset. Offsets are RVAs
  (address - 0x140000000), the same numbers logs print after `SkyrimSE.exe+`. Reads the STB instance's
  `version-1-5-97-0.bin` (SE format 1, parser follows CommonLibSSE-NG `IDDB::unpack_file`). An ID's "+0x7F" is the
  distance into the function that starts at that ID only if no unnamed function lies between: check in Ghidra.
- **Live thread snapshot** (game running or hung): `python thread_stacks.py --busy --ids` (default process
  SkyrimSE.exe). Suspends each thread only while reading it. Take 2-3 snapshots: frames that repeat are where a thread
  is stuck; a thread busy in the same function every time is a loop. Values on a stack that follow a call are
  candidates, not an unwound stack: trust the innermost few and those that repeat. A hung main thread usually waits
  (RIP in ntdll); the culprit is the BUSY thread it waits for.
- **A DLL's function at an RVA from its .pdb**: `python pdbsym.py <dll> 2636A 75910` (dbghelp). `?` = the .pdb does not
  match the DLL (different build) or has no public symbols: use Ghidra.
- **Disassemble around return addresses**: `python disasm_at.py <exe/dll> 6D4B6F 37B26A` shows the call before each.
- **A vtable slot of SkyrimSE.exe, disassembled**: `python vtable_slot.py 291232 5` (vtable REL::ID from
  CommonLibSSE-NG `Offsets_VTABLE.h`, slot index = the `// NN` comment in the class header).
- **Every call a function makes, targets named**: `python calls_in.py 5B2FF0 5B3760` (range of RVAs).
- **Who makes virtual call `[reg+off]`**: byte-scan as in this skill's history, or `python find_vcall.py 0x568 4 ID:35565`
  (BFS over direct calls). vfunc index N -> offset N*8 (PlayerCharacter::Update 0xAD -> 0x568).
- **A .swf's ActionScript 2 at a glance**: `python swf_as2.py file.swf [--names]` (loops, timers, constant pools).
- **Decompile through a running HTTP server**: `D:\Games\Issen\re\venv\Scripts\python decomp.py [--xrefs] /Binary-hash 0xADDR Name::Func`
  (resolves "Ambiguous match" itself). In Git Bash set `MSYS_NO_PATHCONV=1`, else `/Binary-hash` becomes a Windows path.
- **Our own freeze log**: IssenFramework's watchdog (`[Dev] fFreezeLog`) writes `freeze: ... main thread ...` and
  `freeze: ... busy thread <id> (started at X) at ...; menus on the stack: <menu> (<swf>)` lines in
  `Documents\My Games\Skyrim Special Edition\SKSE\IssenFramework.log`.

Verified SkyrimSE.exe 1.5.97 facts (2026-11-04):
- `Main::Update` = ID 35565 (+5B2FF0). Order in a frame: PlayerCharacter::Update via ID 35578 at +5B327E; input
  poll (`BSInputDeviceManager::PollInputDevices`) at +5B33B0; job lists 1-4 kicked at +5B3475..+5B349F (ID 68165,
  ecx = list); render ID 35556 at +5B35C2 waits list 2 at +5B139D (ID 68167). The UI job ID 38088 (+63FCB0) runs
  `UI::ProcessMessages` ID 79945 then `UI::AdvanceMovies` ID 79946 on a job thread between kick and wait.
- `UI::AdvanceMovies` calls each menu's `IMenu::AdvanceMovie` (vfunc 5) with `(UI+0x19C, UI+0x1A0)` = uiTimer
  realTimeDelta (seconds) and smoothedRunTimeMS (ms since start). Vanilla `IMenu::AdvanceMovie` (ID 80284, +ECD8A0)
  passes the interval to `GFxMovieView::Advance` (vtable +0x128); CommonLibSSE-NG's `RE::IMenu::AdvanceMovie`
  (src/RE/I/IMenu.cpp) passes currentTime instead: a bug every plugin calling the base class inherits.

Known SkyrimSE.exe 1.5.97 regions seen in stacks: `EE0000-F50000`, `FFD000-1071000` = Scaleform GFx / AS2 VM (a
Flash menu or widget script); `C07FD0` = BSThread entry (job/task threads); `5AF4F4` / `5ACC05` = the main loop;
`C349C3` = job threads idle waiting.

## Ghidra through MCP (pyghidra-mcp)

Shipped by the SkyrimTools plugin (`D:\Games\SkyrimTools\.mcp.json`) as server `pyghidra-mcp`, stdio, via
`scripts\re\run_ghidra_mcp.cmd`; tool names contain `pyghidra-mcp` (deferred: load them with ToolSearch "pyghidra"). The JVM starts in ~20-60 s at session start.

Tools: `list_project_binaries`, `list_project_binary_metadata`, `decompile_function(binary_name, name_or_address)`,
`disassemble(binary_name, address, count)`, `list_xrefs`, `search_symbols_by_name`, `search_strings`, `search_code`,
`read_bytes`, `list_imports`/`list_exports`, `gen_callgraph`, `import_binary(binary_path)`, `rename_function`,
`set_comment`, `set_function_prototype`, `save`.

- `binary_name` is the project path printed by `list_project_binaries`, e.g. `/SkyrimSE.exe-5666e1` (name + hash
  suffix), not the bare file name.
- Addresses are absolute: SkyrimSE.exe's image base is `0x140000000` (RVA `6D4B6F` -> `0x1406D4B6F`); a DLL's base is
  in `list_project_binary_metadata` (usually `0x180000000`).
- A newly imported binary is analysed in the background; tools answer "Analysis incomplete" until done.
  SkyrimSE.exe takes long the first time (tens of minutes); it is analysed once into `projects\skyrim.gpr` and kept.
- To analyse another mod's DLL: copy it (and its .pdb) into `re\bins\<mod>\`, then `import_binary` with that path.
  The `.pdb` next to the DLL is picked up by Ghidra's PDB analyzer when its GUID matches.
- Rename functions you identify (`rename_function`, e.g. to the CommonLibSSE name + `_ID40293`) and `save`, so the next
  session starts with them.

Without the MCP tools loaded (server failed, or a quick look): start it over HTTP and use the CLI client:
```
cmd /c D:\Games\SkyrimTools\scripts\re\run_ghidra_mcp.cmd -t streamable-http -p 8765   (background; wait for "Uvicorn running")
D:\Games\Issen\re\venv\Scripts\python D:\Games\SkyrimTools\scripts\re\mcp_call.py --url http://127.0.0.1:8765/mcp tools
D:\Games\Issen\re\venv\Scripts\python D:\Games\SkyrimTools\scripts\re\mcp_call.py --url http://127.0.0.1:8765/mcp decompile_function "{\"binary_name\": \"/SkyrimSE.exe-5666e1\", \"name_or_address\": \"0x1406D4AF0\"}"
```
Only one process may hold a Ghidra project: stop the stdio server's twin (or use another `--project-name`) before
starting a second one, else "is in use". A killed server leaves `projects\<name>.lock`; delete it when no
pyghidra-mcp / python3.13 process is left.

Local patch in the venv: `ghidrecomp\utility.py` `set_pdb` printed a variable before assigning it (crashed every
`--sym-file-path` analysis). Re-apply after reinstalling `pyghidra-mcp`.

## Workflow: a freeze or crash

1. Collect addresses: our `freeze:` lines, a crash log (`Documents\My Games\Skyrim Special Edition\SKSE\Crashlogs` or
   the crash logger's folder), or `thread_stacks.py --busy --ids` x3 while it hangs.
2. `addrlib.py off ...` every `SkyrimSE.exe+` frame; `pdbsym.py` every DLL frame with a .pdb.
3. The innermost non-system module of the stuck/busy thread is the suspect; the outer DLL frames say who called it.
4. Decompile the suspect function in Ghidra to see what it waits on / loops over.
5. Say what is proven (stack, repeat across snapshots) and what is a guess.

## Workflow: before an SKSE hook

1. Find the function: CommonLibSSE-NG name -> `grep` its `RELOCATION_ID(se, ae)` -> `addrlib.py id <se>`.
2. Decompile it in Ghidra; for a call-site hook `disassemble` at the site and check the opcode (E8 call / E9 jmp) and
   that the offset is inside the function. For a vtable, `read_bytes` the vtable slot.
3. Write the verified facts in the code comment (address, ID, what was checked), as RDF / IssenFramework already do.

Related: `skse-plugin-authoring` (writing the hook), `skyrim-local-toolbox` (MO2 instance, plugins, records).
