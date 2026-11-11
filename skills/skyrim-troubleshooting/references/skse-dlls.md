# SKSE DLLs: did it load, and which build is it

A mod whose DLL was refused looks exactly like a mod with no feature: no error in game, nothing in the Papyrus log. The
SKSE log is the only place a refusal is written down, one line per DLL, per launch.

## Read the SKSE log

- SE/AE: `Documents\My Games\Skyrim Special Edition\SKSE\skse64.log` (GOG and Epic installs have their own folders).
- VR: `Documents\My Games\Skyrim VR\SKSE\sksevr.log`.
- The newest file wins, and the log describes the **last launch, not the DLLs on disk now**. Always name the file you
  read and how old it is; a report about a launch from three days ago is a report about a different install.
- `python scripts\logs\skse_load_status.py` reads every DLL SKSE checked; `... [filter]` narrows to a DLL file name or
  the name the plugin reports for itself; `... --log PATH` reads a specific file. It discovers the folder per game (SE/AE
  `skse64.log`, including the GOG and EPIC folders; VR `sksevr.log`; LE `skse.log`) and always names the file it read.
  `SKYRIM_DOCUMENTS_DIR` overrides the game folder under Documents, `SKSE_LOG_DIR` the SKSE folder.



- Rows must sum to the plugins checked. A mismatch prints `ACCOUNTING MISMATCH` and exits non-zero — believe it, and
  fix the parser rather than the number.
- On SKSE64 2.1+ the "loaded correctly" lines are printed **after** all loading, not beside their "checking plugin" line,
  so results are matched to plugins by DLL name, never by position. A tool that pairs them by order names the wrong
  plugin as refused.
- `skse64_loader.log` holds the loader's own record (version, target product version) and **no plugin lines**; it is not
  a substitute for the plugin log.

## The four verdicts, and what each means for the user

| Log line | Meaning | Action |
|---|---|---|
| `loaded correctly` | accepted and running this launch | none — but "loaded" is not "works", see *behaviour* below |
| `reported as incompatible during query` / `... during load` | the DLL refused this runtime or this SKSE build | not the mod's fault in game; the DLL was built for another runtime. Get a VR/SE/AE or multi-runtime build |
| `does not appear to be an SKSE plugin` | the file in `SKSE/Plugins` is not an SKSE plugin (a loose dependency, a 32-bit DLL, a helper) | find what it actually is; it is not providing the feature |
| an SKSE error such as an outdated Address Library | SKSE itself stopped on a prerequisite | update the Address Library first |

- The **version** a DLL reports is printed raw, as the author encoded it. Compare it with a known build, never with a
  mod page's version string — they are different numbering schemes as often as not.
- **Many DLLs carry no Windows version resource**, so a file-properties dialog cannot say which build is installed. The
  SKSE log can, because the plugin reports about itself.
- **The DLL on disk is the source of truth for "what is installed", not the mod manager.** A manually installed or
  hand-reverted plugin is invisible to Vortex/MO2, so the manager's version can disagree with what the game loads. Read
  the embedded File/Product version of `Data/SKSE/Plugins/*.dll`.

## The duplicate-DLL trap

- **Forks, ports and renames leave the old DLL behind, and SKSE loads both.** A renamed fork's old DLL beside the new one
  is the classic case, and the older one can override the newer one's functions. After any update, look for an
  old-named sibling before believing the update took effect.
- The Papyrus log's `Replacing native function ...` line is the signature: two plugins registering the same script's
  natives. MEASURED case: a 2019 port left beside a modern build replaced about **90 of the 90** shared natives, some
  with different signatures, so scripts compiled against the modern declarations called them with the wrong shape. Fix:
  rename the old DLL to `.disabled` (a DLL change carries no save data, so it is save-safe) and confirm the
  `Replacing native function` lines are gone from the next log.
- The modern VR install of a Papyrus-extender plugin is the original mod's scripts plus a VR DLL dropped **over** the
  original's DLL (same file name). A mod manager filing that DLL under the original mod is the documented install, not a
  mis-file — but it is also how a second copy of the plugin ends up installed.

## Prerequisites and version traps

