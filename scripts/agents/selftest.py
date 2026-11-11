"""Self-test of the SkyrimTools repo: the scripts, the docs, the manifests and (with --live) the tools on this machine.

python scripts/agents/selftest.py                  static checks + synthetic fixtures: no game, no network (what CI runs)
python scripts/agents/selftest.py --live           also real data here: game plugins, MO2 .pex/.swf, Address Library,
                                                   the RE venv, DLL .pdb names, the houseCARL MCP launcher, doctor.ps1
python scripts/agents/selftest.py --live --ghidra  also start pyghidra-mcp over stdio (JVM, 20-60 s)
python scripts/agents/selftest.py --net            also query Nexus through nexus_gql.py
  -v / --verbose   print the output of every check;  -k TEXT   run only the checks whose name contains TEXT

Every check prints PASS, FAIL or SKIP (with the reason). Exit code 1 when anything failed, 0 otherwise.
--live reads the SKYRIM_* / HOUSECARL_* variables from the user environment in the registry, so a session started
before setup.cmd (with stale inherited values) tests what the next session will get. Nothing is written outside a
temporary folder; data/se_id_names.tsv is hashed before and after to prove it.
"""
import glob
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
import threading
import time
import zlib

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
PY = sys.executable
VERBOSE = False
RESULTS = []

# Scripts and how they behave without arguments: 2 = print usage and exit 2; None = do not run them bare.
SCRIPTS = {
    "scripts/esp/espscan.py": 2, "scripts/esp/pexdis.py": 2,
    "scripts/misc/font_has.py": 2, "scripts/misc/merge_ini.py": 2, "scripts/misc/nexus_gql.py": 2,
    "scripts/re/addrlib.py": 2, "scripts/re/build_id_names.py": None, "scripts/re/calls_in.py": 2,
    "scripts/re/decomp.py": 2, "scripts/re/disasm_at.py": 2, "scripts/re/find_vcall.py": 2, "scripts/re/mcp_call.py": 2,
    "scripts/re/pdbsym.py": 2, "scripts/re/swf_as2.py": 2, "scripts/re/thread_stacks.py": None,
    "scripts/re/vtable_slot.py": 2, "scripts/agents/selftest.py": None, "scripts/papyrus/papyrusc.py": 2,
    "scripts/esp/espdiff.py": 2, "scripts/save/ess_scan.py": 2, "scripts/save/cosave_info.py": 2,
    # these find the logs of this machine when called bare, so a bare run is machine-dependent
    "scripts/logs/crash_triage.py": None, "scripts/logs/papyrus_triage.py": None,
    "scripts/logs/skse_load_status.py": None, "scripts/logs/mirror_logs.py": None,
}
MODULES = {"scripts/re/skyrim_paths.py", "scripts/logs/_paths.py"}  # imported by scripts, not CLIs
NEEDS_VENV = {"scripts/re/calls_in.py", "scripts/re/disasm_at.py", "scripts/re/find_vcall.py", "scripts/re/vtable_slot.py"}
# Shipped files allowed to carry a drive-letter path (maintainer defaults / an example in help text).
ABS_PATH_OK = {"scripts/re/build_id_names.py", "scripts/agents/selftest.py"}


class Skip(Exception):
    pass


def check(name):
    def wrap(fn):
        fn.check_name = name
        return fn
    return wrap


def run(args, timeout=120, env=None, cwd=REPO, stdin=None):
    p = subprocess.run(args, capture_output=True, timeout=timeout, env=env, cwd=cwd, stdin=stdin)
    out = p.stdout.decode("utf-8", "replace")
    err = p.stderr.decode("utf-8", "replace")
    if VERBOSE:
        print("    $ " + " ".join(str(a) for a in args))
        for line in (out + err).strip().splitlines()[:30]:
            print("    | " + line)
    return p.returncode, out, err


def py(script, *args, python=None, **kw):
    return run([python or PY, os.path.join(REPO, script)] + [str(a) for a in args], **kw)


def expect(cond, msg):
    if not cond:
        raise AssertionError(msg)


def rel(path):
    return os.path.relpath(path, REPO).replace("\\", "/")


# ---------------------------------------------------------------------------------------------------- static checks
@check("python: every script compiles")
def t_compile():
    bad = []
    for f in sorted(glob.glob(os.path.join(REPO, "scripts", "**", "*.py"), recursive=True)):
        rc, _, err = run([PY, "-m", "py_compile", f])
        if rc:
            bad.append("%s: %s" % (rel(f), err.strip().splitlines()[-1] if err.strip() else rc))
    expect(not bad, "; ".join(bad))


@check("python: SCRIPTS table covers scripts/")
def t_inventory():
    found = {rel(f) for f in glob.glob(os.path.join(REPO, "scripts", "**", "*.py"), recursive=True)}
    found -= MODULES
    expect(found == set(SCRIPTS), "untested: %s; gone: %s" % (sorted(found - set(SCRIPTS)), sorted(set(SCRIPTS) - found)))


@check("python: --help prints the docstring, bare call prints usage")
def t_help():
    # As on a stranger's machine: an English console code page and nothing installed (no SKYRIM_* variables).
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("SKYRIM_", "HOUSECARL_", "PYTHONUTF8"))}
    env.update(PYTHONIOENCODING="cp1252", LOCALAPPDATA=tempfile.gettempdir())
    bad = []
    for script, bare in SCRIPTS.items():
        doc = re.match(r'\s*(?:[rRuU]?)"""(.*?)"""', open(os.path.join(REPO, script), encoding="utf-8").read(), re.S)
        if not doc or any(ord(c) > 127 for c in doc.group(1)):
            bad.append("%s: docstring %s" % (script, "missing" if not doc else "is not ASCII"))
        if script in NEEDS_VENV and not has_modules("capstone", "pefile"):
            continue
        rc, out, err = py(script, "--help", timeout=30, env=env)
        if rc != 0 or "Traceback" in err or not out.strip():
            bad.append("%s --help -> %d %s" % (script, rc, err.strip().splitlines()[-1:] if err.strip() else ""))
        if bare is not None:
            rc, out, err = py(script, timeout=30, env=env)
            if rc != bare or "Traceback" in err:
                bad.append("%s (no args) -> %d, want %d" % (script, rc, bare))
    expect(not bad, "; ".join(bad))


def has_modules(*names):
    rc, _, _ = run([PY, "-c", "import " + ",".join(names)])
    return rc == 0


