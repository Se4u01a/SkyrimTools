---
name: skyrim-modding-practices
description: >-
  Working rules learned while building SKSE plugins (IssenFramework, ReactiveDodgeFramework, DF) on this machine:
  editing files without mangling them (Bash heredocs, CRLF), never overwriting a deployed ini the user tuned in game,
  committing every finished change, MO2 / Pandora / FLICK pitfalls, where clips and assets may live, how to verify
  engine facts and how to report what was and was not tested. Load at the start of any Skyrim mod work here: before
  editing project files, deploying into an MO2 mod folder, running Pandora, or telling the user a change is done.
---

# Skyrim modding practices (this machine)

Each rule cost at least one debugging round. Tools are listed in `skyrim-local-toolbox`.

## Editing files
- Bash heredocs here halve backslashes (`\\` -> `\`), drop tab indentation and sometimes fail with "unexpected EOF".
  Write new files with Write and change code with Edit. A Python helper that must edit text: put it in a file (Write),
  read bytes, `\r\n` -> `\n`, edit, restore the original EOL, build backslashes with `chr(92)`.
- Repos have `core.autocrlf=true`: working copies are CRLF, the repo LF. An exact-match edit that fails is usually EOL
  or tabs. Keep each file's EOL and encoding (FLICK translations: UTF-16LE with BOM, CRLF).
- `.cmd` files: CRLF.

## Deploying into MO2
- Never copy a shipped ini over the deployed one: the user saves tuned values into it from the in-game menu
  (formatting changes like 0.40 -> 0.4 hide real tuning). Merge by section+key: `scripts\misc\merge_ini.py DIST DEPLOYED`
  keeps every existing value, adds only new keys.
- MO2 rewrites `ModOrganizer.ini` from memory on exit: never edit it while MO2 runs; ask the user to change
  executables in the MO2 GUI.
- A NEW mod folder does nothing until the user enables it in MO2 (it loads last). Say so every time one is created.
- Game clips, meshes and other mods' assets stay in MO2 mod folders, never in a git repo (licences: most forbid
  re-upload). Commit recipes / listings / scripts that rebuild them. Need one effect from another mod: copy just that
  file (with vanilla-only textures) into our own mod folder under the same path instead of enabling the whole mod.
- Never write into another author's mod folder; make a new mod (patch, SPID/KID/SkyPatcher INI, OAR submod).
- OAR, Payload Interpreter and Pandora read their folders at game start: changes need a restart.

## Pandora / behaviors
- Pandora 4.x crashes on `<insert path="">`; use Pandora 5 (single exe, keeps `Settings.json` next to itself) and pass
  `-o:"...\mods\PandoraOutput"` (v5 may reset outputPath). A Pandora copy run outside MO2 reads the real paths from
  its Settings.json (4.3: `%LOCALAPPDATA%\Pandora Behaviour Engine\Settings.json`) and once wrote into a real mod:
  stage it (RDF `tools\stage_pandora.py`, writes only under `_work\`).
- Pandora patches address nodes by NEMESIS ids of the vanilla graph. Check a patch offline (`hkxcheck.py`,
  `pandora_log.py`) before asking the user to run it.
- Only clip annotations named after a graph event reach SKSE plugins (`PIE.@...` works because PIE is one).

## Engine facts and hooks
- Never trust an address, ID, vtable slot or "IDA says" comment unverified: map it with `addrlib.py`, look at it in
  Ghidra (`skyrim-reverse-engineering`), write what was checked into the code comment.
- CommonLibSSE-NG is shared at `D:\Games\Issen\CommonLibSSE-NG` (`../CommonLibSSE-NG` from a project); RDF's
  xmake.lua points to a missing `D:/Games/_build/...` path.
- Freezes: snapshot threads from outside (`thread_stacks.py --busy --ids`, 2-3 times); the busy thread the main thread
  waits for is the suspect. Say what is proven (repeating frames) and what is a guess. Other mods' Scaleform scripts
  (widgets, menus) were the cause twice; don't assume our code.

## Git and reporting
- Commit every finished change that builds and passes its tests (clear message + attribution), so the user can roll
  back after testing in game. Experiments the user rejects go on a `wip/...` branch, not lost. Deployed files outside the
  repo (MO2 ini) are never committed.
- Only the user tests in game. After a change say plainly "built, NOT tested in game" and what they must do (enable a
  mod, rerun Pandora, restart). Mark it confirmed only after they confirm.
- Design decisions the user already answered are recorded in project memory: follow them, don't re-ask.

## Untrusted input
- Downloaded archives go to `_downloads\<name>\` (each in its own empty folder); run Python that reads them with `-I`
  and keep scripts elsewhere (`_scratch\`). Check Nexus permissions before redistributing anything.
