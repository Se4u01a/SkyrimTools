"""Compile Papyrus .psc to .pex with the imports a live MO2 load order provides. Standard library only.

python papyrusc.py compile <file.psc|dir>... -o <out dir> [-i <import dir>]... [--compiler auto|open|ck]
                   [--profile NAME] [--no-mo2] [--check] [--into-existing-mod]
python papyrusc.py imports [--profile NAME] [-i <import dir>]...   the import folders in the order the compiler sees them
python papyrusc.py which                                             which compilers are installed, and where
python papyrusc.py headers [--rebuild]                               build/show the generated vanilla headers

Vanilla headers: the Creation Kit's Scripts.zip (the vanilla .psc) is often not installed. For either compiler the
script then generates declaration-only headers from the game's own .pex (Skyrim - Misc.bsa, Update.bsa, the DLC
BSAs) with parameter defaults from the papyrus-reference corpus, caches them in %SKYRIM_TOOLS_HOME%\\papyrus-headers
and puts them LAST in the imports, so every real .psc (SKSE, USSEP, the mods) still wins. --no-vanilla-headers
turns that off. A default the corpus does not carry is missing: such a call needs the argument written out.

Compilers (auto = open, else ck):
  open  russo-2025/papyrus-compiler (MIT), papyrus.exe; setup.cmd puts it in %SKYRIM_TOOLS_HOME%\\papyrus-compiler
  ck    the Creation Kit's PapyrusCompiler.exe: %SKYRIM_GAME_DIR%\\Papyrus Compiler\\, or the copy shipped in the
        papyrus-compiler archive (papyrus-compiler\\Original Compiler\\)
  --compiler-exe PATH --compiler-kind open|ck   use that executable (any compiler with the same command line)

Imports, highest precedence first (a script name resolves to its FIRST provider, like the MO2 VFS):
  the folders of the inputs, every -i, MO2 overwrite\\, the enabled mods of the profile from the top of modlist.txt
  (top line = highest priority), then the game's Data last. A folder counts when it is <root>\\Source\\Scripts or
  <root>\\Scripts\\Source and holds a .psc. MO2 comes from SKYRIM_MO2_DIR, the game from SKYRIM_GAME_DIR or
  gamePath in ModOrganizer.ini; --no-mo2 uses only the inputs and -i.

Output: the .pex files land in <out dir> as given; for a mod that is <new MO2 mod folder>\\Scripts. A folder of an
installed mod (one with meta.ini) is refused unless --into-existing-mod: never write into another author's mod.
Success is a .pex WRITTEN by this run with the Papyrus magic, not the exit code. Exit 0 = every input compiled,
1 = some failed, 2 = usage error, 3 = no compiler. Nothing is tested in game by this.
"""
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time

PEX_MAGIC = 0xFA57C0DE
LAYOUTS = (("Source", "Scripts"), ("Scripts", "Source"))
ANSI = re.compile(r"\x1b\[[0-9;]*m")
# open compiler: "path:line:col: error: message";  CK: "path(line,col): message"
DIAG_OPEN = re.compile(r"^(?P<file>.+?\.psc):(?P<line>\d+):(?P<col>\d+):\s*(?P<kind>error|warning|notice)?:?\s*(?P<msg>.*)$", re.I)
DIAG_CK = re.compile(r"^(?P<file>.+?\.psc)\((?P<line>\d+),(?P<col>\d+)\):\s*(?P<msg>.*)$", re.I)
UNRESOLVED = re.compile(r"unknown type|is not a known user-defined|could not be resolved|not found|undefined|"
                        r"cannot find|unknown (?:object|identifier|function|variable|property)", re.I)


def tools_home():
    return os.environ.get("SKYRIM_TOOLS_HOME") or os.path.join(os.environ.get("LOCALAPPDATA", ""), "SkyrimTools")


def repo_root():
    return os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))


