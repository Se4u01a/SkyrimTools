"""papyrus_triage -- turn a Papyrus.N.log into a bucketed, script-attributed triage.

Ported from skyrim-ai-assistant-toolkit (c) 2026 WingedGuardian, MIT License.

A hand-rolled `grep | sort | uniq -c` cannot notice that it dropped a shape. Two properties are non-negotiable
here:

  1. The rows SUM TO THE INPUT: every entry is accounted for.
  2. The unclassified / "not shown" row PRINTS EVEN WHEN IT IS ZERO. Silence about the remainder is how a
     triage tool starts lying.

Both are checked against INDEPENDENTLY COUNTED totals, incremented in the bucketing loop itself -- a remainder
computed as `total - shown` and then checked against the total is `x == x`, a check that can never fail.

An entry is MULTI-LINE: Papyrus.1.log is ~37% continuation lines (`stack:` frames and their file/line records)
belonging to the entry above. The unit of accounting is the ENTRY, so a line-based sum is wrong by that margin.

Severity is spelled BOTH ways in the same file (`warning:` and `WARNING:`), so the match is case-insensitive.
Known-benign shapes are LABELLED, never dropped: the job is to rank attention, not to decide what the reader
may see.

    python papyrus_triage.py [logfile] [--top N] [--all]

    logfile   default: the newest Papyrus.*.log in Logs/Script of the first game folder under Documents/My Games
              (SKYRIM_DOCUMENTS_DIR or PAPYRUS_LOG_DIR overrides that)
    --top N   shapes printed per severity (default 15); --all prints every shape

Exit: 0 triaged - 1 an accounting check failed (see RESULT) - 2 bad usage, or no Papyrus log to read.
"""

from __future__ import annotations

import os
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

ENTRY_RE = re.compile(r"^\[\d{2}/\d{2}/\d{4} - [^\]]+\]\s*(.*)$")
SEVERITY_RE = re.compile(r"^(error|warning)\s*:\s*(.*)$", re.I)
SEVERITIES = ("error", "warning", "info")
LOG_NAME = "Papyrus.*.log"
STALE_DAYS = 7

# Normalisation applied before bucketing. Each pattern collapses an instance-specific token so identical shapes
# group; anything carrying signal (plugin names, script names) is deliberately left alone.
NORMALISERS = [
    (re.compile(r"\(\s*[0-9A-Fa-f]{8}\s*\)"), "(FORMID)"),
    (re.compile(r"\[\s*[0-9A-Fa-f]{8}\s*\]"), "[FORMID]"),
    (re.compile(r"\b[0-9A-Fa-f]{8}\b"), "FORMID"),
    (re.compile(r"::temp\d+"), "::tempN"),
    (re.compile(r"::NoneVar\d*"), "::NoneVarN"),
    (re.compile(r"\bLine \d+"), "Line N"),
    (re.compile(r"\b\d{3,}\b"), "N"),
]

# Known noise, with the reason. LABELLED in the output, never removed -- a triage tool that silently drops rows
# is indistinguishable from one that missed them. These are vanilla script shapes, not rulings from any
# knowledgebase, so they stay baked in.
BENIGN = [
    (re.compile(r"dunKilkreathCrystalNodeSCRIPT|dunLabyrinthianMazeTabletScript"),
     "vanilla dungeon script, unbound property on an unloaded cell"),
    (re.compile(r"Cannot check to for a None item to be equipped"),
     "vanilla equip check on a None item"),
]

# Attribution, most specific first. The quoted-".psc" form appears only in stack continuations; the unquoted
# forms are what the runtime log actually emits and dominate real entries, so both are needed or attribution is
# mostly "-".
ATTRIBUTORS = [
    re.compile(r'File "([^"]+)" does not exist', re.I),
    re.compile(r'"([A-Za-z0-9_]+\.psc)"'),
    re.compile(r"on script ([A-Za-z0-9_]+)", re.I),
    re.compile(r"on unlinked object ([A-Za-z0-9_]+)", re.I),
    re.compile(r"used in ([A-Za-z0-9_]+)\."),
    re.compile(r"\bbind script ([A-Za-z0-9_]+)", re.I),
    re.compile(r"Script ([A-Za-z0-9_]+) cannot be bound", re.I),
    re.compile(r"variable ([A-Za-z0-9_:]+) on script", re.I),
]


