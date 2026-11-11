"""crash_triage -- reduce CrashLogger / trainwreck crash dumps to ranked signatures, and say which are known.

Ported from skyrim-ai-assistant-toolkit (c) 2026 WingedGuardian, MIT License.

A dump is a short header plus a few thousand lines of raw stack. What identifies the crash is the exception
line and the top of the probable call stack; this turns a folder of dumps into a ranked signature table, so a
crash seen four times is recognised instead of investigated four times.

    python crash_triage.py [dir-or-file] [--frames N] [--all] [--known FILE]

    dir-or-file   one dump, or a folder of dumps. Default: the SKSE folder of the first game folder under
                  Documents/My Games; SKYRIM_DOCUMENTS_DIR or SKSE_CRASH_DIR overrides that.
    --frames N    stack frames printed under an unknown signature (default 4)
    --all         print every signature, not just the top 15
    --known FILE  one signature per line, "MODULE+OFFSET STATUS note"; '#' or ';' starts a comment;
                  STATUS is ACCEPTED or KNOWN and its note is printed under the signature.
                  Without --known every signature prints as UNKNOWN.

Dumps read: <folder>/crash-*.txt, <folder>/crash-*.log, and <folder>/Crashlogs/*.log (CrashLoggerSSE 1.15+
writes its dumps into that subfolder under a timestamp name). A folder named Crashlogs is read whole, whatever
its files are called. A file named like a dump that matches neither shape is reported as a near miss instead of
being dropped.

Accounting is the point of this tool, not decoration: every file lands in exactly one bucket, the buckets must
sum to the file count, the "not shown" row prints even when it is zero, and dumps the parser did not understand
-- or understood but got no stack frames from -- are counted and called out. A parser that stopped matching the
format must not read as a clean install.

Exit: 0 triaged - 1 see RESULT (accounting, parser degraded, input set incomplete) - 2 bad usage or no dumps.
.NET Script Framework dumps are a different format: counted as unparsed, never guessed at.
"""

from __future__ import annotations

import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

# "Unhandled exception "TYPE" at 0xADDR MODULE+OFFSET<TAB>instruction |  symbol)"
# The quoted TYPE is optional: CrashLogger names only a fixed list of codes, and any other code (__fastfail,
# 0xC0000409, ... on 1.24.0) prints no type at all -- requiring the quotes counted those dumps as "no exception".
# MODULE+OFFSET is optional too: a jump into no loaded module leaves nothing to attribute and the line ends
# after the address. Requiring it made such a dump permanently unparseable, reported as a dump we did not read.
EXC_RE = re.compile(
    r'^Unhandled exception(?: "(?P<type>[^"]+)"|(?=\s+at\s+0x))'
    r'(?:\s+at\s+0x(?P<addr>[0-9A-Fa-f]+))?'
    r'(?:\s+(?P<module>[^\s+]+)\+(?P<offset>[0-9A-Fa-f]+))?'
    r'\s*(?P<instr>[^|]*)'
    r'(?:\|\s*(?P<symbol>.*?)\)?\s*)?$'
)
# CrashLoggerSSE 1.2x marks each frame [P]robable or [S]tack-scan; older builds emit no marker. The frame index
# is padded ("[0 ]") by trainwreck, so whitespace before the closing bracket has to be allowed -- without it
# every trainwreck dump parsed with zero frames and the frames guard blamed the stack header.
FRAME_RE = re.compile(
    r"^\s*\[\s*\d+\s*\]"
    r"(?:\[(?P<kind>[PS])\])?"
    r"\s+0x[0-9A-Fa-f]+\s+(?P<mod>[^\s+]+)\+(?P<off>[0-9A-Fa-f]+)"
)
# CrashLoggerSSE writes `crash-*.log`, older builds (and Crash Log Toolkit) write `crash-*.txt`; both live in the
# same folder, so matching one extension does not fail -- it reports a confident total made of one half.
# `CrashLogger.log` is the plugin's OWN log and is excluded by the `crash-` prefix.
CRASH_NAME_RE = re.compile(r"^crash-.+\.(txt|log)$", re.I)
# CrashLoggerSSE 1.15+ writes <SKSE>/Crashlogs/<timestamp>.log. A dump folder nobody reads is the same failure
# as an extension nobody matches, so the subfolder is read as well.
DUMP_DIR_NAMES = ("crashlogs",)
DUMP_NAME_RE = re.compile(r"^.+\.(txt|log)$", re.I)
# Near-miss detector: keys on the `crash-` PREFIX, not the word "crash" anywhere in the name, because the looser
# form fires on healthy logs (LeveledListCrashPrevention.log, CrashLogger.log) and a guard that trips on healthy
# input gets ignored. Scoped to the shape that actually failed: a real dump whose extension drifted out.
CRASH_PREFIX_RE = re.compile(r"^crash[-_]", re.I)
# A folder whose patterns broke would otherwise print one line per file. The COUNT is the finding; the names are
# a sample.
LIST_CAP = 10

