"""skse_load_status -- what SKSE actually did with each DLL, read from SKSE's own log.

Ported from skyrim-ai-assistant-toolkit (c) 2026 WingedGuardian, MIT License.

Many SKSE plugin DLLs carry no Windows version resource, so a file's properties cannot say which build is
installed. SKSE's log records, per DLL in Data/SKSE/Plugins, the version the plugin reports about itself and what
SKSE did with it: loaded it, refused it as incompatible, or found it was not an SKSE plugin at all.

    python skse_load_status.py [filter] [--log PATH]

    filter     matches the DLL file name OR the name the plugin reports about itself (default: everything)
    --log PATH read this file instead of discovering one

Which log (the newest wins, and the one read is always named):
    SE / AE     <My Games>/Skyrim Special Edition[ GOG| EPIC]/SKSE/skse64.log
                (every SKSE64 release from 2.0.20 to 2.3.1 writes this one name: skse64/skse64.cpp,
                 gLog.OpenRelative, in ianpatt/skse64)
    Skyrim VR   <My Games>/Skyrim VR/SKSE/sksevr.log
    LE          <My Games>/Skyrim/SKSE/skse.log
Override the folder with SKSE_LOG_DIR, or the whole Documents root with SKYRIM_DOCUMENTS_DIR.
skse64_loader.log is read too, but only for the launcher's record (loader version, target product version, dll):
it holds no plugin lines, and neither does skse64_steam_loader.log.

The line formats this reads (MEASURED on a real SKSE64 2.0.20 log; READ for 2.1+ in ianpatt/skse64
skse64/PluginManager.cpp, tags v2.0.20 and v2.3.1):
    checking plugin <dll, a full path up to 2.0.x, a bare name on 2.1+>
    plugin <dll> (<data ver> <name> <plugin ver>) loaded correctly (handle N)
    plugin <dll> (<data ver> <name> <plugin ver>) reported as incompatible during query|load (handle N)
    plugin <dll> does not appear to be an SKSE plugin                     (VR, 2.0.x)
    plugin <dll> (<data ver> <name> <plugin ver>) <reason> <code> (handle N)   (2.1+ errors)
SKSE64 2.1+ prints every "loaded correctly" line together after all loading, not next to its "checking plugin"
line, so results are matched to plugins by DLL name, never by position. `plugin N allocated M bytes` has no
.dll and never matches.

The version is printed RAW (hex as logged): authors encode it differently (one plugin's 0.8.5 logs 00000850,
another's 1.5.10 logs 00010510, some always log 00000001), so decoding it would invent precision. Compare it
against a known build, not against a Nexus version string.

Accounting: every "checking plugin" line is one plugin, and the status rows must sum to that count. Result lines
that name no checked plugin are counted on their own row, printed even at zero -- a log this tool misreads must
not look like a clean one.

Exit: 0 read and consistent - 1 the rows do not sum (see ACCOUNTING MISMATCH) - 2 bad usage, or no log to read.
"""

from __future__ import annotations

import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

CHECK_RE = re.compile(r"^checking plugin (?P<dll>.+?\.dll)\s*$", re.I)
# The parenthesised version block is optional: VR and SKSE64 2.0.x print the "not an SKSE plugin" verdict without
# one. `plugin 12 allocated ...` has no .dll and never matches.
RESULT_RE = re.compile(
    r"^plugin (?P<dll>.+?\.dll) "
    r"(?:\((?P<data>[0-9A-Fa-f]{8}) (?P<name>.*) (?P<ver>[0-9A-Fa-f]{8})\) )?"
    r"(?P<status>.+?)(?: \(handle -?\d+\))?\s*$", re.I)
ERRCODE_RE = re.compile(r"^(?P<msg>.*\D) (?P<code>-?\d+)$")

LOADED = "loaded correctly"
NOT_SKSE = "does not appear to be an SKSE plugin"
NO_RESULT = "NO RESULT LINE"

# One log name per runtime. skse.log is the LE name; the folder lookup only finds it when an LE install is
# present, so listing it costs nothing.
LOG_NAMES = ("skse64.log", "sksevr.log", "skse.log")
LOADER_NAMES = ("skse64_loader.log", "sksevr_loader.log")
PRODUCT_RE = re.compile(r"^productVersionStr\s*=\s*(?P<value>\S+)", re.I)
DLL_RE = re.compile(r"^dll\s*=\s*(?P<value>.+?)\s*$", re.I)


def basename(dll):
    return re.split(r"[\\/]", dll)[-1]


def find_log():
    """(path or None, what was looked at, the other candidates)."""
    folder = _paths.resolve_dir("SKSE_LOG_DIR", "SKSE")[0]
    found = [folder / name for name in LOG_NAMES if (folder / name).is_file()]
    if not found:
        return None, "no %s in %s" % (" / ".join(LOG_NAMES), folder), [], folder
    found.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return found[0], str(folder), found[1:], folder


