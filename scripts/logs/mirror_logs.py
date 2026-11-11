"""mirror_logs -- snapshot the game's logs now, into an append-only mirror the game cannot rotate away.

Ported from skyrim-ai-assistant-toolkit (c) 2026 WingedGuardian, MIT License.

The game and its plugins overwrite their logs at every launch: Papyrus.0.log becomes Papyrus.1.log and the oldest
falls off, skse64.log starts empty, a plugin's log is truncated. The evidence for a problem from two launches ago
is usually gone by the time anyone looks. Run this once after a session (or before the next launch) and the logs
are kept.

One shot: it copies, reports, and exits. No watcher, no background process.

    python mirror_logs.py [--dest DIR]

Sources (each folder discovered under Documents/My Games; the variable in brackets overrides it):
    SKSE       *.log, crash-*.txt              [SKSE_LOG_DIR]    SKSE and plugin logs, CrashLogger dumps
    crash      crash-*.log, crash-*.txt        [SKSE_CRASH_DIR]  the same folder unless overridden
    Crashlogs  *.log, *.txt                    [SKSE_CRASH_DIR]  CrashLoggerSSE 1.15+ dumps (timestamp names)
    Papyrus    Papyrus.*.log                   [PAPYRUS_LOG_DIR] Logs/Script
Destination: <SKYRIM_TOOLS_HOME>/log-mirror/<SKSE|crash|Crashlogs|Papyrus>/<file name>, i.e.
%LOCALAPPDATA%/SkyrimTools/log-mirror by default -- never the repository -- or --dest DIR.

Per file, against its mirror copy:
    NEW        no mirror copy yet: copied whole
    APPENDED   the log grew: only the new bytes are copied (the copy is never rewritten)
    UNCHANGED  nothing new: the copy is not touched
    REPLACED   the log was truncated or replaced (a new launch): the previous copy is KEPT, renamed
               <name>.replaced-<UTC time>, and a fresh copy started. Nothing is ever overwritten or deleted.
    SHORT      the log shrank WHILE it was being read (the game rotated it mid-copy): what was read is kept,
               and the next run sees the mismatch and keeps it as a REPLACED copy. Exit 1.
    FAILED     the file could not be read. Exit 1.

"Same log, grown" is decided by comparing the copy's first and last 4 KB with the same ranges of the source; a
replacement that matched both by coincidence would be taken for an append. Each pass copies at most the size the
source had when it was opened, so a log still being written cannot make a pass run forever.

Exit: 0 mirrored - 1 a file could not be read, or shrank while being read - 2 bad usage.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

SAMPLE = 4096
CHUNK = 1024 * 1024
STATUSES = ("NEW", "APPENDED", "UNCHANGED", "REPLACED", "SHORT", "FAILED")

# (label, env override, folder under My Games/<game>/, file patterns). CrashLoggerSSE 1.15+ writes its dumps as
# <SKSE>/Crashlogs/<timestamp>.log, a file name the `crash-` patterns do not cover -- a source of its own keeps
# them, because a dump nobody copied is the evidence this tool exists to save.
SOURCES = (
    ("SKSE", "SKSE_LOG_DIR", "SKSE", ("*.log", "crash-*.txt")),
    ("crash", "SKSE_CRASH_DIR", "SKSE", ("crash-*.log", "crash-*.txt")),
    ("Crashlogs", "SKSE_CRASH_DIR", "SKSE/Crashlogs", ("*.log", "*.txt")),
    ("Papyrus", "PAPYRUS_LOG_DIR", "Logs/Script", ("Papyrus.*.log",)),
)


def default_dest():
    """<SKYRIM_TOOLS_HOME>/log-mirror (default %LOCALAPPDATA%/SkyrimTools/log-mirror), never the repository."""
    return _paths.tools_home() / "log-mirror"


def open_source(path):
    """The source handle (a seam for the mid-read truncation test)."""
    return path.open("rb")


def _same_log(old, src, old_size, size):
    if old_size > size:
        return False
    for pos in sorted({0, max(0, old_size - SAMPLE)}):
        length = min(SAMPLE, old_size - pos)
        old.seek(pos)
        src.seek(pos)
        if old.read(length) != src.read(length):
            return False
    return True


def _keep_previous(destination):
    """Rename the existing copy aside; never overwrite one already kept."""
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(destination.stat().st_mtime))
    kept = destination.with_name("%s.replaced-%s" % (destination.name, stamp))
    n = 2
    while kept.exists():
        kept = destination.with_name("%s.replaced-%s-%d" % (destination.name, stamp, n))
        n += 1
    destination.rename(kept)
    return kept


def mirror(source, destination):
    """Bring the mirror copy up to date. Returns (status, bytes written, the kept previous copy or None)."""
    source, destination = Path(source), Path(destination)
    kept = None
    with open_source(source) as src:
        size = os.fstat(src.fileno()).st_size
        destination.parent.mkdir(parents=True, exist_ok=True)
        offset, status = 0, "NEW"
        if destination.exists():
            with destination.open("rb") as old:
                old_size = os.fstat(old.fileno()).st_size
                same = _same_log(old, src, old_size, size)
            if same and old_size == size:
                return "UNCHANGED", 0, None
            if same:
                offset, status = old_size, "APPENDED"
            else:
                kept, status = _keep_previous(destination), "REPLACED"
        src.seek(offset)
        written = 0
        with destination.open("ab" if status == "APPENDED" else "xb") as dst:
            while written < size - offset:
                block = src.read(min(CHUNK, size - offset - written))
                if not block:
                    status = "SHORT"          # the source shrank mid-read; the next pass keeps this copy aside
                    break
                dst.write(block)
                written += len(block)
        return status, written, kept


def collect(sources=SOURCES):
    """[(label, source file)], each real file once (the crash folder is usually the SKSE folder), plus the folders
    looked in."""
    seen, out, folders = set(), [], []
    for label, env, sub, patterns in sources:
        folder = _paths.resolve_dir(env, sub)[0]
        folders.append((label, folder))
        if not folder.is_dir():
            continue
        for pattern in patterns:
            for path in sorted(folder.glob(pattern)):
                key = os.path.normcase(str(path.resolve()))
                if path.is_file() and key not in seen:
                    seen.add(key)
                    out.append((label, path))
    return out, folders


def usage(problem=""):
    """Print the usage problem and the docstring; the exit code for bad usage is 2."""
    if problem:
        print("ERROR: %s" % problem, file=sys.stderr)
    print(__doc__.strip())
    return 2


def read_args(argv):
    """(destination Path or None, None) or (None, exit code) after printing usage."""
    dest, i = None, 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--dest":
            if i + 1 >= len(argv):
                return None, usage("--dest needs a folder")
            dest = Path(argv[i + 1])
            i += 2
        elif arg.startswith("-") and arg != "-":
            return None, usage("unknown option %s" % arg)
        else:
            return None, usage("no positional arguments: %s (the destination is --dest DIR)" % arg)
    return dest, None


def main(argv):
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, OSError):
        pass

    if "-h" in argv or "--help" in argv:
        print(__doc__.strip())
        return 0

    dest, problem = read_args(argv)
    if problem is not None:
        return problem
    defaulted = dest is None
    if defaulted:
        dest = default_dest()

    try:
        files, folders = collect()
    except OSError as e:
        print("ERROR: cannot list the log folders: %s" % e, file=sys.stderr)
        return 2

    print("mirror: %s%s" % (dest, "   (SKYRIM_TOOLS_HOME default; --dest DIR to change)" if defaulted else ""))
    for label, folder in folders:
        print("  %-9s from %s%s" % (label, folder, "" if folder.is_dir() else "  (not found: nothing to copy)"))
    counts = {status: 0 for status in STATUSES}
    for label, src in files:
        try:
            status, written, kept = mirror(src, dest / label / src.name)
        except OSError as e:
            status, written, kept = "FAILED", 0, None
            print("  FAILED    %s/%s: %s" % (label, src.name, e))
        counts[status] += 1
        if status == "FAILED":
            continue
        note = ""
        if status in ("NEW", "APPENDED", "REPLACED"):
            note = "  +%s bytes" % format(written, ",")
        if kept is not None:
            note += "  (previous copy kept as %s)" % kept.name
        if status == "SHORT":
            note = "  the log shrank while it was read (%s bytes kept); run again" % format(written, ",")
        print("  %-9s %s/%s%s" % (status, label, src.name, note))
    print("  %d file(s): " % len(files) + ", ".join("%d %s" % (counts[s], s) for s in STATUSES))
    return 1 if counts["FAILED"] or counts["SHORT"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