# The runtime line: "Skyrim SSE v1.5.97" (CrashLoggerSSE), "SkyrimSE v1.5.97" (trainwreck), "Skyrim Special
# Edition v1.6.1170", "Skyrim VR v1.4.15". The pattern ported from the original knew only two of these, so a
# trainwreck or GOG dump reported no game build at all.
VERSION_RE = re.compile(r"^(?P<name>Skyrim[^0-9]*?)\s*v?(?P<ver>\d+(?:\.\d+)+)\s*$", re.I)

# Where the call stack section ends: the next ALL-CAPS header ("REGISTERS:", "STACK:", "MODULES:", "STACK SCAN:").
# Both loggers put the disassembly of each frame on its OWN line under the frame, so the reader cannot stop at
# the first line that is not a frame -- that kept only frame [0] of every dump and made "top N frames" a lie.
SECTION_RE = re.compile(r"^\s*[A-Z][A-Z0-9 _()/-]*:\s*$")
MAX_FRAME_LINES = 400

# A C++ throw reports the THROW SITE on the exception line -- the same KERNELBASE address for every C++ crash on
# the machine. What distinguishes them lives in the `C++ EXCEPTION:` block, so parse it.
CPP_FIELD_RE = re.compile(r"^\s*(?P<field>Type|Info|Throw Location)\s*:\s*(?P<value>.+?)\s*$")

STATUSES = ("ACCEPTED", "KNOWN")


def key(module, offset):
    """(module, offset) as used for --known lookups: module lowercased, offset upper hex without 0x or zeros.

    Normalising BOTH sides is what makes a hand-written known list usable: a dump prints `SkyrimSE.exe+0688493`
    and `SkyrimSE.exe+0C6E1A5`, a known line may say `0x688493`. The table still displays the offset as logged.
    """
    hex_digits = offset.strip().lower()
    if hex_digits.startswith("0x"):
        hex_digits = hex_digits[2:]
    hex_digits = hex_digits.lstrip("0") or "0"
    return (module.strip().lower(), hex_digits.upper())


def load_known(path):
    """(rulings, count of lines that did not parse) from a --known file.

    A ruling is keyed by module AND offset: an offset means nothing outside its module, so `SomeMod.dll+0B84F05`
    must not be told "ACCEPTED, do not re-investigate".
    """
    rulings, bad = {}, 0
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line[0] in "#;":
            continue
        parts = line.split(None, 2)
        if len(parts) < 2 or "+" not in parts[0] or parts[1].upper() not in STATUSES:
            bad += 1
            continue
        module, _, offset = parts[0].rpartition("+")
        rulings[key(module, offset)] = (parts[1].upper(), parts[2] if len(parts) > 2 else "")
    return rulings, bad


def known(rulings, rec):
    """(status, note) for one parsed crash: ("UNKNOWN", "") unless its module AND offset have a ruling."""
    return rulings.get(key(rec["module"], rec["offset"]), ("UNKNOWN", ""))


