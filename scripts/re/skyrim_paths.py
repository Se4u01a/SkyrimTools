"""Where things live on this machine. Every path comes from a user environment variable that setup.ps1 writes:

  SKYRIM_TOOLS_HOME   install root of the heavy parts      (default %LOCALAPPDATA%\\SkyrimTools)
  SKYRIM_RE_DIR       RE workspace: Ghidra, JDK, venv, projects, bins   (default %SKYRIM_TOOLS_HOME%\\re or repo root re\\)
  SKYRIM_MO2_DIR      MO2 instance folder, the one with ModOrganizer.ini
  SKYRIM_GAME_DIR     game folder (SkyrimSE.exe)
  SKYRIM_ADDRLIB_BIN  Address Library .bin, when it is not found under the MO2 mods or the game's Data
"""
import glob
import os

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS_ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
DATA_DIR = os.path.join(TOOLS_ROOT, "data")
TOOLS_HOME = os.environ.get("SKYRIM_TOOLS_HOME") or os.path.join(os.environ.get("LOCALAPPDATA", ""), "SkyrimTools")
RE_DIR = os.environ.get("SKYRIM_RE_DIR")
if not RE_DIR or not os.path.isdir(RE_DIR):
    repo_re = os.path.join(TOOLS_ROOT, "re")
    if os.path.isdir(repo_re):
        RE_DIR = repo_re
    else:
        RE_DIR = os.path.join(TOOLS_HOME, "re")
MO2_DIR = os.environ.get("SKYRIM_MO2_DIR", "")
GAME_DIR = os.environ.get("SKYRIM_GAME_DIR", "")
SKYRIM_EXE = os.path.join(RE_DIR, "bins", "skyrim", "SkyrimSE.exe")


def address_library_bin(name="version-1-5-97-0.bin"):
    """The Address Library .bin: SKYRIM_ADDRLIB_BIN, else the first MO2 mod that ships it, else the game's Data."""
    if os.environ.get("SKYRIM_ADDRLIB_BIN"):
        return os.environ["SKYRIM_ADDRLIB_BIN"]
    found = []
    if MO2_DIR:
        found += sorted(glob.glob(os.path.join(glob.escape(MO2_DIR), "mods", "*", "SKSE", "Plugins", name)))
    if GAME_DIR:
        found.append(os.path.join(GAME_DIR, "Data", "SKSE", "Plugins", name))
    for path in found:
        if os.path.isfile(path):
            return path
    raise SystemExit("Address Library %s not found: set SKYRIM_MO2_DIR / SKYRIM_GAME_DIR (setup.ps1), "
                     "SKYRIM_ADDRLIB_BIN, or pass --bin <path>" % name)