# ------------------------------------------------------------------------------------------------ compilers
def find_compilers():
    """[(kind, exe, origin)] of every compiler found, in auto-preference order."""
    found = []
    homes = [os.environ.get("PAPYRUS_COMPILER_DIR", ""), os.path.join(tools_home(), "papyrus-compiler"),
             os.path.join(repo_root(), "tools", "papyrus-compiler")]
    for h in [h for h in homes if h]:
        for sub in ("", "papyrus-compiler"):
            exe = os.path.join(h, sub, "papyrus.exe")
            if os.path.isfile(exe):
                found.append(("open", exe, h))
    game = game_dir(mo2_dir())
    ck = []
    if game:
        ck.append(os.path.join(game, "Papyrus Compiler", "PapyrusCompiler.exe"))
    for _, exe, _ in list(found):
        ck.append(os.path.join(os.path.dirname(exe), "Original Compiler", "PapyrusCompiler.exe"))
    for exe in ck:
        if os.path.isfile(exe):
            found.append(("ck", exe, os.path.dirname(exe)))
    seen, out = set(), []
    for kind, exe, origin in found:
        key = os.path.normcase(os.path.abspath(exe))
        if key not in seen:
            seen.add(key)
            out.append((kind, os.path.abspath(exe), origin))
    return out


def pick_compiler(want, exe_override=None, kind_override=None):
    if exe_override:
        if not os.path.isfile(exe_override):
            die(3, "compiler not found: %s" % exe_override)
        kind = kind_override or ("ck" if "papyruscompiler" in os.path.basename(exe_override).lower() else "open")
        return kind, os.path.abspath(exe_override)  # a .py stub runs under this Python (the self-test uses one)
    comps = find_compilers()
    for kind, exe, _ in comps:
        if want in ("auto", kind):
            return kind, exe
    die(3, "no %s Papyrus compiler found. Install the open-source one with setup.cmd (it lands in %s), or the "
           "Creation Kit (its PapyrusCompiler.exe is in <game>\\Papyrus Compiler\\), or pass --compiler-exe."
        % ("" if want == "auto" else want, os.path.join(tools_home(), "papyrus-compiler")))


# ------------------------------------------------------------------------------------------------ MO2
def ini_value(text, key):
    m = re.search(r"^\s*%s\s*=\s*(.*)$" % re.escape(key), text, re.M | re.I)
    if not m:
        return ""
    v = m.group(1).strip()
    v = re.sub(r"^@ByteArray\((.*)\)$", r"\1", v)
    return v.replace("\\\\", "\\").strip('"')


def mo2_dir():
    d = os.environ.get("SKYRIM_MO2_DIR", "")
    return d if d and os.path.isfile(os.path.join(d, "ModOrganizer.ini")) else ""


def mo2_settings(mo2):
    text = open(os.path.join(mo2, "ModOrganizer.ini"), encoding="utf-8", errors="replace").read()
    base = ini_value(text, "base_directory") or mo2

    def path_of(key, default):
        v = ini_value(text, key)
        v = v.replace("%BASE_DIR%", base) if v else os.path.join(base, default)
        return os.path.normpath(os.path.join(mo2, v))

    return {"text": text, "mods": path_of("mod_directory", "mods"), "overwrite": path_of("overwrite_directory", "overwrite"),
            "profiles": path_of("profiles_directory", "profiles"), "profile": ini_value(text, "selected_profile"),
            "gamePath": ini_value(text, "gamePath")}


def game_dir(mo2):
    g = os.environ.get("SKYRIM_GAME_DIR", "")
    if g and os.path.isdir(g):
        return g
    if mo2:
        gp = mo2_settings(mo2)["gamePath"]
        if gp:
            g = os.path.normpath(os.path.join(mo2, gp))
            if os.path.isdir(g):
                return g
    return ""


def enabled_mods(mo2, profile=None):
    """Enabled mod folders, highest priority first (modlist.txt is written top = highest)."""
    s = mo2_settings(mo2)
    profile = profile or s["profile"]
    modlist = os.path.join(s["profiles"], profile, "modlist.txt")
    if not os.path.isfile(modlist):
        die(2, "no modlist.txt for profile %r: %s" % (profile, modlist))
    mods = []
    for line in open(modlist, encoding="utf-8", errors="replace"):
        line = line.rstrip("\r\n")
        if line.startswith("+") and not line.endswith("_separator"):
            mods.append(os.path.join(s["mods"], line[1:]))
    return s, profile, mods