@check("powershell: every .ps1 parses, setup.ps1 has a UTF-8 BOM")
def t_ps():
    ps = powershell()
    files = [rel(f) for f in glob.glob(os.path.join(REPO, "**", "*.ps1"), recursive=True) if not ignored(f)]
    script = ("$bad=0; foreach($f in $args){ $e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile("
              "(Join-Path (Get-Location) $f),[ref]$null,[ref]$e); if($e.Count){ $bad++; \"$f`: $($e[0].Message) line "
              "$($e[0].Extent.StartLineNumber)\" } }; exit $bad")
    rc, out, _ = run([ps, "-NoProfile", "-NonInteractive", "-Command", "& {" + script + "}"] + files)
    expect(rc == 0, out.strip())
    expect(open(os.path.join(REPO, "setup.ps1"), "rb").read(3) == b"\xef\xbb\xbf", "setup.ps1 lost its BOM")


def powershell():
    for name in ("powershell.exe", "pwsh.exe", "pwsh"):
        for d in os.environ.get("PATH", "").split(os.pathsep):
            if os.path.isfile(os.path.join(d, name)):
                return os.path.join(d, name)
    raise Skip("no PowerShell on PATH")


def ignored(path):
    r = rel(path)
    return r.split("/")[0] in ("re", "houseCARL", "houseCARL-data", "tools", ".git") or "__pycache__" in r


@check("git: index is LF, .cmd/.ps1 are CRLF in the working copy")
def t_eol():
    rc, out, _ = run(["git", "ls-files", "--eol"])
    if rc:
        raise Skip("not a git checkout")
    bad = []
    for line in out.splitlines():
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        idx, path = parts[0], parts[3].split("\t")[-1]
        if idx not in ("i/lf", "i/-text", "i/none"):
            bad.append("%s stored as %s" % (path, idx))
        if path.endswith((".cmd", ".bat", ".ps1")):
            data = open(os.path.join(REPO, path), "rb").read()
            if data.count(b"\n") != data.count(b"\r\n"):
                bad.append("%s is not CRLF on disk" % path)
    expect(not bad, "; ".join(bad[:10]))


@check("json: manifests and MCP configs parse, plugin version is semver")
def t_json():
    files = [".claude-plugin/plugin.json", ".claude-plugin/marketplace.json", ".mcp.json"]
    files += [rel(f) for f in glob.glob(os.path.join(REPO, ".vscode", "*.json"))]
    for f in files:
        try:
            json.load(open(os.path.join(REPO, f), encoding="utf-8"))
        except ValueError as e:
            raise AssertionError("%s: %s" % (f, e))
    v = json.load(open(os.path.join(REPO, ".claude-plugin/plugin.json"), encoding="utf-8")).get("version", "")
    expect(re.fullmatch(r"\d+\.\d+\.\d+", v), "plugin.json version %r" % v)
    log = open(os.path.join(REPO, "CHANGELOG.md"), encoding="utf-8").read()
    top = re.search(r"^## (\d+\.\d+\.\d+)", log, re.M)
    expect(top and top.group(1) == v, "CHANGELOG.md top section %s != plugin.json %s" % (top and top.group(1), v))
    for name, server in json.load(open(os.path.join(REPO, ".mcp.json"), encoding="utf-8"))["mcpServers"].items():
        target = server["args"][-1].replace("${CLAUDE_PLUGIN_ROOT}", REPO)
        expect(os.path.isfile(target), ".mcp.json %s -> missing %s" % (name, target))


def frontmatter(path):
    text = open(path, encoding="utf-8").read()
    m = re.match(r"---\r?\n(.*?)\r?\n---", text, re.S)
    return m.group(1) if m else ""


@check("skills: frontmatter, listed in skills/README.md and AGENTS.md")
def t_skills():
    index = open(os.path.join(REPO, "skills", "README.md"), encoding="utf-8").read()
    agents = open(os.path.join(REPO, "AGENTS.md"), encoding="utf-8").read()
    bad = []
    for d in sorted(glob.glob(os.path.join(REPO, "skills", "*", ""))):
        name = os.path.basename(os.path.dirname(d))
        fm = frontmatter(os.path.join(d, "SKILL.md")) if os.path.isfile(os.path.join(d, "SKILL.md")) else ""
        m = re.search(r"^name:\s*(\S+)", fm, re.M)
        if not m or m.group(1) != name:
            bad.append("%s: frontmatter name %s" % (name, m.group(1) if m else "missing"))
        if not re.search(r"^description:", fm, re.M):
            bad.append("%s: no description" % name)
        if "`%s`" % name not in index:
            bad.append("%s: not in skills/README.md" % name)
        if "`%s`" % name not in agents:
            bad.append("%s: not in AGENTS.md" % name)
    expect(not bad, "; ".join(bad))


@check("skills: every index.jsonl entry points at an existing file and line")
def t_indexes():
    bad, n = [], 0
    for idx in glob.glob(os.path.join(REPO, "skills", "*", "references", "index.jsonl")):
        skill = os.path.dirname(os.path.dirname(idx))
        lines_of = {}
        for k, line in enumerate(open(idx, encoding="utf-8"), 1):
            if not line.strip():
                continue
            try:
                e = json.loads(line)
            except ValueError:
                bad.append("%s:%d bad JSON" % (rel(idx), k))
                continue
            n += 1
            f = e.get("file")
            path = next((p for p in (os.path.join(skill, f), os.path.join(skill, "references", f)) if os.path.isfile(p)),
                        None) if f else None
            if not path:
                bad.append("%s:%d -> %s missing" % (rel(idx), k, f))
                continue
            if path not in lines_of:
                lines_of[path] = sum(1 for _ in open(path, encoding="utf-8", errors="replace"))
            last = e.get("line_end") or e.get("line") or e.get("line_start") or 0
            # The papyrus index generator ends a file's last entry one line past EOF; anything further is broken.
            if last > lines_of[path] + (1 if e.get("line_end") else 0):
                bad.append("%s:%d -> %s line %d > %d" % (rel(idx), k, f, last, lines_of[path]))
    expect(not bad, "%d bad of %d: %s" % (len(bad), n, "; ".join(bad[:5])))


@check("markdown: relative links resolve")
def t_links():
    bad = []
    files = glob.glob(os.path.join(REPO, "*.md")) + glob.glob(os.path.join(REPO, "docs", "*.md"))
    files += glob.glob(os.path.join(REPO, "skills", "*", "*.md")) + glob.glob(os.path.join(REPO, "skills", "*.md"))
    files += glob.glob(os.path.join(REPO, ".github", "*.md"))
    for f in files:
        text = re.sub(r"```.*?```", "", open(f, encoding="utf-8").read(), flags=re.S)
        for target in re.findall(r"\]\(([^)\s]+)\)", text):
            if re.match(r"[a-z]+:", target) or target.startswith("#"):
                continue
            path = target.split("#")[0]
            if path and not os.path.exists(os.path.normpath(os.path.join(os.path.dirname(f), path))):
                bad.append("%s -> %s" % (rel(f), target))
    expect(not bad, "; ".join(bad[:10]))