- **A newer Address Library can be a hard prerequisite even when the mod's stated minimum is met.** MEASURED on one VR
  install: a plugin whose stated minimum Address Library was 0.235.0 stopped the game before SKSE finished starting,
  missing ID 40291, with 0.276.1 installed; with 0.279.0 it loaded. **Update the Address Library first when a DLL
  update fails early**, and treat a stated minimum as a claim to test against the log.
- A newer build is not automatically better: a Papyrus fix-up plugin's newer release broke NPC dialogue on VR (the NPC
  speaks, the choice menu never opens) with unbound-native lines at load. Keep a personal "do not update past X" list,
  keyed by build, and record why.
- A DLL that declares native functions and the `.pex` declarations its consumers compiled against **move together**. A
  mismatch logs `does not match existing signature` and the native goes unbound.
- A plugin's config is sometimes split: a user-owned TOML beside the one the mod installs (`EngineFixesCustom.toml` next
  to `EngineFixes.toml`). Overrides belong in the user-owned file, and the mod's own log line is the confirmation that
  the setting was read.
- **A VR mod's MAIN file on Nexus can be the SE/AE build.** MEASURED on one mod: MAIN was SE/AE-only and the VR DLL was
  on the author's GitHub release. An `openvr` string inside a DLL is **not** proof of VR support — the SE/AE DLL had one
  too. Judge by declared runtime support and runtime guards, or by this log after a test start. A page that *claims* VR
  is provisional until the log line says `loaded correctly`.
- **The mod manager's attribution is not evidence.** A manager can file a DLL under the wrong mod when files were dropped
  over each other; the bytes and the log line decide.

## Load failure versus behaviour

- **A main-menu start is enough** to check that an SKSE plugin loads: launch to the main menu (no save loaded) and read
  its line in the SKSE log. It says nothing about behaviour in a loaded world — say "the DLL loads and starts", not
  "the mod works".
- A DLL that loads and does nothing is a different investigation: a missing prerequisite DLL, a config it could not
  read, a feature gated behind its own INI, or an unbound native in the Papyrus log. Read
  [papyrus-errors.md](papyrus-errors.md) next, then the mod's own log.
- **A DLL change is save-safe** (no save data, so reverting is safe mid-playthrough) — **unless the DLL writes co-save
  records**, which changes the picture:
  `python scripts\save\cosave_info.py [SAVE.skse]` lists the co-save records by opcode, so you can see which plugins
  stash state. Common writers are a JSON store, a string/form storage utility, a Papyrus extender, a distribution
  framework; many opcodes are unnamed because the format inside each chunk belongs to its plugin.

## With the houseCARL server

`housecarl_skse` reads the SKSE layer of the live load order rather than one log:

- `findings='pairing'` pairs the scripts that declare natives with the DLLs the providing mod ships, and leads with
  **PAIRED-BUT-DEAD** (every candidate DLL statically cannot load: wrong runtime, BSA-only, subfolder-shipped, 32-bit,
  unreadable, debug build) and **UNPAIRED**.
- `findings='inventory'` reports the whole layer's diagnostics: version-locked plugins, legacy query-only plugins,
  non-plugin DLLs, subfolder DLLs, DLLs contested by more than one mod, debug builds.
- Both are **verify flags, not promises about a running game**. The log is still the per-launch truth.

Without houseCARL, read `mods\*\SKSE\Plugins\*` and the SKSE log directly, and say that the answer is file-level.

## Reverting a DLL

1. Note the current line in the SKSE log for that DLL (before).
2. Put the old DLL back (or rename the new one to `.disabled`) in the **mod folder that owns it**, not in `Data/` — the
   user's mod manager owns what is installed, and a hand-placed DLL is untracked and unreproducible (see
   [conflicts-and-paths.md](conflicts-and-paths.md)).
3. Relaunch to the main menu and diff the log line (after). Only then say the reverted build is the one running.
4. If the DLL is stateful, the co-save may now describe a format it no longer writes; back the pair up before the next
   save and say so.

Source: adapted from skyrim-ai-assistant-toolkit (c) 2026 WingedGuardian, MIT License.