def source_dirs(root):
    """<root>\\Source\\Scripts and <root>\\Scripts\\Source that hold a .psc (case-insensitive, either layout)."""
    out = []
    for a, b in LAYOUTS:
        d = os.path.join(root, a, b)
        if os.path.isdir(d) and any(f.lower().endswith(".psc") for f in os.listdir(d)):
            out.append(d)
    return out


def import_roots(inputs, extras, use_mo2=True, profile=None):
    """[(dir, origin)] highest precedence first, deduplicated by real path (first occurrence keeps its slot)."""
    roots = []
    for p in inputs:
        roots.append((p if os.path.isdir(p) else os.path.dirname(os.path.abspath(p)), "input"))
    roots += [(d, "-i") for d in extras]
    mo2 = mo2_dir() if use_mo2 else ""
    if mo2:
        s, prof, mods = enabled_mods(mo2, profile)
        roots += [(d, "MO2 overwrite") for d in source_dirs(s["overwrite"])]
        for m in mods:
            roots += [(d, "mod: " + os.path.basename(m)) for d in source_dirs(m)]
    game = game_dir(mo2) if use_mo2 else ""
    if game:
        roots += [(d, "game Data") for d in source_dirs(os.path.join(game, "Data"))]
    seen, out = set(), []
    for d, origin in roots:
        key = os.path.normcase(os.path.realpath(d))
        if key not in seen and os.path.isdir(d):
            seen.add(key)
            out.append((os.path.abspath(d), origin))
    return out


def stage_headers(roots, exclude_names, dest):
    """Copy every script name's FIRST provider into one folder, so precedence is ours, not the compiler's."""
    providers = {}
    for d, origin in roots:
        for f in os.listdir(d):
            if not f.lower().endswith(".psc"):
                continue
            name = f[:-4].lower()
            if name in exclude_names or name in providers:
                continue
            providers[name] = (os.path.join(d, f), origin)
    for name, (src, _) in providers.items():
        target = os.path.join(dest, os.path.basename(src))
        try:
            os.link(src, target)
        except OSError:
            shutil.copyfile(src, target)
    return providers


# ------------------------------------------------------------------------------------------------ vanilla headers
HEADER_VERSION = "2"
VANILLA_BSAS = ("Skyrim - Misc.bsa", "Update.bsa", "Dawnguard.bsa", "HearthFires.bsa", "Dragonborn.bsa")  # later wins
OBJECT_TYPES_PRIMITIVE = {"bool", "int", "float", "string"}


def bsa_pex(path):
    """{name: bytes} of the scripts\\*.pex in an SSE (v105) or LE (v104) BSA; LZ4/zlib-compressed entries are skipped."""
    data = open(path, "rb").read()
    magic, ver, off, flags, nfold, nfile, _, _, _ = struct.unpack_from("<4sIIIIIIIH", data, 0)
    if magic != b"BSA\0" or ver not in (104, 105):
        return {}, 0
    rec = 24 if ver == 105 else 16
    folders = []
    for k in range(nfold):
        _, count = struct.unpack_from("<QI", data, off + k * rec)
        folders.append(count)
    p = off + nfold * rec
    entries = []
    for count in folders:
        name = ""
        if flags & 1:
            n = data[p]
            name = data[p + 1:p + n].decode("cp1252", "replace").lower()  # bzstring, length includes the NUL
            p += 1 + n
        for _ in range(count):
            _, size, foff = struct.unpack_from("<QII", data, p)
            p += 16
            entries.append((name, size, foff))
    names = []
    if flags & 2:
        for _ in range(nfile):
            e = data.index(b"\0", p)
            names.append(data[p:e].decode("cp1252", "replace").lower())
            p = e + 1
    out, skipped = {}, 0
    for k, (folder, size, foff) in enumerate(entries):
        if folder != "scripts" or k >= len(names) or not names[k].endswith(".pex"):
            continue
        compressed = bool(flags & 4) != bool(size & 0x40000000)
        size &= 0x3FFFFFFF
        start = foff
        if flags & 0x100:  # embedded full path, a bstring
            start += 1 + data[foff]
            size -= 1 + data[foff]
        if compressed:
            skipped += 1
            continue
        out[names[k][:-4]] = data[start:start + size]
    return out, skipped