@check("shipped files: no drive-letter paths in scripts and manifests")
def t_abs_paths():
    bad = []
    pats = ["scripts/**/*.py", "scripts/**/*.cmd", "scripts/**/*.ps1", ".mcp.json", ".claude-plugin/*.json", "setup.cmd"]
    for pat in pats:
        for f in glob.glob(os.path.join(REPO, pat), recursive=True):
            r = rel(f)
            if r in ABS_PATH_OK or ignored(f):
                continue
            for k, line in enumerate(open(f, encoding="utf-8", errors="replace"), 1):
                if re.search(r"(?<![\w%])[A-Za-z]:[\\/](?!\\)", line) and "%" not in line.split(":")[0]:
                    bad.append("%s:%d %s" % (r, k, line.strip()[:80]))
    expect(not bad, "; ".join(bad[:10]))


@check("docs: every script is in the AGENTS.md scripts table")
def t_documented():
    agents = open(os.path.join(REPO, "AGENTS.md"), encoding="utf-8").read().replace("\\", "/")
    missing = [s for s in SCRIPTS if s.split("/")[-1] not in agents]
    for cmd in glob.glob(os.path.join(REPO, "scripts", "**", "*.cmd"), recursive=True):
        if os.path.basename(cmd) not in agents:
            missing.append(rel(cmd))
    expect(not missing, "missing: %s" % missing)


@check("data: se_id_names.tsv is a full id/name table")
def t_id_table():
    rows = open(os.path.join(REPO, "data", "se_id_names.tsv"), encoding="utf-8").read().splitlines()
    expect(rows and rows[0] == "id\tname\twhere", "header %r" % rows[:1])
    expect(len(rows) > 1000, "only %d rows (was it overwritten?)" % (len(rows) - 1))
    bad = [r for r in rows[1:] if not re.match(r"\d+\t[^\t]+\t[^\t]+$", r)]
    expect(not bad, "malformed rows: %s" % bad[:3])


# ---------------------------------------------------------------------------------------------------- fixtures
def rec(typ, fid, subs, flags=0):
    data = b"".join(t.encode() + struct.pack("<H", len(d)) + d for t, d in subs)
    if flags & 0x40000:
        data = struct.pack("<I", len(data)) + zlib.compress(data)
    return typ.encode() + struct.pack("<IIIIHH", len(data), flags, fid, 0, 44, 0) + data


def grup(label, recs):
    body = b"".join(recs)
    return b"GRUP" + struct.pack("<I4sIIHH", 24 + len(body), label.encode(), 0, 0, 0, 0) + body


@check("espscan: text / ref / dump on a synthetic plugin (incl. a compressed record)")
def t_espscan(tmp):
    esp = os.path.join(tmp, "SelfTest.esp")
    with open(esp, "wb") as f:
        f.write(rec("TES4", 0, [("HEDR", struct.pack("<fII", 1.7, 2, 0x800))]))
        f.write(grup("WEAP", [
            rec("WEAP", 0x01000800, [("EDID", b"SelfTestSword\0"), ("FULL", b"Clavis Probationis\0"),
                                     ("KWDA", struct.pack("<I", 0x0001E711))]),
            rec("WEAP", 0x01000801, [("EDID", b"SelfTestPacked\0"), ("KWDA", struct.pack("<I", 0x0001E711))],
                flags=0x40000)]))
    rc, out, _ = py("scripts/esp/espscan.py", esp, "text", "probationis")
    expect(rc == 0 and out.split() == ["WEAP", "01000800", "SelfTestSword"], "text: %r" % out)
    rc, out, _ = py("scripts/esp/espscan.py", esp, "ref", "1E711")
    expect(rc == 0 and "01000800 SelfTestSword" in out and "01000801 SelfTestPacked" in out, "ref: %r" % out)
    rc, out, _ = py("scripts/esp/espscan.py", esp, "dump", "01000801")
    expect(rc == 0 and "EDID [15] SelfTestPacked" in out and "KWDA [4] 11 e7 01 00" in out, "dump: %r" % out)


@check("espdiff: diff finds the one changed subrecord, summary counts new records, truncation is INCONCLUSIVE")
def t_espdiff(tmp):
    def plugin(name, value, extra=b""):
        path = os.path.join(tmp, name)
        weap = rec("WEAP", 0x01000800, [("EDID", b"SelfTestSword\0"), ("DATA", struct.pack("<I", value))])
        with open(path, "wb") as f:
            f.write(rec("TES4", 0, [("HEDR", struct.pack("<fII", 1.7, 1, 0x800)), ("MAST", b"Skyrim.esm\0")]))
            f.write(grup("WEAP", [weap + extra]))
        return path
    a, b = plugin("A.esp", 1), plugin("B.esp", 2)
    rc, out, err = py("scripts/esp/espdiff.py", "diff", a, b)
    expect(rc == 1 and "CHANGED 01000800 WEAP SelfTestSword  subrecords: DATA" in out and "differences: 1" in out,
           (out + err)[:600])
    rc, out, err = py("scripts/esp/espdiff.py", "diff", a, a)
    expect(rc == 0 and "byte-identical: yes" in out and "differences: 0" in out, (out + err)[:400])
    rc, out, err = py("scripts/esp/espdiff.py", "summary", a)
    expect(rc == 0 and "records: 1 (1 new, 0 overrides)" in out and "problems: 0" in out, (out + err)[:400])
    bad = os.path.join(tmp, "Bad.esp")
    data = bytearray(open(a, "rb").read())
    data[-6:-4] = struct.pack("<H", 40)  # the last subrecord now claims 40 bytes it does not have
    open(bad, "wb").write(bytes(data))
    rc, out, err = py("scripts/esp/espdiff.py", "summary", bad)
    expect(rc == 1 and "problems: 1" in out, (out + err)[:400])