def parse(path):
    """One dict for a dump, or None if it has no exception line."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()

    exc = None
    for line in lines[:40]:
        m = EXC_RE.match(line.strip())
        if m:
            exc = m
            break
    if not exc:
        return None

    game_ver = ""
    for line in lines[:5]:
        m = VERSION_RE.match(line.strip())
        if m:
            game_ver = m.group("ver")
            break

    # CrashLoggerSSE 1.2x heads the stack "CALL STACK ([P]robable / [S]tack scan):", older builds wrote
    # "PROBABLE CALL STACK". When frames are marked, keep only [P]: an [S] frame is a stack scan and is not solid
    # enough to key a signature on.
    frames = []
    try:
        start = next(i for i, line in enumerate(lines)
                     if line.startswith("PROBABLE CALL STACK") or line.startswith("CALL STACK"))
        for line in lines[start + 1:start + 1 + MAX_FRAME_LINES]:
            frame = FRAME_RE.match(line)
            if frame:
                if frame.group("kind") != "S":
                    frames.append("%s+%s" % (frame.group("mod"), frame.group("off")))
                continue
            if SECTION_RE.match(line):
                break                                  # the stack section ended; later frames belong to no crash
    except StopIteration:
        pass

    cpp = {}
    # 200 lines, not 80: MEASURED on real dumps, the pre-stack preamble reaches line 79 in one of them, and
    # overrunning the window silently blanks cpp_info -- which collapses every C++ crash onto the shared throw
    # site, the exact merge this parsing exists to prevent.
    for i, line in enumerate(lines[:200]):
        if line.strip().startswith("C++ EXCEPTION"):
            for sub in lines[i + 1:i + 8]:
                field = CPP_FIELD_RE.match(sub)
                if field:
                    cpp[field.group("field")] = field.group("value")
                elif sub.strip():
                    break
            break

    instr = (exc.group("instr") or "").strip()
    etype = exc.group("type")
    if not etype:
        # An unnamed code. `int 0x29` is the __fastfail instruction (Zydis Intel syntax; `int 29h` elsewhere).
        etype = ("__fastfail" if re.fullmatch(r"int\s+(?:0x29|29h)", instr, re.I)
                 else "(unnamed exception code)")

    return {
        "file": path.name,
        "type": etype,
        # No module means the address is all we have; naming it that way groups those dumps together instead of
        # pretending to a module.
        "module": exc.group("module") or "(no module)",
        "offset": (exc.group("offset") or exc.group("addr") or "?").upper(),
        "instr": instr,
        "symbol": (exc.group("symbol") or "").strip().rstrip(")"),
        "game": game_ver,
        "frames": frames,
        # A truncated CrashLogger write (tens of lines, no stack, no registers) has no stack section to read, so
        # counting it as "frames missing" turns healthy input into a format-break verdict. REGISTERS is the
        # marker that the dump got that far.
        "complete": any(line.startswith("REGISTERS") for line in lines),
        "cpp_type": cpp.get("Type", ""),
        "cpp_info": cpp.get("Info", ""),
        "cpp_throw": cpp.get("Throw Location", ""),
    }


def dump_subdir(folder):
    """CrashLoggerSSE's own dump subfolder under this folder, or None."""
    try:
        return next((p for p in folder.iterdir() if p.is_dir() and p.name.lower() in DUMP_DIR_NAMES), None)
    except OSError:
        return None


def collect(folder):
    """(dumps in the folder, dumps in its Crashlogs subfolder, that subfolder, every file, near misses).

    A folder that IS a dump folder (named Crashlogs) is read whole: what it holds is dumps whatever they are
    called, and refusing them would answer "no dumps" about the one folder where dumps certainly are.
    """
    population = [p for p in folder.iterdir() if p.is_file()]
    pattern = DUMP_NAME_RE if folder.name.lower() in DUMP_DIR_NAMES else CRASH_NAME_RE
    primary = sorted(p for p in population if pattern.match(p.name))
    sub = dump_subdir(folder)
    extra = sorted(p for p in sub.iterdir() if p.is_file() and DUMP_NAME_RE.match(p.name)) if sub else []
    read = primary + extra
    population += extra
    seen = {str(p) for p in read}
    near = sorted(p.name for p in population if str(p) not in seen and CRASH_PREFIX_RE.match(p.name))
    return primary, extra, sub, population, near


def patterns(folder):
    """How this folder's dumps are chosen, for the two lines that have to say what was and was not read."""
    if folder.name.lower() in DUMP_DIR_NAMES:
        return "*.log / *.txt in a dump folder"
    return "crash-*.txt / crash-*.log"


def usage(problem=""):
    """Print the usage problem and the docstring; the exit code for bad usage is 2."""
    if problem:
        print("ERROR: %s" % problem, file=sys.stderr)
    print(__doc__.strip())
    return 2


def read_args(argv):
    """(target or None, opts, None) or (None, None, exit code) after printing usage."""
    opts = {"frames": 4, "all": False, "known": None}
    args, i = [], 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--frames", "--known"):
            if i + 1 >= len(argv):
                return None, None, usage("%s needs a value" % arg)
            if arg == "--frames":
                try:
                    opts["frames"] = int(argv[i + 1])
                except ValueError:
                    return None, None, usage("--frames needs a whole number, got %r" % argv[i + 1])
                if opts["frames"] < 1:
                    return None, None, usage("--frames must be 1 or more")
            else:
                opts["known"] = argv[i + 1]
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
        return None, None, usage("one target at a time, got %d: %s" % (len(args), " ".join(args)))
    return (args[0] if args else None), opts, None