def pex_objects(buf):
    """[(name, parent, properties[(type,name)], functions[(name, ret, params[(type,name)], native, global)])]."""
    p = [0]

    def u(fmt):
        v = struct.unpack_from(">" + fmt, buf, p[0])
        p[0] += struct.calcsize(">" + fmt)
        return v[0]

    def ws():
        n = u("H")
        s = buf[p[0]:p[0] + n].decode("cp1252", "replace")
        p[0] += n
        return s

    if u("I") != PEX_MAGIC:
        raise ValueError("not a .pex")
    u("B"), u("B"), u("H"), u("Q")
    ws(), ws(), ws()
    st = [ws() for _ in range(u("H"))]
    if u("B"):  # debug info
        u("Q")
        for _ in range(u("H")):
            u("H"), u("H"), u("H"), u("B")
            n = u("H")  # not "p[0] += 2 * u()": that reads p[0] before u() moves it
            p[0] += 2 * n
    for _ in range(u("H")):  # user flags
        u("H"), u("B")

    def skip_data():
        t = u("B")
        p[0] += {0: 0, 1: 2, 2: 2, 3: 4, 4: 4, 5: 1}[t]

    def func(name):
        ret = st[u("H")]
        u("H"), u("I")
        fl = u("B")
        params = [(st[u("H")], st[u("H")]) for _ in range(u("H"))]
        params = [(t, n) for n, t in params]
        for _ in range(u("H")):
            u("H"), u("H")
        for _ in range(u("H")):  # instructions
            op = u("B")
            n = OPCODE_ARGS[op]
            for _ in range(n):
                skip_data()
            if op in (23, 24, 25):
                t = u("B")
                cnt = u("i") if t == 3 else 0
                for _ in range(cnt):
                    skip_data()
        return (name, ret, params, bool(fl & 2), bool(fl & 1))

    objects = []
    for _ in range(u("H")):
        name = st[u("H")]
        u("I")
        parent = st[u("H")]
        u("H"), u("I"), u("H")
        for _ in range(u("H")):  # variables
            u("H"), u("H"), u("I")
            skip_data()
        props = []
        for _ in range(u("H")):
            pn, pt = st[u("H")], st[u("H")]
            u("H"), u("I")
            fl = u("B")
            if fl & 4:
                u("H")
            else:
                if fl & 1:
                    func("get")
                if fl & 2:
                    func("set")
            props.append((pt, pn))
        funcs = []
        for _ in range(u("H")):
            state = st[u("H")]
            for _ in range(u("H")):
                f = func(st[u("H")])
                if state == "":
                    funcs.append(f)
        objects.append((name, parent, props, funcs))
    return objects


OPCODE_ARGS = {0: 0, 1: 3, 2: 3, 3: 3, 4: 3, 5: 3, 6: 3, 7: 3, 8: 3, 9: 3, 10: 2, 11: 2, 12: 2, 13: 2, 14: 2, 15: 3,
               16: 3, 17: 3, 18: 3, 19: 3, 20: 1, 21: 2, 22: 2, 23: 3, 24: 2, 25: 3, 26: 1, 27: 3, 28: 3, 29: 3,
               30: 2, 31: 2, 32: 3, 33: 3, 34: 4, 35: 4}