def lz4_literal(data):
    """One LZ4 block holding a single literal run (no match): a valid block with no compressor."""
    n, ext = len(data), b""
    if n >= 15:
        rest = n - 15
        ext = b"\xff" * (rest // 255) + bytes([rest % 255])
    return bytes([min(n, 15) << 4]) + ext + data


def ess_bytes():
    ws = lambda s: struct.pack("<H", len(s.encode())) + s.encode()  # noqa: E731
    plugins = struct.pack("<B", 1) + ws("Test.esp") + struct.pack("<H", 0)
    header = (struct.pack("<II", 12, 7) + ws("Hero") + struct.pack("<I", 42) + ws("Whiterun") + ws("017.08.22")
              + ws("NordRace") + struct.pack("<HffQII", 0, 0.0, 100.0, 0, 1, 1) + struct.pack("<H", 2))
    base = 13 + 4 + len(header) + 4                      # offsets count from the length pair after the screenshot
    table_at = 1 + 4 + len(plugins)
    ids_at = table_at + 25 * 4
    end = ids_at + 8
    table = struct.pack("<25I", *([base + ids_at, base + end] + [base + ids_at] * 4 + [0] * 19))
    payload = struct.pack("<BI", 78, len(plugins)) + plugins + table + struct.pack("<II", 1, 0x00001234)
    block = lz4_literal(payload)
    return (b"TESV_SAVEGAME" + struct.pack("<I", len(header)) + header + b"\x00\x00\x00\xff"
            + struct.pack("<II", len(payload), len(block)) + block)


@check("ess_scan / cosave_info: synthetic SE save + co-save parse completely; truncation is INCONCLUSIVE")
def t_saves(tmp):
    ess = os.path.join(tmp, "Mini.ess")
    open(ess, "wb").write(ess_bytes())
    rc, out, err = py("scripts/save/ess_scan.py", "info", ess)
    expect(rc == 0 and '"complete": true' in out and '"playerName": "Hero"' in out and '"problems": []' in out,
           (out + err)[:800])
    rc, out, err = py("scripts/save/ess_scan.py", "search", ess, "--formid", "00001234")
    expect(rc == 0 and '"matchCount": 1' in out, (out + err)[:400])
    rc, out, err = py("scripts/save/ess_scan.py", "plugins", ess)
    expect(rc == 0 and "Test.esp" in out, (out + err)[:400])
    cut = os.path.join(tmp, "Cut.ess")
    open(cut, "wb").write(ess_bytes()[:200])
    rc, out, err = py("scripts/save/ess_scan.py", "info", cut)
    expect(rc == 1 and "INCONCLUSIVE" in err, (out + err)[:400])
    junk = os.path.join(tmp, "Junk.ess")
    open(junk, "wb").write(b"not a save at all")
    rc, out, err = py("scripts/save/ess_scan.py", "info", junk)
    expect(rc == 2, (out + err)[:300])
    skse = os.path.join(tmp, "Mini.skse")
    open(skse, "wb").write(b"SKSE" + struct.pack("<IIIIIII", 1, 0x02000140, 0x01050610, 0, 0, 0, 0)
                           + b"NGLP" + struct.pack("<II", 1, 0))
    rc, out, err = py("scripts/save/cosave_info.py", skse)
    expect(rc == 0 and '"chunkCount": 1' in out and '"PLGN"' in out, (out + err)[:600])
    open(skse, "wb").write(b"XXXXjunk")
    rc, out, err = py("scripts/save/cosave_info.py", skse)
    expect(rc == 2 and '"ok": false' in out, (out + err)[:300])


CRASH_DUMP = """Skyrim SSE v1.5.97
CrashLoggerSSE v1-23-1-0 Nov  1 2025 09:12:11

Unhandled exception "EXCEPTION_ACCESS_VIOLATION" at 0x7FF6EE5A1234 SkyrimSE.exe+0D280C0

CALL STACK ([P]robable / [S]tack scan):
\t[0][P] 0x7FF6EE5A1234 SkyrimSE.exe+0D280C0 FUN_140D280C0
\t\tmov rax, [rcx]
\t[1][P] 0x7FF6EE5A2345 SkyrimSE.exe+0C56D8F FUN_140C56D8F

REGISTERS:
\tRAX 0x0                (NULL)
"""


@check("log triage: crash dumps (+ --known), Papyrus log, SKSE log, append-only mirror")
def t_logs(tmp):
    crashes = os.path.join(tmp, "SKSE")
    os.makedirs(crashes)
    for stamp in ("2026-01-02-03-04-05", "2026-01-02-04-05-06"):
        open(os.path.join(crashes, "crash-%s.log" % stamp), "w").write(CRASH_DUMP)
    rc, out, err = py("scripts/logs/crash_triage.py", crashes)
    expect(rc == 0 and "2 x  SkyrimSE.exe+0D280C0" in out and "RESULT: OK" in out, (out + err)[-800:])
    known = os.path.join(tmp, "known.txt")
    open(known, "w").write("SkyrimSE.exe+0x0D280C0  ACCEPTED  ruled in the selftest\n")
    rc, out, err = py("scripts/logs/crash_triage.py", crashes, "--known", known)
    expect(rc == 0 and "ACCEPTED" in out, (out + err)[-800:])
    broken = os.path.join(tmp, "broken")
    os.makedirs(broken)
    for i in range(2):
        open(os.path.join(broken, "crash-2026-01-01-00-00-0%d.log" % i), "w").write("NOT A DUMP\n")
    rc, out, err = py("scripts/logs/crash_triage.py", broken)
    expect(rc == 1 and "PARSER DEGRADED" in out, (out + err)[-600:])

    plog = os.path.join(tmp, "Papyrus.0.log")
    open(plog, "w").write(
        "[01/02/2026 - 03:04:06PM] error: Cannot call GetActorValue() on a None object, aborting function call\n"
        "stack:\n\t[alias Player on quest MyQuest (0A0012AB)].MyModScript.OnUpdate() - \"MyModScript.psc\" Line 42\n")
    rc, out, err = py("scripts/logs/papyrus_triage.py", plog)
    expect(rc == 0 and "MyModScript.psc" in out and "RESULT: OK" in out, (out + err)[-800:])

    slog = os.path.join(tmp, "skse64.log")
    open(slog, "w").write("checking plugin C:\\Games\\Skyrim\\Data\\SKSE\\Plugins\\GoodPlugin.dll\n"
                          "plugin C:\\Games\\Skyrim\\Data\\SKSE\\Plugins\\GoodPlugin.dll (00000001 GoodPlugin 01020000)"
                          " loaded correctly (handle 1)\n")
    rc, out, err = py("scripts/logs/skse_load_status.py", "--log", slog)
    expect(rc == 0 and "RESULT: OK (rows sum to 1 checked)" in out, (out + err)[-600:])

    game = os.path.join(tmp, "docs", "Skyrim Special Edition")
    os.makedirs(os.path.join(game, "SKSE"))
    src = os.path.join(game, "SKSE", "one.log")
    open(src, "w").write("first line\n")
    env = dict(os.environ, SKYRIM_DOCUMENTS_DIR=game)
    dest = os.path.join(tmp, "mirror")
    rc, out, err = py("scripts/logs/mirror_logs.py", "--dest", dest, env=env)
    expect(rc == 0 and "1 NEW" in out, (out + err)[-600:])
    rc, out, err = py("scripts/logs/mirror_logs.py", "--dest", dest, env=env)
    expect(rc == 0 and "1 UNCHANGED" in out, (out + err)[-600:])
    open(src, "a").write("second line\n")
    rc, out, err = py("scripts/logs/mirror_logs.py", "--dest", dest, env=env)
    expect(rc == 0 and "APPENDED" in out, (out + err)[-600:])


@check("merge_ini: adds new keys, keeps tuned values")
def t_merge_ini(tmp):
    dist, dep = os.path.join(tmp, "dist.ini"), os.path.join(tmp, "deployed.ini")
    open(dist, "w").write("[General]\nfSpeed=1.0\nbNew=1\n[Extra]\niCount=3\n")
    open(dep, "w").write("; user comment\n[General]\nfSpeed=2.5\n")
    rc, out, _ = py("scripts/misc/merge_ini.py", dist, dep)
    text = open(dep).read()
    expect(rc == 0, "rc %d" % rc)
    expect("fSpeed=2.5" in text and "fSpeed=1.0" not in text, "tuned value lost:\n" + text)
    expect("bNew=1" in text and "iCount=3" in text and "; user comment" in text, "keys/comment:\n" + text)
    before = open(dep).read()
    py("scripts/misc/merge_ini.py", dist, dep)
    expect(open(dep).read() == before, "second merge changed the file")


@check("font_has: a Windows font with Cyrillic")
def t_font():
    font = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "arial.ttf")
    if not os.path.isfile(font):
        raise Skip("no arial.ttf")
    rc, out, _ = py("scripts/misc/font_has.py", font)
    expect(rc == 0 and "'0x410': True" in out, out)