def loader_lines(folder):
    """The launcher's own record of the last launch as printed lines, or [] when the log is not there."""
    for name in LOADER_NAMES:
        path = folder / name
        if not path.is_file():
            continue
        try:
            lines = [line.strip() for line in path.read_text(encoding="utf-8", errors="replace").splitlines()]
        except OSError:
            return []
        head = next((line for line in lines if line), "")
        product = next((m.group("value") for m in (PRODUCT_RE.match(line) for line in lines) if m), "")
        dll = next((m.group("value") for m in (DLL_RE.match(line) for line in lines) if m), "")
        out = ["  loader         : %s  (the launcher's own record: it holds no plugin lines)" % name]
        if head:
            out.append("    %s" % head)
        if product or dll:
            out.append("    target product %s, dll %s" % (product or "?", basename(dll) if dll else "?"))
        return out
    return []


def classify(status):
    s = status.lower()
    if s == LOADED:
        return "loaded"
    if s.startswith("reported as incompatible"):
        return "incompatible"
    if s.startswith(NOT_SKSE.lower()):
        return "not an SKSE plugin"
    return "other error"


def parse(lines):
    """(rows in log order, orphan result lines, the "checking plugin" count, per-verdict counts).

    The verdict counter is kept as each result line is APPLIED -- independent of the rows -- so a plugin given
    two verdicts, or two plugins collapsed into one row, makes the totals disagree instead of hiding.
    """
    rows, by_name, orphans, checked, verdicts = [], {}, [], 0, Counter()
    for line in lines:
        m = CHECK_RE.match(line)
        if m:
            checked += 1
            row = {"dll": basename(m.group("dll")), "status": NO_RESULT, "kind": "no result line",
                   "name": "", "ver": "", "code": ""}
            rows.append(row)
            by_name[row["dll"].lower()] = row
            continue
        m = RESULT_RE.match(line)
        if not m:
            continue
        row = by_name.get(basename(m.group("dll")).lower())
        if row is None:
            orphans.append(line)
            continue
        status, code = m.group("status"), ""
        e = ERRCODE_RE.match(status)
        if e and status.lower() != LOADED:
            status, code = e.group("msg"), e.group("code")
        row.update(status=status, kind=classify(status), name=m.group("name") or "",
                   ver=m.group("ver") or "", code=code)
        verdicts[row["kind"]] += 1
    return rows, orphans, checked, verdicts


def usage(problem=""):
    """Print the usage problem and the docstring; the exit code for bad usage is 2."""
    if problem:
        print("ERROR: %s" % problem, file=sys.stderr)
    print(__doc__.strip())
    return 2


def read_args(argv):
    """(filter, log Path or None, None) or (None, None, exit code) after printing usage."""
    log, args, i = None, [], 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--log":
            if i + 1 >= len(argv):
                return None, None, usage("--log needs a path")
            log = Path(argv[i + 1])
            i += 2
        elif arg.startswith("-") and arg != "-":
            # An unknown flag taken as a filter silently matches nothing, which reads as "not installed".
            return None, None, usage("unknown option %s" % arg)
        else:
            args.append(arg)
            i += 1
    if len(args) > 1:
        return None, None, usage("one filter at a time, got %d: %s" % (len(args), " ".join(args)))
    return (args[0].lower() if args else ""), log, None


def main(argv):
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, OSError):
        pass

    if "-h" in argv or "--help" in argv:
        print(__doc__.strip())
        return 0

    flt, log, problem = read_args(argv)
    if problem is not None:
        return problem

    others, folder = [], None
    if log is None:
        log, where, others, folder = find_log()
        if log is None:
            print("ERROR: no SKSE log found (%s). Set SKSE_LOG_DIR or pass --log PATH." % where,
                  file=sys.stderr)
            return 2
    try:
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
        mtime = log.stat().st_mtime
    except OSError as e:
        print("ERROR: cannot read %s: %s" % (log, e), file=sys.stderr)
        return 2

    rows, orphans, checked, verdicts = parse(lines)
    age_h = (time.time() - mtime) / 3600.0
    print("SKSE log: %s" % log)
    print("  written %s (%.1f h ago) -- it describes the LAST launch, not the files on disk now"
          % (time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime)), age_h))
    for other in others:
        print("  also present, not read: %s" % other)
    for line in loader_lines(folder or log.parent):
        print(line)

    shown = [r for r in rows if flt in r["dll"].lower() or flt in r["name"].lower()]
    for r in shown:
        status = r["status"] + (" (code %s)" % r["code"] if r["code"] else "")
        print("  %-45s %-9s %-44s %s" % (r["dll"], r["ver"], status, r["name"]))

    kinds = Counter(verdicts)
    kinds["no result line"] = sum(1 for r in rows if r["status"] == NO_RESULT)
    order = ("loaded", "incompatible", "not an SKSE plugin", "other error", "no result line")
    print("  -- %d shown of %d checked" % (len(shown), checked))
    for kind in order:
        print("     %-20s: %d" % (kind, kinds.get(kind, 0)))
    print("     %-20s: %d  (result lines naming no checked DLL)" % ("unmatched results", len(orphans)))
    total = sum(kinds.get(kind, 0) for kind in order)
    if total != checked:
        print("  ACCOUNTING MISMATCH: the rows sum to %d for %d checked plugins (a DLL checked twice, or given"
              " two verdicts); the table above is not trustworthy" % (total, checked))
        return 1
    print("  RESULT: OK (rows sum to %d checked)" % checked)
    if kinds.get("not an SKSE plugin"):
        print("  note: 'not an SKSE plugin' is expected for helper DLLs some mods ship beside their plugin"
              " (e.g. a crash logger's msdia140.dll); for a real SKSE plugin it means it never loaded.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