def normalise(msg):
    out = msg
    for pattern, repl in NORMALISERS:
        out = pattern.sub(repl, out)
    return out.strip()


def attribute(msg, stack):
    for pattern in ATTRIBUTORS:
        m = pattern.search(msg)
        if m:
            return m.group(1)
    for line in stack:
        m = re.search(r'"([A-Za-z0-9_]+\.psc)"', line)
        if m:
            return m.group(1)
    return "-"


def benign_reason(shape):
    for pattern, reason in BENIGN:
        if pattern.search(shape):
            return reason
    return None


def parse(path):
    """(entries, lines read, continuation lines).

    An entry is (severity, message, stack_lines); a line that is not timestamped attaches to the entry above it
    and is counted as a continuation, even when there is no entry above it to attach to.
    """
    entries = []
    total = 0
    undated = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        total += 1
        m = ENTRY_RE.match(line)
        if not m:
            undated += 1
            if entries:
                entries[-1][2].append(line)
            continue
        body = m.group(1)
        sm = SEVERITY_RE.match(body)
        if sm:
            entries.append((sm.group(1).lower(), sm.group(2), []))
        else:
            entries.append(("info", body, []))
    return entries, total, undated


def bucket(subset):
    """(shapes, who, bucketed, failed) -- grouped by normalised shape.

    `bucketed` and `failed` are counted in this loop, independently of len(subset), so the caller's accounting
    check is a real comparison rather than an identity.
    """
    shapes = Counter()
    who = defaultdict(Counter)
    bucketed = 0
    failed = 0
    for msg, stack in subset:
        try:
            shape = normalise(msg)
            shapes[shape] += 1
            who[shape][attribute(msg, stack)] += 1
            bucketed += 1
        except Exception:                             # a shape that cannot be bucketed is a row, not a crash
            failed += 1
    return shapes, who, bucketed, failed


def usage(problem=""):
    """Print the usage problem and the docstring; the exit code for bad usage is 2."""
    if problem:
        print("ERROR: %s" % problem, file=sys.stderr)
    print(__doc__.strip())
    return 2


def read_args(argv):
    """(logfile or None, opts, None) or (None, None, exit code) after printing usage."""
    opts = {"top": 15, "all": False}
    args, i = [], 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--top":
            if i + 1 >= len(argv):
                return None, None, usage("--top needs a value")
            try:
                opts["top"] = int(argv[i + 1])
            except ValueError:
                return None, None, usage("--top needs a whole number, got %r" % argv[i + 1])
            if opts["top"] < 0:
                return None, None, usage("--top must be 0 or more")
            i += 2
        elif arg == "--all":
            opts["all"] = True
            i += 1
        elif arg.startswith("-") and arg != "-":
            return None, None, usage("unknown option %s" % arg)
        else:
            args.append(arg)
            i += 1
    if len(args) > 1:
        return None, None, usage("one log at a time, got %d: %s" % (len(args), " ".join(args)))
    return (args[0] if args else None), opts, None