@check("swf_as2: a minimal SWF")
def t_swf(tmp):
    body = bytes([0x00]) + struct.pack("<HH", 30 << 8, 1)  # empty RECT (nbits 0), 30 fps, 1 frame
    body += struct.pack("<H", (12 << 6) | 1) + b"\x00"  # DoAction, one ActionEnd byte
    body += struct.pack("<H", 0)  # End tag
    swf = os.path.join(tmp, "t.swf")
    open(swf, "wb").write(b"FWS" + bytes([8]) + struct.pack("<I", 8 + len(body)) + body)
    rc, out, err = py("scripts/re/swf_as2.py", swf)
    expect(rc == 0 and "SWF 8" in out and "Traceback" not in err, out + err)


@check("build_id_names: refuses bad input, leaves the table alone")
def t_build_ids(tmp):
    table = os.path.join(REPO, "data", "se_id_names.tsv")
    before = hashlib.sha256(open(table, "rb").read()).hexdigest()
    empty = os.path.join(tmp, "empty_src")
    os.makedirs(empty)
    for args in (["--help"], [os.path.join(tmp, "nope")], [empty]):
        py("scripts/re/build_id_names.py", *args)
    expect(hashlib.sha256(open(table, "rb").read()).hexdigest() == before, "data/se_id_names.tsv was rewritten")


@check("thread_stacks: snapshots a child process, clean error for a missing one")
def t_threads():
    child = subprocess.Popen([PY, "-c", "import time; time.sleep(60)"])
    try:
        time.sleep(1.0)
        rc, out, err = py("scripts/re/thread_stacks.py", child.pid, "--max", 2, timeout=60)
        expect(rc == 0 and re.search(r"pid %d: \d+ threads" % child.pid, out), out + err)
        rc, out, err = py("scripts/re/thread_stacks.py", "NoSuchProcess_SelfTest.exe")
        expect(rc == 1 and "no process" in err and "Traceback" not in err, "rc %d %s" % (rc, err))
    finally:
        child.kill()


def pex_bytes(name, parent, funcs):
    """A minimal .pex: one object, empty-state functions [(name, ret, [(type, pname)], native, global)]."""
    strings = []

    def s(x):
        if x not in strings:
            strings.append(x)
        return struct.pack(">H", strings.index(x))

    obj = b""
    obj += struct.pack(">H", 0) + struct.pack(">H", 0)  # 0 variables, 0 properties
    obj += struct.pack(">H", 1) + s("") + struct.pack(">H", len(funcs))
    for fname, ret, params, native, glob in funcs:
        obj += s(fname) + s(ret) + s("") + struct.pack(">IB", 0, (2 if native else 0) | (1 if glob else 0))
        obj += struct.pack(">H", len(params)) + b"".join(s(n) + s(t) for t, n in params)
        obj += struct.pack(">HH", 0, 0)  # no locals, no instructions
    head = s(name) + struct.pack(">I", 0) + s(parent) + s("") + struct.pack(">I", 0) + s("")
    body = head + obj
    table = struct.pack(">H", len(strings)) + b"".join(struct.pack(">H", len(x)) + x.encode() for x in strings)
    hdr = struct.pack(">IBBHQ", 0xFA57C0DE, 3, 2, 1, 0) + b"".join(struct.pack(">H", 0) for _ in range(3))
    return hdr + table + b"\x00" + struct.pack(">H", 0) + struct.pack(">H", 1) + body


def bsa_bytes(files):
    """A minimal uncompressed SSE (v105) BSA with one folder 'scripts' holding {name.pex: bytes}."""
    names = sorted(files)
    nfile = len(names)
    folder = b"scripts\0"
    names_blob = b"".join(n.encode() + b"\0" for n in names)
    off = 36
    recs_end = off + 24 + 1 + len(folder) + 16 * nfile
    data_start = recs_end + len(names_blob)
    out = struct.pack("<4sIIIIIIIHH", b"BSA\0", 105, off, 0x3, 1, nfile, len(folder), len(names_blob), 0, 0)
    out += struct.pack("<QIIQ", 0, nfile, 0, off + 24 + len(names_blob))
    out += bytes([len(folder)]) + folder
    pos, blobs = data_start, b""
    for n in names:
        out += struct.pack("<QII", 0, len(files[n]), pos)
        pos += len(files[n])
        blobs += files[n]
    return out + names_blob + blobs


FAKE_COMPILER = r'''
import os, struct, sys
a = sys.argv[1:]
hdr = a[a.index("-h") + 1]; out = a[a.index("-o") + 1]
ind = a[a.index("-i") + 1]  # papyrusc stages the inputs into one folder
ins = [os.path.join(ind, n) for n in sorted(os.listdir(ind))]
with open(os.path.join(out, "headers.txt"), "w") as f:
    for n in sorted(os.listdir(hdr)):
        f.write("%s|%s\n" % (n, open(os.path.join(hdr, n)).readline().strip()))
for p in ins:
    if "BROKEN" in open(p).read():
        print("%s:3:5: error: unknown type `NoSuchType`" % p)
    else:
        open(os.path.join(out, os.path.basename(p)[:-4] + ".pex"), "wb").write(struct.pack(">I", 0xFA57C0DE) + b"x")
'''