def corpus_signatures():
    """{(class, name): (kind, {param: default or None})} from the papyrus-reference corpus (vanilla + SKSE)."""
    ref = os.path.join(repo_root(), "skills", "papyrus-reference", "references")
    idx = os.path.join(ref, "index.jsonl")
    out = {}
    if not os.path.isfile(idx):
        return out
    import json
    files = {}
    for line in open(idx, encoding="utf-8"):
        e = json.loads(line)
        q = e.get("qualified", "").replace("#", ".")  # "Debug.Trace" for globals, "Actor#EquipItem" for methods
        if e.get("source") not in ("vanilla", "skse") or "." not in q:
            continue
        path = os.path.join(os.path.dirname(ref), e["file"])
        if path not in files:
            files[path] = open(path, encoding="utf-8").read().splitlines()
        block = files[path][e["line_start"] - 1:e["line_end"]]
        defaults = {}
        for row in block:
            cells = [c.strip() for c in row.split("|")]
            if len(cells) >= 6 and cells[1].startswith("`") and cells[2].startswith("`"):
                pname, ptype = cells[1].strip("`").lower(), cells[2].strip("`")
                required, default = cells[3], cells[4].strip("`")
                if "✓" not in required:
                    if not default and ptype.lower() not in OBJECT_TYPES_PRIMITIVE:
                        default = "None"
                    if default:
                        if ptype.lower() == "float" and re.fullmatch(r"-?\d+", default):
                            default += ".0"
                        defaults[pname] = default
        cls, name = q.rsplit(".", 1)
        key = (cls.lower(), name.lower())
        prev = out.get(key)
        if prev is None or (e["source"] == "skse" and prev[0] != "event"):
            out[key] = (e["kind"], defaults)
    return out


def header_text(obj, sigs, origin):
    name, parent, props, funcs = obj
    lines = ["ScriptName %s%s Hidden" % (name, " extends " + parent if parent else ""),
             "; generated by SkyrimTools papyrusc.py from %s: declarations only, never compile or ship this file" % origin]
    lines += ["%s Property %s Auto" % (t, n) for t, n in props]
    for fname, ret, params, native, glob in funcs:
        if fname.lower() in ("gotostate", "getstate", "onbeginstate", "onendstate"):
            continue  # the compiler generates GotoState/GetState into every script; state events are built in
        kind, defaults = sigs.get((name.lower(), fname.lower()), (None, {}))
        is_event = kind == "event" or (kind is None and not native and not glob and ret.lower() == "none"
                                       and fname.lower().startswith("on"))
        args = []
        for t, n in params:
            d = defaults.get(n.lower())
            args.append("%s %s%s" % (t, n, " = " + d if d else ""))
        # defaults must be trailing: drop any default followed by a required parameter
        seen_required = False
        for k in range(len(args) - 1, -1, -1):
            if " = " not in args[k]:
                seen_required = True
            elif seen_required:
                args[k] = args[k].split(" = ")[0]
        sig = "%s(%s)" % (fname, ", ".join(args))
        if is_event:
            lines += ["Event " + sig, "EndEvent"]
        else:
            lines.append("%sFunction %s native%s" % ("" if ret.lower() == "none" else ret + " ", sig, " global" if glob else ""))
    return "\n".join(lines) + "\n"


def vanilla_headers(rebuild=False, quiet=False):
    """Folder of generated vanilla headers (cached per game install), or "" when the game BSAs are not found."""
    game = game_dir(mo2_dir())
    if not game:
        return ""
    bsas = [os.path.join(game, "Data", b) for b in VANILLA_BSAS if os.path.isfile(os.path.join(game, "Data", b))]
    if not bsas:
        return ""
    import hashlib
    corpus = os.path.join(repo_root(), "skills", "papyrus-reference", "references", "index.jsonl")
    key = "|".join([HEADER_VERSION] + ["%s:%d:%d" % (b, os.path.getsize(b), os.path.getmtime(b)) for b in bsas] +
                   ["%d" % os.path.getmtime(corpus) if os.path.isfile(corpus) else ""])
    dest = os.path.join(tools_home(), "papyrus-headers", hashlib.sha1(key.encode()).hexdigest()[:12])
    if os.path.isfile(os.path.join(dest, ".complete")) and not rebuild:
        return dest
    parent = os.path.dirname(dest)
    if os.path.isdir(parent):  # one cache per game install: older builds are stale
        for old in os.listdir(parent):
            if os.path.isfile(os.path.join(parent, old, ".complete")) or old == os.path.basename(dest):
                shutil.rmtree(os.path.join(parent, old), ignore_errors=True)
    os.makedirs(dest)
    sigs = corpus_signatures()
    pex, skipped, bad = {}, 0, 0
    for b in bsas:
        found, s = bsa_pex(b)
        skipped += s
        for n, buf in found.items():
            pex[n] = (buf, os.path.basename(b))
    written = 0
    for n, (buf, origin) in sorted(pex.items()):
        try:
            objs = pex_objects(buf)
        except (ValueError, struct.error, KeyError, IndexError):
            bad += 1
            continue
        for obj in objs:
            with open(os.path.join(dest, obj[0] + ".psc"), "w", encoding="utf-8", newline="\n") as f:
                f.write(header_text(obj, sigs, origin + " scripts\\" + n + ".pex"))
            written += 1
    with open(os.path.join(dest, ".complete"), "w") as f:
        f.write("%d headers from %s; %d compressed entries skipped, %d unreadable .pex\n"
                % (written, ", ".join(os.path.basename(b) for b in bsas), skipped, bad))
    if not quiet:
        print("generated %d vanilla headers in %s (%d compressed skipped, %d unreadable)" % (written, dest, skipped, bad))
    return dest