def main(argv):
    # A dump can carry any codepoint a mod author used, and Windows stdout is cp1252 here: an unprintable name
    # would abort the report mid-write with UnicodeEncodeError and no RESULT line.
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, OSError):
        pass

    if "-h" in argv or "--help" in argv:
        print(__doc__.strip())
        return 0

    target_arg, opts, problem = read_args(argv)
    if problem is not None:
        return problem

    rulings, known_bad = {}, 0
    if opts["known"]:
        try:
            rulings, known_bad = load_known(opts["known"])
        except OSError as e:
            print("ERROR: cannot read --known %s: %s" % (opts["known"], e), file=sys.stderr)
            return 2
        if known_bad:
            print("--known: %d line(s) are not 'MODULE+OFFSET STATUS note' (skipped)" % known_bad,
                  file=sys.stderr)

    target = Path(target_arg) if target_arg else _paths.resolve_dir("SKSE_CRASH_DIR", "SKSE")[0]
    primary, extra, sub, population, near = [], [], None, [], []
    if target.is_file():
        files = [target]
    elif target.is_dir():
        try:
            primary, extra, sub, population, near = collect(target)
        except OSError as e:
            print("ERROR: cannot list %s: %s" % (target, e), file=sys.stderr)
            return 2
        files = primary + extra
    else:
        print("Not a file or directory: %s" % target, file=sys.stderr)
        print("Launch the game at least once, or pass a dump or a folder of dumps as an argument.",
              file=sys.stderr)
        return 2
    if not files:
        # "None found" and "none MATCHED" are different answers, and printing the first when the second is true
        # is the near-miss failure in its purest form: the reader is told the folder is empty of dumps while
        # dumps sit in it under a shape the pattern does not cover.
        print("No %s found in %s" % (patterns(target), target), file=sys.stderr)
        if near:
            print("  but %d file(s) there carry the crash-/crash_ prefix and did NOT match the extension "
                  "pattern -- widen CRASH_NAME_RE if these are dumps:" % len(near), file=sys.stderr)
            for name in near[:LIST_CAP]:
                print("    !! %s" % name, file=sys.stderr)
            if len(near) > LIST_CAP:
                print("    ... and %d more" % (len(near) - LIST_CAP), file=sys.stderr)
        return 2

    parsed, unreadable, no_exception = [], [], []
    for path in files:
        try:
            rec = parse(path)
        except Exception as e:                        # a dump that cannot be read is a bucket, never a traceback
            unreadable.append((path.name, str(e)))
            continue
        (parsed if rec else no_exception).append(rec if rec else path.name)

    # --- denominator FIRST ---------------------------------------------------
    print("=" * 78)
    print("CRASH TRIAGE  --  %d dump(s) in %s" % (len(files), target if target.is_dir() else target.parent))
    print("=" * 78)
    if target.is_dir():
        print("files in folder : %d" % len(population))
        print("  matched       : %d   (%s)" % (len(primary), patterns(target)))
        if sub is not None:
            print("  in %-11s: %d   (CrashLoggerSSE 1.15+ writes <timestamp>.log there)" % (sub.name, len(extra)))
        print("  near misses   : %d%s" % (len(near),
                                          "   <-- LOOK: named like a dump, not matched by the pattern"
                                          if near else ""))
        for name in near[:LIST_CAP]:
            print("    !! %s" % name)
        if len(near) > LIST_CAP:
            print("    ... and %d more" % (len(near) - LIST_CAP))
    print("dumps found     : %d" % len(files))
    print("  parsed        : %d" % len(parsed))
    print("  no exception  : %d" % len(no_exception))
    print("  unreadable    : %d" % len(unreadable))

    # UNPARSED RATIO. The accounting line balances by construction, so it cannot say the parser stopped
    # understanding its input: on CrashLoggerSSE 1.23.1 this tool once read 1 of 7 real dumps and printed
    # RESULT: OK. A high unparsed share is the format-agnostic symptom. Thresholds picked against real data: the
    # 1.2x break was 86% unparsed, a healthy install sits at 0-4%. BOTH >25% and at least 2 keeps an isolated
    # oddity quiet and a real break loud.
    unparsed = len(no_exception) + len(unreadable)
    unparsed_pct = (100.0 * unparsed / len(files)) if files else 0.0
    # Nothing parsed at all is the WORST break, and it used to be the one case that printed OK: 6-of-7 unparsed
    # said DEGRADED while 7-of-7 said OK -- the worse the break, the cleaner the report. It also frees single-file
    # mode, where unparsed >= 2 can never hold.
    total_break = unparsed > 0 and not parsed

    # FRAMES COVERAGE. `unparsed` only counts dumps whose EXCEPTION LINE failed; a changed stack header leaves
    # every dump parsed with zero frames and no complaint. One dump lacking frames is ordinary (a jump with no
    # return chain to walk); EVERY complete dump lacking them is the header having moved.
    complete = [r for r in parsed if r["complete"]]
    frameless = sum(1 for r in complete if not r["frames"])
    frames_broken = len(complete) >= 2 and frameless == len(complete)

    parse_degraded = total_break or (unparsed >= 2 and unparsed_pct > 25.0) or frames_broken

    # Two tiers, because silence is the thing to avoid, not the verdict. A non-zero count below the gate used to
    # print bare -- "1/2 (50%)" above RESULT: OK -- with nothing saying those bytes went unread.
    if total_break or (unparsed >= 2 and unparsed_pct > 25.0):
        unparsed_note = "   <-- the parser is not understanding these dumps"
    elif unparsed:
        # Name the clause that actually held it back: the gate is a conjunction, and telling the reader "too few
        # to call a format change" at 4-of-20 sends them to lower a floor that is not the cause.
        why = ("too few to call a format change" if unparsed < 2
               else "only %.0f%% of the set, under the 25%% mark" % unparsed_pct)
        unparsed_note = ("   <-- NOT read; %s, so the signatures below cover only the parsed ones" % why)
    else:
        unparsed_note = ""
    print("  unparsed      : %d/%d (%.0f%%)%s" % (unparsed, len(files), unparsed_pct, unparsed_note))

    # THE FRAMES DENOMINATOR. `frameless` used to print nowhere at all, so a single complete dump whose stack
    # header moved was reported as an UNKNOWN crash "worth looking at" with no frames and RESULT: OK.
    if frames_broken:
        frames_note = "   <-- NOT ONE of them did; the stack header or frame syntax has changed"
    elif frameless and len(complete) < 2:
        frames_note = ("   <-- too few complete dumps to call a format change; a jump with no return chain "
                       "looks exactly like this")
    elif frameless:
        frames_note = ("   <-- the rest did, so this is not a format change; those dumps contribute no stack "
                       "to the signatures below")
    else:
        frames_note = ""
    print("  with frames   : %d/%d complete dump(s)%s" % (len(complete) - frameless, len(complete), frames_note))

    games = Counter(r["game"] for r in parsed if r["game"])
    if not games:
        game_note = "(not named in the dumps)"
    elif len(games) == 1:
        game_note = next(iter(games))
    else:
        game_note = "mixed (" + ", ".join("%s x%d" % (v, n) for v, n in sorted(games.items())) + ")"
    print("  game version  : %s" % game_note)

    accounted = len(parsed) + len(no_exception) + len(unreadable)
    ok = accounted == len(files)
    print("  " + "-" * 14)
    print("  accounted     : %d   [%s vs %d found]" % (accounted, "OK" if ok else "MISMATCH", len(files)))
    for name, err in unreadable:
        print("    !! %s: %s" % (name, err))
    print()
    if opts["known"]:
        print("known list      : %s (%d signature(s)%s)" % (
            opts["known"], len(rulings), ", %d line(s) skipped" % known_bad if known_bad else ""))
    else:
        print("known list      : (none: pass --known FILE to label already-ruled crashes)")
    print()

    # When two problems are present the verdict must name both: the verdict line is the part people read, and a
    # reader pointed at a parser problem has no reason to suspect the input set was short as well.
    also_near = (" ALSO: %d file(s) carry the crash-/crash_ prefix but did not match the pattern, so the input "
                 "set is short too -- see the near-miss list above." % len(near) if near else "")
    also_frames = (" ALSO: every dump that DID parse yielded zero stack frames, so the stack header or frame "
                   "syntax has moved as well -- the signatures above carry no call stacks." if frames_broken else "")

    if parse_degraded and not parsed:
        print("RESULT: PARSER DEGRADED -- none of the %d dump(s) could be parsed, so nothing above is a report "
              "on their contents. Either the format moved -- compare one against EXC_RE -- or these files are "
              "not crash dumps at all.%s" % (len(files), also_near))
        return 1

    if not parsed:
        print("RESULT: OK" if ok else "RESULT: ACCOUNTING MISMATCH")
        return 0 if ok else 1

    # --- signatures ---------------------------------------------------------
    sigs = Counter()
    detail = {}
    dates = defaultdict(list)
    for rec in parsed:
        sig = "%s+%s" % (rec["module"], rec["offset"])
        if rec.get("cpp_info"):
            sig += "  %s" % rec["cpp_info"]
        sigs[sig] += 1
        detail.setdefault(sig, rec)
        dates[sig].append(rec["file"].replace("crash-", "").replace(".txt", "").replace(".log", ""))

    print("SIGNATURES  (%d crashes, %d distinct)" % (len(parsed), len(sigs)))
    rows = sigs.most_common() if opts["all"] else sigs.most_common(15)
    shown = 0
    for sig, count in rows:
        shown += count
        rec = detail[sig]
        status, note = known(rulings, rec)
        tag = {"ACCEPTED": "[ACCEPTED - do not re-investigate]", "KNOWN": "[known]"}.get(status, "[** UNKNOWN **]")
        print("\n  %d x  %s   %s" % (count, sig, tag))
        print(("        %s  %s" % (rec["type"], rec["instr"])).rstrip())
        if rec.get("cpp_type") or rec.get("cpp_info"):
            print(("        C++    : %s %s" % (rec.get("cpp_type", ""), rec.get("cpp_info", ""))).rstrip())
            if rec.get("cpp_throw"):
                print("        throw  : %s" % rec["cpp_throw"])
        if rec["symbol"]:
            print("        symbol : %s" % rec["symbol"])
        if note:
            print("        note   : %s" % note)
        print("        seen   : %s" % ", ".join(sorted(dates[sig])))
        if status == "UNKNOWN" and rec["frames"]:
            print("        top %d frames:" % opts["frames"])
            for frame in rec["frames"][:opts["frames"]]:
                print("          %s" % frame)

    remainder = len(parsed) - shown
    print("\n  %d x  (signatures not shown above)" % remainder)
    sig_total = sum(sigs.values())
    sig_ok = sig_total == len(parsed)
    print("  " + "-" * 6)
    print("  %d accounted   [%s vs %d parsed crashes]" % (sig_total, "OK" if sig_ok else "MISMATCH", len(parsed)))

    unknown = sum(c for s, c in sigs.items() if known(rulings, detail[s])[0] == "UNKNOWN")
    print("\n  known/accepted : %d" % (len(parsed) - unknown))
    print("  UNKNOWN        : %d   <-- the ones worth looking at" % unknown)

    all_ok = ok and sig_ok and not parse_degraded and not near
    unparsed_clause = unparsed >= 2 and unparsed_pct > 25.0
    if parse_degraded and frames_broken and not unparsed_clause:
        print("\nRESULT: PARSER DEGRADED -- all %d parsed dump(s) yielded ZERO stack frames. The exception line "
              "still parses, so this is the stack header or frame syntax having changed; compare a dump against "
              "FRAME_RE and the CALL STACK header match.%s" % (len(parsed), also_near))
    elif parse_degraded:
        print("\nRESULT: PARSER DEGRADED -- %d of %d dumps (%.0f%%) could not be parsed. The signatures above "
              "cover only the %d that could be. This usually means the crash logger's format changed; compare a "
              "failing dump against EXC_RE and FRAME_RE.%s%s"
              % (unparsed, len(files), unparsed_pct, len(parsed), also_frames, also_near))
    elif near:
        # Distinct from ACCOUNTING MISMATCH: the arithmetic is fine, the input set is not. Calling it
        # "accounting" sends the reader to the wrong place.
        print("\nRESULT: INPUT SET INCOMPLETE -- %d file(s) look like crash dumps but did not match the pattern. "
              "Widen CRASH_NAME_RE (or narrow CRASH_PREFIX_RE if these are not dumps); do not trust the totals "
              "above until then." % len(near))
    else:
        print("\nRESULT: OK" if all_ok else "\nRESULT: ACCOUNTING MISMATCH")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