@check("papyrusc: MO2 import order, first provider wins, vanilla headers from a BSA, stub compile, write guard")
def t_papyrusc(tmp):
    j = lambda *p: os.path.join(tmp, *p)  # noqa: E731
    w = lambda path, text: (os.makedirs(os.path.dirname(path), exist_ok=True), open(path, "w").write(text))  # noqa: E731
    mo2, game = j("MO2"), j("Game")
    w(os.path.join(mo2, "ModOrganizer.ini"), "[General]\ngamePath=@ByteArray(%s)\nselected_profile=@ByteArray(P)\n"
      % game.replace("\\", "\\\\"))
    w(os.path.join(mo2, "profiles", "P", "modlist.txt"), "# generated\n+Top Mod\n-Disabled Mod\n+Bottom Mod\n+Sep_separator\n")
    w(os.path.join(mo2, "mods", "Top Mod", "Scripts", "Source", "Shared.psc"), "ScriptName Shared ; TOP\n")
    w(os.path.join(mo2, "mods", "Bottom Mod", "Source", "Scripts", "Shared.psc"), "ScriptName Shared ; BOTTOM\n")
    w(os.path.join(mo2, "mods", "Bottom Mod", "Source", "Scripts", "Mine.psc"), "ScriptName Mine ; MOD COPY\n")
    w(os.path.join(mo2, "mods", "Disabled Mod", "Scripts", "Source", "Ghost.psc"), "ScriptName Ghost\n")
    w(os.path.join(mo2, "mods", "Installed", "meta.ini"), "[General]\n")
    w(os.path.join(mo2, "overwrite", "Scripts", "Source", "Over.psc"), "ScriptName Over\n")
    w(os.path.join(game, "Data", "Source", "Scripts", "Form.psc"), "ScriptName Form Hidden ; GAME\n")
    os.makedirs(os.path.join(game, "Data"), exist_ok=True)
    open(os.path.join(game, "Data", "Skyrim - Misc.bsa"), "wb").write(bsa_bytes({
        "debug.pex": pex_bytes("Debug", "", [("TraceAndBox", "None", [("string", "asTextToPrint"), ("int", "aiSeverity")], True, True)]),
        "door.pex": pex_bytes("Door", "Form", []),
        "form.pex": pex_bytes("Form", "", [("GetFormID", "int", [], True, False)])}))
    src = j("src")
    w(os.path.join(src, "Mine.psc"), "ScriptName Mine extends Quest\n")
    w(os.path.join(src, "Bad.psc"), "ScriptName Bad\n; BROKEN\n")
    stub = j("fakec.py")
    open(stub, "w").write(FAKE_COMPILER)
    env = dict(os.environ, SKYRIM_MO2_DIR=mo2, SKYRIM_GAME_DIR=game, SKYRIM_TOOLS_HOME=j("home"))
    env.pop("PAPYRUS_COMPILER_DIR", None)
    script = "scripts/papyrus/papyrusc.py"

    rc, out, err = py(script, "imports", "-i", j("extra"), env=env) if os.makedirs(j("extra")) is None else (1, "", "")
    origins = [l.split(None, 2)[2].rsplit(None, 1)[0].strip() if len(l.split()) > 2 else "" for l in out.splitlines()]
    order = [o for o in ("-i", "MO2 overwrite", "mod: Top Mod", "mod: Bottom Mod", "game Data", "vanilla headers") if
             any(x.startswith(o) for x in origins)]
    expect(rc == 0 and order == ["-i", "MO2 overwrite", "mod: Top Mod", "mod: Bottom Mod", "game Data", "vanilla headers"],
           "imports order %s\n%s%s" % (order, out, err))
    expect("Disabled Mod" not in out, "a disabled mod is in the imports")

    rc, out, err = py(script, "headers", env=env)
    hdir = out.splitlines()[0] if out else ""
    expect(rc == 0 and os.path.isfile(os.path.join(hdir, "Door.psc")), out + err)
    door = open(os.path.join(hdir, "Door.psc")).read()
    dbg = open(os.path.join(hdir, "Debug.psc")).read()
    expect(door.startswith("ScriptName Door extends Form Hidden"), door)
    expect("Function TraceAndBox(string asTextToPrint, int aiSeverity = 0) native global" in dbg, "default not from corpus:\n" + dbg)

    outdir = j("NewMod", "Scripts")
    rc, out, err = py(script, "compile", os.path.join(src, "Mine.psc"), os.path.join(src, "Bad.psc"), "-o", outdir,
                      "--compiler-exe", stub, "--compiler-kind", "open", env=env)
    expect(rc == 1, "want exit 1 (Bad fails), got %d\n%s%s" % (rc, out, err))
    expect(os.path.isfile(os.path.join(outdir, "Mine.pex")) and not os.path.exists(os.path.join(outdir, "Bad.pex")), out)
    expect("Bad.psc(3,5): error: unknown type" in out and "FAILED: Bad" in out and "hint:" in out, out)
    staged = dict(l.split("|", 1) for l in open(os.path.join(outdir, "headers.txt")).read().splitlines())
    expect("TOP" in staged.get("Shared.psc", ""), "Shared.psc should come from Top Mod: %s" % staged.get("Shared.psc"))
    expect("Mine.psc" not in staged and "Bad.psc" not in staged, "inputs leaked into the headers")
    expect("GAME" in staged.get("Form.psc", ""), "game Data Form.psc should beat the generated header")
    expect("Door.psc" in staged and "Over.psc" in staged and "Ghost.psc" not in staged, sorted(staged))

    rc, out, err = py(script, "compile", os.path.join(src, "Mine.psc"), "-o", os.path.join(mo2, "mods", "Installed", "Scripts"),
                      "--compiler-exe", stub, env=env)
    expect(rc == 2 and "refusing" in err and not os.path.exists(os.path.join(mo2, "mods", "Installed", "Scripts")),
           "write guard: rc %d %s" % (rc, err))


@check("pdbsym: names a symbol from a .pdb (python DLL when it ships one)")
def t_pdbsym_static():
    base = glob.escape(os.path.dirname(PY))
    pdbs = glob.glob(os.path.join(base, "*.pdb")) + glob.glob(os.path.join(base, "DLLs", "*.pdb"))
    pairs = [(p[:-4] + ".dll", p) for p in pdbs if os.path.isfile(p[:-4] + ".dll")]
    if not pairs:
        raise Skip("no DLL+PDB next to this Python (covered by --live with re\\bins)")
    pdbsym_resolves(pairs[0][0])