# ------------------------------------------------------------------------------------------------ compile
def collect_inputs(paths):
    files = []
    for p in paths:
        if os.path.isdir(p):
            files += sorted(os.path.join(p, f) for f in os.listdir(p) if f.lower().endswith(".psc"))
        elif p.lower().endswith(".psc") and os.path.isfile(p):
            files.append(p)
        else:
            die(2, "not a .psc file or a folder of them: %s" % p)
    if not files:
        die(2, "no .psc files in %s" % ", ".join(paths))
    return [os.path.abspath(f) for f in files]


def guard_output(out, allow_existing_mod):
    out = os.path.abspath(out)
    mo2 = mo2_dir()
    if mo2:
        mods = os.path.normcase(mo2_settings(mo2)["mods"]) + os.sep
        if os.path.normcase(out).startswith(mods):
            mod = os.path.join(mo2_settings(mo2)["mods"], out[len(mods):].split(os.sep)[0])  # normcase keeps lengths
            if os.path.isfile(os.path.join(mod, "meta.ini")) and not allow_existing_mod:
                die(2, "refusing to write into the installed mod %r (it has meta.ini): put the .pex into a NEW mod "
                       "folder, e.g. %s, or pass --into-existing-mod if this mod is yours"
                    % (os.path.basename(mod), os.path.join(os.path.dirname(mod), "My Patch", "Scripts")))
    game = game_dir(mo2)
    if game and os.path.normcase(out).startswith(os.path.normcase(os.path.join(game, "Data")) + os.sep) and not allow_existing_mod:
        die(2, "refusing to write into the game's Data folder: use a new MO2 mod folder (or --into-existing-mod)")
    return out


def find_flags(compiler_exe, roots):
    for d in [os.path.dirname(compiler_exe)] + [r for r, _ in roots]:
        f = os.path.join(d, "TESV_Papyrus_Flags.flg")
        if os.path.isfile(f):
            return f
    return ""


def parse_diags(text):
    diags = []
    for raw in text.splitlines():
        line = ANSI.sub("", raw).strip()
        m = DIAG_OPEN.match(line) or DIAG_CK.match(line)
        if m:
            g = m.groupdict()
            kind = (g.get("kind") or ("warning" if "warning" in g["msg"].lower()[:10] else "error")).lower()
            diags.append((os.path.basename(g["file"]), int(g["line"]), int(g["col"]), kind, g["msg"].strip()))
    seen, out = set(), []
    for d in diags:
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


def is_pex(path):
    try:
        with open(path, "rb") as f:
            return struct.unpack(">I", f.read(4))[0] == PEX_MAGIC
    except (OSError, struct.error):
        return False


