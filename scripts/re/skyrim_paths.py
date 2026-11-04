"""Where the heavy reverse-engineering workspace lives (Ghidra, JDK, venv, Ghidra projects, binary copies).

The scripts live in SkyrimTools; the workspace stays outside the repo. Override with the SKYRIM_RE_DIR variable.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS_ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
DATA_DIR = os.path.join(TOOLS_ROOT, "data")
RE_DIR = os.environ.get("SKYRIM_RE_DIR", r"D:\Games\Issen\re")
SKYRIM_EXE = os.path.join(RE_DIR, "bins", "skyrim", "SkyrimSE.exe")