def entry_rva(dll):
    data = open(dll, "rb").read(4096)
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    return struct.unpack_from("<I", data, pe + 24 + 16)[0]


def pdbsym_resolves(dll):
    rva = "%X" % entry_rva(dll)
    rc, out, err = py("scripts/re/pdbsym.py", dll, rva)
    line = [l for l in out.splitlines() if l.startswith("+")]
    expect(rc == 0 and line and not line[0].rstrip().endswith("?"), "%s +%s -> %r %s" % (os.path.basename(dll), rva, out, err))


# ---------------------------------------------------------------------------------------------------- live checks
def user_env():
    env = dict(os.environ)
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            i = 0
            while True:
                try:
                    name, val, _ = winreg.EnumValue(k, i)
                except OSError:
                    break
                if name.upper().startswith(("SKYRIM_", "HOUSECARL_")):
                    env[name] = os.path.expandvars(val)
                i += 1
    except ImportError:
        pass
    return env


def var(name):
    v = user_env().get(name, "")
    if not v or not os.path.exists(v):
        raise Skip("%s %s" % (name, "unset" if not v else "points at a missing path: " + v))
    return v


def re_dir():
    v = user_env().get("SKYRIM_RE_DIR", "")
    for d in (v, os.path.join(REPO, "re")):
        if d and os.path.isfile(os.path.join(d, "venv", "Scripts", "python.exe")):
            return d
    raise Skip("no RE workspace (setup.cmd -Ghidra)")


def venv_py():
    return os.path.join(re_dir(), "venv", "Scripts", "python.exe")


def mo2_files(pattern):
    mods = os.path.join(var("SKYRIM_MO2_DIR"), "mods")
    for d in sorted(os.listdir(mods)):
        hit = glob.glob(os.path.join(glob.escape(os.path.join(mods, d)), "**", pattern), recursive=True)  # "[STB] ..."
        if hit:
            return hit[0]
    raise Skip("no %s under the MO2 mods" % pattern)


@check("live espscan: Update.esm of the game")
def t_live_esp():
    esm = os.path.join(var("SKYRIM_GAME_DIR"), "Data", "Update.esm")
    if not os.path.isfile(esm):
        raise Skip("no Update.esm")
    rc, out, _ = py("scripts/esp/espscan.py", esm, "text", "Ulfric", env=user_env())
    expect(rc == 0 and re.search(r"^\w{4} [0-9A-F]{8} ", out, re.M), out[:300])
    fid = out.split()[1]
    rc, out, _ = py("scripts/esp/espscan.py", esm, "dump", fid, env=user_env())
    expect(rc == 0 and "EDID" in out, out[:300])


@check("live pexdis: a .pex from the MO2 mods")
def t_live_pex():
    rc, out, err = py("scripts/esp/pexdis.py", mo2_files("*.pex"))
    expect(rc == 0 and "SCRIPTNAME" in out, (out + err)[:300])


@check("live swf_as2: a .swf from the MO2 mods")
def t_live_swf():
    rc, out, err = py("scripts/re/swf_as2.py", mo2_files("*.swf"))
    expect(rc == 0 and "(SWF " in out, (out + err)[:300])


@check("live addrlib: ID 11045 <-> SkyrimSE.exe+FCFE0 (1.5.97)")
def t_live_addrlib():
    rc, out, err = py("scripts/re/addrlib.py", "id", "11045", env=user_env())
    if rc and ("not found" in err.lower() or "address library" in err.lower()):
        raise Skip(err.strip().splitlines()[-1])
    expect(rc == 0 and "SkyrimSE.exe+FCFE0" in out, out + err)
    rc, out, err = py("scripts/re/addrlib.py", "off", "FCFE0", env=user_env())
    expect(rc == 0 and "11045" in out, out + err)


@check("live RE venv: disasm_at, calls_in, vtable_slot, find_vcall on the exe copy")
def t_live_venv():
    v, env = venv_py(), user_env()
    exe = os.path.join(re_dir(), "bins", "skyrim", "SkyrimSE.exe")
    if not os.path.isfile(exe):
        raise Skip("no %s" % exe)
    rc, out, err = py("scripts/re/disasm_at.py", exe, "FCFE0", python=v, env=env)
    expect(rc == 0 and "+FCFE0" in out, (out + err)[:300])
    rc, out, err = py("scripts/re/calls_in.py", "0xFCFE0", "0xFD100", python=v, env=env)
    expect(rc == 0 and re.search(r"call 0x[0-9a-f]+\s+ID \d+", out), (out + err)[:300])
    rc, out, err = py("scripts/re/vtable_slot.py", "291232", "5", python=v, env=env)
    expect(rc == 0 and "vtable ID 291232" in out, (out + err)[:300])
    rc, out, err = py("scripts/re/find_vcall.py", "0x568", "4", "ID:35565", python=v, env=env, timeout=300)
    expect(rc == 0 and "in ID 35578" in out, (out + err)[:300])


@check("live pdbsym: DLLs in re\\bins name their entry point")
def t_live_pdbsym():
    dlls = [d for d in glob.glob(os.path.join(glob.escape(re_dir()), "bins", "*", "*.dll")) if os.path.isfile(d[:-4] + ".pdb")]
    if not dlls:
        raise Skip("no DLL+PDB pair in re\\bins")
    for d in dlls:
        pdbsym_resolves(d)


def mcp_probe(launcher, timeout):
    p = subprocess.Popen(["cmd.exe", "/c", launcher], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, env=user_env(), cwd=REPO)
    lines, err = [], []
    threading.Thread(target=lambda: lines.extend(p.stdout), daemon=True).start()
    threading.Thread(target=lambda: err.extend(p.stderr), daemon=True).start()

    def send(o):
        p.stdin.write((json.dumps(o) + "\n").encode())
        p.stdin.flush()

    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "selftest", "version": "0"}}})
        listed, deadline = False, time.time() + timeout
        while time.time() < deadline:
            msgs = [json.loads(l) for l in list(lines) if l.strip().startswith(b"{")]
            if not listed and any(m.get("id") == 1 for m in msgs):
                send({"jsonrpc": "2.0", "method": "notifications/initialized"})
                send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
                listed = True
            for m in msgs:
                if m.get("id") == 2:
                    return [t["name"] for t in m.get("result", {}).get("tools", [])]
            if p.poll() is not None:
                break
            time.sleep(0.3)
        tail = b"".join(err).decode("utf-8", "replace").strip().splitlines()[-3:]
        raise AssertionError("no tools/list answer (exit %s): %s" % (p.poll(), " | ".join(tail)))
    finally:
        p.kill()


@check("live MCP: houseCARL launcher answers initialize + tools/list")
def t_live_housecarl():
    tools = mcp_probe(os.path.join(REPO, "scripts", "run_housecarl.cmd"), 60)
    expect(len(tools) >= 20 and "housecarl_records" in tools, "tools: %s" % tools)