def compile_cmd(args):
    out = guard_output(args.out, args.into_existing_mod)
    inputs = collect_inputs(args.inputs)
    kind, exe = pick_compiler(args.compiler, args.compiler_exe, args.compiler_kind)
    roots = import_roots(args.inputs, args.imports, not args.no_mo2, args.profile)
    if not args.no_vanilla_headers and not args.no_mo2:  # both compilers accept the bodyless native headers
        vh = vanilla_headers()
        if vh:
            roots.append((vh, "vanilla headers (generated)"))
    if not args.check:
        os.makedirs(out, exist_ok=True)
    names = {os.path.basename(f)[:-4].lower() for f in inputs}
    print("compiler: %s  %s" % (kind, exe))
    print("imports:  %d folders (%s)" % (len(roots), ", ".join(o for _, o in roots[:6]) + (", ..." if len(roots) > 6 else "")))
    if not any(o == "game Data" or o.startswith("mod: ") for _, o in roots):
        print("  note: no MO2/game sources in the imports; vanilla types (Quest, Actor, ...) resolve only through -i")
    started = time.time() - 1.0  # file times on some filesystems are coarse
    log = []
    with tempfile.TemporaryDirectory(prefix="papyrusc-") as tmp:
        if kind == "open":
            headers = os.path.join(tmp, "headers")
            os.makedirs(headers)
            providers = stage_headers(roots, names, headers)
            print("headers:  %d scripts staged (first provider wins)" % len(providers))
            staged_inputs = os.path.join(tmp, "inputs")  # one folder: hundreds of paths overflow the command line
            os.makedirs(staged_inputs)
            for f in inputs:
                try:
                    os.link(f, os.path.join(staged_inputs, os.path.basename(f)))
                except OSError:
                    shutil.copyfile(f, os.path.join(staged_inputs, os.path.basename(f)))
            cmd = [exe, "compile", "-nocache", "-h", headers, "-i", staged_inputs, "-o", out if not args.check else tmp]
            if args.check:
                cmd.append("-check")
            runs = [cmd]
        else:
            flags = find_flags(exe, roots)
            if not flags:
                die(2, "TESV_Papyrus_Flags.flg not found next to the compiler or in the imports")
            imp = ";".join(r for r, _ in roots)
            if len(imp) > 30000:
                die(2, "the import path is too long for one command line (%d chars): narrow it with --no-mo2 -i ..." % len(imp))
            common = ["-f=" + flags, "-i=" + imp, "-o=" + (out if not args.check else tmp)]
            # a folder input is one -all run (the CK starts slowly: once per file costs ~1 s each)
            runs = [[exe, os.path.abspath(p), "-all"] + common for p in args.inputs if os.path.isdir(p)]
            runs += [[exe, os.path.abspath(p)] + common for p in args.inputs if not os.path.isdir(p)]
        env = dict(os.environ, VERROR_PATHS="absolute")
        if exe.lower().endswith(".py"):
            runs = [[sys.executable] + cmd for cmd in runs]
        for cmd in runs:
            try:
                p = subprocess.run(cmd, capture_output=True, timeout=args.timeout, env=env, cwd=tmp)
            except subprocess.TimeoutExpired:
                die(1, "the compiler did not finish within %ds" % args.timeout)
            except OSError as e:
                die(3, "could not run %s: %s" % (exe, e))
            log.append(p.stdout.decode("utf-8", "replace") + "\n" + p.stderr.decode("utf-8", "replace"))
    text = "\n".join(log)
    diags = parse_diags(text)
    ok, failed = [], []
    for f in inputs:
        name = os.path.basename(f)[:-4]
        pex = os.path.join(out, name + ".pex")
        if args.check:
            (failed if any(d[0].lower() == os.path.basename(f).lower() and d[3] == "error" for d in diags) else ok).append(name)
        elif os.path.isfile(pex) and os.path.getmtime(pex) >= started and is_pex(pex):
            ok.append(name)
        else:
            failed.append(name)
    for d in diags:
        print("  %s(%d,%d): %s: %s" % d)
    if failed and not diags:
        tail = [l for l in ANSI.sub("", text).splitlines() if l.strip()][-15:]
        print("  compiler output (no diagnostics recognised):")
        for l in tail:
            print("    " + l)
    errors = [d for d in diags if d[3] == "error"]
    if errors and sum(1 for d in errors if UNRESOLVED.search(d[4])) * 3 >= len(errors) * 2:
        print("hint: most errors are unknown names: usually a missing import (unless the name is a typo). Check"
              " `papyrusc.py imports`: the mod that ships those .psc (SKSE, SkyUI SDK, PapyrusUtil, ...) must be enabled"
              " in MO2 or passed with -i.")
    if failed and ok == [] and kind == "open" and len(inputs) > 1 and errors:
        print("note: papyrus-compiler writes no .pex when any input has an error; fix the files above or compile the"
              " others by name (the CK compiler, --compiler ck, builds each file on its own)")
    verb = "checked" if args.check else "compiled"
    print("%s %d of %d: %s%s" % (verb, len(ok), len(inputs), ", ".join(ok) or "-",
                                  ("; FAILED: " + ", ".join(failed)) if failed else ""))
    if ok and not args.check:
        print("output: %s  (a new MO2 mod does nothing until it is enabled; NOT tested in game)" % out)
    return 1 if failed else 0