def main(argv):
    # The log can contain any codepoint a mod author used and Windows stdout is cp1252 here: a CJK or Cyrillic
    # name would otherwise abort the report mid-write with UnicodeEncodeError and no RESULT line.
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, OSError):
        pass

    if "-h" in argv or "--help" in argv:
        print(__doc__.strip())
        return 0

    logfile, opts, problem = read_args(argv)
    if problem is not None:
        return problem

    auto_selected = not logfile
    if logfile:
        path = Path(logfile)
    else:
        log_dir = _paths.resolve_dir("PAPYRUS_LOG_DIR", "Logs/Script")[0]
        candidates = sorted(log_dir.glob(LOG_NAME), key=lambda p: p.stat().st_mtime, reverse=True)
        if not candidates:
            print("No %s found in %s" % (LOG_NAME, log_dir), file=sys.stderr)
            print("Launch the game with a Papyrus log enabled, or pass the log as an argument.", file=sys.stderr)
            return 2
        path = candidates[0]

    if not path.is_file():
        print("Not a file: %s" % path, file=sys.stderr)
        return 2

    age_days = None
    if auto_selected:
        age_days = (time.time() - path.stat().st_mtime) / 86400.0

    entries, total_lines, undated = parse(path)

    # --- denominator FIRST, before any finding -------------------------------
    print("=" * 78)
    print("PAPYRUS TRIAGE  --  %s" % path.name)
    print("=" * 78)
    print("log                  : %s" % path)
    if auto_selected:
        print("  (the newest %s of the %d found there)" % (LOG_NAME, len(candidates)))
    print("lines read           : %d" % total_lines)
    print("timestamped entries  : %d" % len(entries))
    print("continuation lines   : %d   (stack traces and their file/line records, attached to the entry above)"
          % undated)
    print()

    if age_days is not None:
        marker = "   <-- STALE: older than %d days" % STALE_DAYS if age_days > STALE_DAYS else ""
        print("log age        : %.1f days%s" % (age_days, marker))
        print()

    by_sev = Counter(sev for sev, _, _ in entries)
    unexpected = {s: n for s, n in by_sev.items() if s not in SEVERITIES}

    print("by severity:")
    printed_total = 0
    for sev in SEVERITIES:
        n = by_sev.get(sev, 0)
        printed_total += n                        # sum only what is actually shown
        print("  %-9s: %d" % (sev, n))
    for sev, n in sorted(unexpected.items()):
        printed_total += n
        print("  %-9s: %d   <-- severity outside the expected set" % (sev, n))
    print("  %s  %s" % ("-" * 9, "-" * 6))
    sev_ok = printed_total == len(entries)
    # NOTE: sev_ok cannot fail by construction -- SEVERITY_RE only yields error/warning and everything else
    # defaults to info, so `unexpected` is always empty. Kept as a cheap labelled assertion: the REAL guards are
    # the bucket() accounting below (which can genuinely go red) and the staleness check above.
    print("  %-9s: %d   [%s vs %d entries]" % ("TOTAL", printed_total, "OK" if sev_ok else "MISMATCH",
                                              len(entries)))
    print("             (internal only: SEVERITY_RE yields error/warning and everything")
    print("              else defaults to info, so these rows always sum. Cannot go red.)")
    if not sev_ok:
        print("  !! the printed severity rows do not sum to the entry count")
    print()

    exit_code = 0 if sev_ok else 1

    # --- buckets, per severity ----------------------------------------------
    for sev in ("error", "warning"):
        subset = [(msg, stack) for s, msg, stack in entries if s == sev]
        if not subset:
            continue
        shapes, who, bucketed, failed = bucket(subset)
        in_buckets = sum(shapes.values())

        print("%s buckets  (%d entries, %d distinct shapes)" % (sev.upper(), len(subset), len(shapes)))
        print("  %6s  %-34s  shape" % ("count", "attribution"))
        rows = shapes.most_common() if opts["all"] else shapes.most_common(opts["top"])
        shown = 0
        for shape, count in rows:
            shown += count
            attrib = who[shape].most_common(1)[0][0]
            reason = benign_reason(shape)
            tag = "  [benign: " + reason + "]" if reason else ""
            text = shape if len(shape) <= 96 else shape[:93] + "..."
            print("  %6d  %-34s  %s%s" % (count, attrib[:34], text, tag))

        # The remainder comes from the bucket totals, NOT from (len(subset) - shown), so the sum below compares
        # two independently derived numbers.
        remainder = in_buckets - shown
        print("  %6d  %-34s  (not shown above)" % (remainder, "-"))
        if failed:
            print("  %6d  %-34s  (FAILED TO BUCKET)" % (failed, "-"))
        print("  %s" % ("-" * 6))
        accounted = in_buckets + failed
        ok = accounted == len(subset) and bucketed == in_buckets
        print("  %6d  ACCOUNTED FOR   [%s vs %d %s entries]" % (accounted, "OK" if ok else "MISMATCH",
                                                                len(subset), sev))
        if not ok:
            print("  !! %d %s entries are unaccounted for" % (len(subset) - accounted, sev))
            exit_code = 1
        print()

    print("RESULT: OK" if exit_code == 0 else "RESULT: ACCOUNTING MISMATCH")
    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