@check("live MCP: pyghidra-mcp launcher answers initialize + tools/list")
def t_live_ghidra():
    if not ARGS_GHIDRA:
        raise Skip("pass --ghidra (starts a JVM, 20-60 s)")
    re_dir()
    tools = mcp_probe(os.path.join(REPO, "scripts", "re", "run_ghidra_mcp.cmd"), 240)
    expect("decompile_function" in tools, "tools: %s" % tools)


@check("live MCP: SkyLink AI launcher answers initialize + tools/list (game not needed)")
def t_live_skylink():
    env = user_env()
    home = env.get("SKYRIM_TOOLS_HOME") or os.path.join(env.get("LOCALAPPDATA", ""), "SkyrimTools")
    exe = env.get("SKYLINK_EXE") or os.path.join(home, "skylink", "server", "SkyrimMCP.exe")
    if not os.path.isfile(exe):
        raise Skip("not installed (optional: setup.cmd -SkyLink)")
    tools = mcp_probe(os.path.join(REPO, "scripts", "run_skylink.cmd"), 60)
    expect(len(tools) >= 50 and any(t.lower().replace("_", "") == "checkconnection" for t in tools), "tools: %s" % tools)


LIVE_PSC = """ScriptName SkyrimToolsSelfTest extends Quest
{compiled by scripts/agents/selftest.py --live; never shipped}
Actor Property PlayerRef Auto
Event OnInit()
    Debug.Notification("SkyrimTools selftest: " + Game.GetModCount() + " plugins")
    PlayerRef.EquipItem(Game.GetFormFromFile(0x12EB7, "Skyrim.esm"))
    RegisterForSingleUpdate(1.0)
EndEvent
"""


@check("live papyrusc: compile a script against this MO2 (SKSE + vanilla headers), pexdis reads it")
def t_live_papyrus(tmp):
    env = user_env()
    rc, out, _ = py("scripts/papyrus/papyrusc.py", "which", env=env)
    if rc == 3:
        raise Skip("no Papyrus compiler (setup.cmd installs papyrus-compiler)")
    var("SKYRIM_MO2_DIR")
    src = os.path.join(tmp, "src", "SkyrimToolsSelfTest.psc")
    os.makedirs(os.path.dirname(src))
    open(src, "w").write(LIVE_PSC)
    outdir = os.path.join(tmp, "NewMod", "Scripts")
    rc, out, err = py("scripts/papyrus/papyrusc.py", "compile", src, "-o", outdir, env=env, timeout=600)
    pex = os.path.join(outdir, "SkyrimToolsSelfTest.pex")
    expect(rc == 0 and os.path.isfile(pex), (out + err)[-1500:])
    rc, out, err = py("scripts/esp/pexdis.py", pex)
    expect(rc == 0 and re.search(r"SCRIPTNAME SkyrimToolsSelfTest extends quest", out, re.I) and "PlayerRef" in out,
           (out + err)[:800])


@check("live doctor.ps1: no FAIL")
def t_live_doctor():
    rc, out, err = run([powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                        os.path.join(REPO, "scripts", "agents", "doctor.ps1"), "-Json"], env=user_env())
    try:
        data = json.loads(out[out.index("{") if "{" in out[:5] else out.index("["):])
    except ValueError:
        raise AssertionError("doctor -Json did not print JSON: %s" % (out + err)[:300])
    items = data if isinstance(data, list) else data.get("results") or data.get("checks") or []
    fails = [i for i in items if str(i.get("status", i.get("Status", ""))).upper() == "FAIL"]
    expect(not fails, "; ".join("%s: %s" % (i.get("name", i.get("Name")), i.get("detail", i.get("Detail"))) for i in fails))


@check("net nexus_gql: search SkyUI")
def t_net_nexus():
    rc, out, err = py("scripts/misc/nexus_gql.py", "search", "SkyUI", "--count", "3", timeout=60)
    expect(rc == 0 and "SkyUI" in out, (out + err)[:300])


STATIC = [t_compile, t_inventory, t_help, t_ps, t_eol, t_json, t_skills, t_indexes, t_links, t_abs_paths, t_documented,
          t_id_table, t_espscan, t_espdiff, t_saves, t_logs, t_merge_ini, t_font, t_swf, t_build_ids, t_threads, t_papyrusc, t_pdbsym_static]
LIVE = [t_live_esp, t_live_pex, t_live_swf, t_live_addrlib, t_live_venv, t_live_pdbsym, t_live_housecarl, t_live_ghidra,
        t_live_skylink, t_live_papyrus, t_live_doctor]
NET = [t_net_nexus]
ARGS_GHIDRA = False


def main():
    global VERBOSE, ARGS_GHIDRA
    args = sys.argv[1:]
    if "-h" in args or "--help" in args:
        print(__doc__.strip())
        return 0
    VERBOSE = "-v" in args or "--verbose" in args
    ARGS_GHIDRA = "--ghidra" in args
    only = args[args.index("-k") + 1] if "-k" in args else ""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    checks = STATIC + (LIVE if "--live" in args or ARGS_GHIDRA else []) + (NET if "--net" in args else [])
    counts = {"PASS": 0, "FAIL": 0, "SKIP": 0}
    with tempfile.TemporaryDirectory(prefix="skyrimtools-selftest-") as tmp:
        for fn in checks:
            name = fn.check_name
            if only and only.lower() not in name.lower():
                continue
            t0 = time.time()
            try:
                if fn.__code__.co_argcount:
                    sub = os.path.join(tmp, fn.__name__)
                    os.makedirs(sub)
                    fn(sub)
                else:
                    fn()
                status, why = "PASS", ""
            except Skip as e:
                status, why = "SKIP", str(e)
            except AssertionError as e:
                status, why = "FAIL", str(e)
            except Exception as e:  # a crash in the check itself is a failure too
                status, why = "FAIL", "%s: %s" % (type(e).__name__, e)
            counts[status] += 1
            if status == "FAIL" and os.environ.get("GITHUB_ACTIONS"):  # an annotation is readable without the log
                esc = lambda s: s.replace("%", "%25").replace("\r", "").replace("\n", "%0A")  # noqa: E731
                print("::error title=%s::%s" % (esc(name).replace(":", " -").replace(",", ";"), esc(why[:4000])))
            print("  %-4s %-72s %5.1fs%s" % (status, name, time.time() - t0, ("\n       " + why) if why else ""))
            sys.stdout.flush()
    print("\n%d passed, %d failed, %d skipped" % (counts["PASS"], counts["FAIL"], counts["SKIP"]))
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