# ------------------------------------------------------------------------------------------------ CLI
class Args:
    pass


def die(code, msg):
    print("papyrusc: " + msg, file=sys.stderr)
    sys.exit(code)


def parse(argv):
    a = Args()
    a.cmd, a.inputs, a.imports, a.out, a.compiler, a.profile = argv[0], [], [], "", "auto", None
    a.no_mo2 = a.check = a.into_existing_mod = a.no_vanilla_headers = a.rebuild = False
    a.compiler_exe = a.compiler_kind = None
    a.timeout = 300
    it = iter(argv[1:])
    for x in it:
        try:
            if x in ("-o", "--out"):
                a.out = next(it)
            elif x in ("-i", "--import"):
                a.imports.append(os.path.abspath(next(it)))
            elif x == "--compiler":
                a.compiler = next(it)
            elif x == "--compiler-exe":
                a.compiler_exe = next(it)
            elif x == "--compiler-kind":
                a.compiler_kind = next(it)
            elif x == "--profile":
                a.profile = next(it)
            elif x == "--timeout":
                a.timeout = int(next(it))
            elif x == "--no-mo2":
                a.no_mo2 = True
            elif x == "--no-vanilla-headers":
                a.no_vanilla_headers = True
            elif x == "--rebuild":
                a.rebuild = True
            elif x == "--check":
                a.check = True
            elif x == "--into-existing-mod":
                a.into_existing_mod = True
            elif x.startswith("-"):
                die(2, "unknown option %s (see --help)" % x)
            else:
                a.inputs.append(x)
        except StopIteration:
            die(2, "%s needs a value" % x)
    if a.compiler not in ("auto", "open", "ck") or a.compiler_kind not in (None, "open", "ck"):
        die(2, "--compiler is auto|open|ck, --compiler-kind is open|ck")
    return a


def main():
    argv = sys.argv[1:]
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    help_flag = "-h" in argv or "--help" in argv
    if help_flag or not argv or argv[0] not in ("compile", "imports", "which", "headers"):
        print(__doc__.strip())
        sys.exit(0 if help_flag else 2)
    a = parse(argv)
    if a.cmd == "which":
        comps = find_compilers()
        for kind, exe, origin in comps:
            print("%-4s %s" % (kind, exe))
        if not comps:
            print("no Papyrus compiler found (setup.cmd installs the open-source one into %s)"
                  % os.path.join(tools_home(), "papyrus-compiler"))
        return 0 if comps else 3
    if a.cmd == "headers":
        d = vanilla_headers(rebuild=a.rebuild)
        if not d:
            die(3, "game not found (SKYRIM_GAME_DIR / gamePath in ModOrganizer.ini) or no vanilla BSA in its Data")
        print(d)
        print(open(os.path.join(d, ".complete")).read().strip())
        return 0
    if a.cmd == "imports":
        roots = import_roots(a.inputs, a.imports, not a.no_mo2, a.profile)
        if not a.no_mo2 and not a.no_vanilla_headers:
            vh = vanilla_headers(quiet=True)
            if vh:
                roots.append((vh, "vanilla headers (generated)"))
        for k, (d, origin) in enumerate(roots, 1):
            n = sum(1 for f in os.listdir(d) if f.lower().endswith(".psc"))
            print("%3d  %-5d %-40s %s" % (k, n, origin[:40], d))
        if not roots:
            print("no import folders: set SKYRIM_MO2_DIR (setup.cmd) or pass -i")
        return 0
    if not a.out:
        die(2, "compile needs -o <out dir>")
    if not a.inputs:
        die(2, "compile needs at least one .psc or folder")
    return compile_cmd(a)


if __name__ == "__main__":
    sys.exit(main())
