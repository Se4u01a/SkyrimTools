"""Where a Skyrim install keeps its logs: the per-game folder under Documents/My Games, and the toolkit's folders.

Ported from skyrim-ai-assistant-toolkit (c) 2026 WingedGuardian, MIT License.

Shared by the four tools in this folder so the discovery rule lives in exactly one place. Two things it
deliberately does NOT do: bake in a path from the machine it was written on, and pick between candidates
silently.

The silent pick is the real hazard. A machine can carry several per-game folders under Documents/My Games at
once -- an SE install, a VR install, one left behind by an uninstall -- and they are structurally identical.
Reading the wrong one does not fail: it produces a complete, plausible report about a log nobody asked about,
and a clean bill of health is exactly what that looks like. So when more than one candidate exists, the first
is used and the rest are named on stderr together with the variable that overrides it.

Priority order (this repo is SE-first; the toolkit these tools were ported from is VR-first):
    Skyrim Special Edition, Skyrim Special Edition GOG, Skyrim Special Edition EPIC, Skyrim VR, Skyrim (LE)

Environment overrides, each checked before any discovery:
    SKYRIM_DOCUMENTS_DIR   the game folder under Documents, e.g. <Documents>/My Games/Skyrim Special Edition
    SKSE_LOG_DIR           the SKSE folder (skse64.log, plugin logs, crash dumps)
    SKSE_CRASH_DIR         where crash dumps are (default: the SKSE folder)
    PAPYRUS_LOG_DIR        the Logs/Script folder (Papyrus.N.log)
    SKYRIM_TOOLS_HOME      the toolkit's own folder (the log mirror destination; default %LOCALAPPDATA%/SkyrimTools)

An override is never second-guessed: if it names a folder that does not exist, the answer is that folder, not a
fallback to some other install -- the caller's error message then names a place the user can go and look.
Windows only: Documents comes from SHGetFolderPathW, so a redirected Documents (OneDrive, a moved or localized
folder) is found where the user sees it.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

GAME_FOLDERS = ("Skyrim Special Edition", "Skyrim Special Edition GOG", "Skyrim Special Edition EPIC",
                "Skyrim VR", "Skyrim")
DOCS_ENV = "SKYRIM_DOCUMENTS_DIR"


def _windows_folder(csidl):
    """The folder Windows reports for a CSIDL id, or "" when it cannot answer (not Windows, or the call failed)."""
    if sys.platform != "win32":
        return ""
    try:
        import ctypes

        buf = ctypes.create_unicode_buffer(32768)
        ok = ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buf)
    except (AttributeError, OSError):
        return ""
    return buf.value if ok == 0 else ""


def my_games():
    """Documents/My Games, where Bethesda writes: as Windows reports Documents, else <home>/Documents/My Games.

    Documents can be redirected (OneDrive, a moved or localized folder), so a guess like ~/Documents would miss
    the real one. CSIDL_PROFILE is compared with USERPROFILE first: a test's fake profile keeps its own
    Documents instead of the real one.
    """
    home = os.environ.get("USERPROFILE") or str(Path.home())
    profile = _windows_folder(0x28)                              # CSIDL_PROFILE
    if profile and os.path.normcase(profile) != os.path.normcase(os.path.normpath(home)):
        return Path(home) / "Documents" / "My Games"
    documents = _windows_folder(0x05)                            # CSIDL_PERSONAL
    if documents:
        return Path(documents) / "My Games"
    return Path(home) / "Documents" / "My Games"


def game_folders():
    """(candidate game folders in priority order, how they were found -- an env variable name or the root)."""
    override = os.environ.get(DOCS_ENV)
    if override:
        return [Path(override)], DOCS_ENV
    root = my_games()
    return [root / name for name in GAME_FOLDERS], str(root)


def find_game_dir(subpath=""):
    """(chosen, others) for "<game folder>/<subpath>".

    A candidate is a game folder that actually holds `subpath`, `subpath` may use either separator ("SKSE" or
    "Logs/Script" or "SKSE/Crashlogs"). `others` is every rival that also exists: callers are expected to surface
    it rather than drop it -- see the module docstring.

    With no candidate at all the answer is the highest-priority name (which may not exist), so the error that
    follows points at a real location instead of printing an empty path.
    """
    folders, _ = game_folders()

    def probe(folder):
        return folder / subpath if subpath else folder

    existing = [probe(folder) for folder in folders if probe(folder).is_dir()]
    if not existing:
        return probe(folders[0]), []
    return existing[0], existing[1:]


def resolve_dir(env_var, subpath=""):
    """find_game_dir, with an environment override and a warning on stderr when the choice is ambiguous."""
    override = os.environ.get(env_var)
    if override:
        return Path(override), []

    chosen, others = find_game_dir(subpath)
    if others:
        lines = ["[_paths] more than one candidate exists for %s; using:" % (subpath or "the game folder"),
                 "  %s" % chosen]
        lines += ["  ignoring: %s" % other for other in others]
        lines += ["  They can belong to different installs, and the wrong one reads perfectly.",
                  "  If this picked wrong, set %s." % env_var]
        print("\n".join(lines), file=sys.stderr)
    return chosen, others


def tools_home():
    """The toolkit's own folder (never the repo): $SKYRIM_TOOLS_HOME, else %LOCALAPPDATA%/SkyrimTools."""
    override = os.environ.get("SKYRIM_TOOLS_HOME")
    if override:
        return Path(override)
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "SkyrimTools"
    return Path.home() / "AppData" / "Local" / "SkyrimTools"
