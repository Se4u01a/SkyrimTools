"""Read a Skyrim SE/AE/VR save (.ess) with the standard library only: header, LZ4 body, plugin table, raw search.

Ported from skyrim-ai-assistant-toolkit (c) 2026 WingedGuardian, MIT License.
READ-ONLY: nothing here writes, edits or repairs a save. A string or FormID hit is an investigation lead,
not a resolved reference; the structured parts (plugin table, file location table) are counted, not decoded.

python ess_scan.py list [--dir DIR]                 .ess/.skse pairs in the saves folder found on this machine
python ess_scan.py info SAVE|SAVEDIR                header fields, sizes, plugin counts, body structure
python ess_scan.py plugins SAVE|SAVEDIR             the plugin table stored in the save (regular + light)
python ess_scan.py search SAVE|SAVEDIR --string TEXT [--limit N] [--scope body|header|both]
python ess_scan.py search SAVE|SAVEDIR --formid 0001ABCD [--limit N]
python ess_scan.py search SAVE|SAVEDIR --hex DEADBEEF [--limit N]
python ess_scan.py strings SAVE|SAVEDIR [--min 4] [--grep TEXT] [--limit 200]
python ess_scan.py forms SAVE|SAVEDIR [--by-plugin] [--limit N]

SAVE may be a folder: the newest .ess in it is used. For "list" the saves folder is the first of these
that holds .ess files, and the folder used is printed: SKYRIM_DOCUMENTS_DIR (the game folder
under My Games, as for scripts/logs; a Saves or a Documents folder also works), then the Documents folder (SHGetFolderPathW) with My Games\\Skyrim
Special Edition, ...GOG, ...EPIC, then Skyrim VR, then %SKYRIM_MO2_DIR%\\profiles\\*\\saves. An override
that holds no save does not hide the real Documents folder; --dir names one folder outright.

Exit: 0 parsed completely - 1 INCONCLUSIVE, the parse is partial (see "problems" and the stderr line) -
2 usage, an unreadable file, or a file this tool cannot walk.
"""
import ctypes
import json
import os
import struct
import sys
import time

MAGIC = b"TESV_SAVEGAME"
SE_SAVE_VERSION = 12
COMPRESSION_NONE = 0
COMPRESSION_LZ4 = 2
HEADER_START = len(MAGIC) + 4          # the header block starts after magic (13 bytes) and headerSize (4)
MAX_SHOWN = 50                         # contexts kept per search, as in the original tool
PLUGIN_NAME_MAX = 512


class SaveError(ValueError):
    """The input is not a save this tool can walk; the message names the field and the byte offset."""


class Matches(list):
    """Count every raw hit while retaining at most the displayed contexts."""

    def __init__(self, limit=MAX_SHOWN):
        super().__init__()
        self.total = 0
        self.limit = limit

    def add(self, match):
        self.total += 1
        if len(self) < self.limit:
            super().append(match)


class Cursor:
    """Read little-endian fields forward; every read is bounds-checked before it is unpacked."""

    def __init__(self, data, pos=0):
        self.data = data
        self.pos = pos

    def take(self, n):
        if n < 0 or self.pos + n > len(self.data):
            raise SaveError("a %d byte read at offset %d runs past the end of the %d byte(s) available"
                            % (n, self.pos, len(self.data)))
        out = self.data[self.pos:self.pos + n]
        self.pos += n
        return out

    def u8(self):
        return self.take(1)[0]

    def u16(self):
        return struct.unpack("<H", self.take(2))[0]

    def u32(self):
        return struct.unpack("<I", self.take(4))[0]

    def u64(self):
        return struct.unpack("<Q", self.take(8))[0]

    def f32(self):
        return struct.unpack("<f", self.take(4))[0]

    def wstring(self):
        """uint16 byte length, then that many UTF-8 bytes (the format's wstring)."""
        return self.take(self.u16())


def show(raw):
    """Print a stored string without failing on bad bytes; a save may hold any encoding."""
    return raw.decode("utf-8", "replace")


# --------------------------------------------------------------------------------------------------
# LZ4 block decompression (raw block, not an LZ4 frame: what a Skyrim SE/AE/VR save body uses)


def lz4_decompress(src, expected=0):
    """Inflate a raw LZ4 block; `expected` is the size the save header declares and caps the output."""
    out = bytearray()
    i, n = 0, len(src)
    while i < n:
        token = src[i]
        i += 1
        literals = token >> 4
        if literals == 15:
            while True:
                if i >= n:
                    raise SaveError("LZ4: the literal length at block offset %d runs past the block" % i)
                b = src[i]
                i += 1
                literals += b
                if b != 255:
                    break
        if literals:
            if i + literals > n:
                raise SaveError("LZ4: %d literal byte(s) at block offset %d run past the block" % (literals, i))
            if expected and len(out) + literals > expected:
                raise SaveError("LZ4: the block inflates past the %d byte(s) the save declares" % expected)
            out += src[i:i + literals]
            i += literals
        if i >= n:
            break
        if i + 2 > n:
            raise SaveError("LZ4: the match offset at block offset %d is truncated" % i)
        offset = src[i] | (src[i + 1] << 8)
        i += 2
        if offset == 0 or offset > len(out):
            raise SaveError("LZ4: match offset %d at block offset %d points before the %d byte(s) already written"
                            % (offset, i - 2, len(out)))
        length = token & 0x0F
        if length == 15:
            while True:
                if i >= n:
                    raise SaveError("LZ4: the match length at block offset %d runs past the block" % i)
                b = src[i]
                i += 1
                length += b
                if b != 255:
                    break
        length += 4
        start = len(out) - offset
        while length:
            take = min(length, len(out) - start)       # an overlapping match grows one window at a time
            if expected and len(out) + take > expected:
                raise SaveError("LZ4: the block inflates past the %d byte(s) the save declares" % expected)
            out += out[start:start + take]
            length -= take
    return bytes(out)


# --------------------------------------------------------------------------------------------------
# Header (never compressed) and body (LZ4-compressed in every SE/AE/VR save that uses compression)


def parse_header(data):
    """The uncompressed header. A bad field ends the walk and is reported; it does not end the run."""
    if not data.startswith(MAGIC):
        raise SaveError("not a Skyrim save: it does not start with TESV_SAVEGAME")
    fields, problems = {}, []
    c = Cursor(data, len(MAGIC))
    try:
        fields["headerSize"] = c.u32()
        fields["saveVersion"] = c.u32()
        fields["saveNumber"] = c.u32()
        fields["playerName"] = show(c.wstring())
        fields["playerLevel"] = c.u32()
        fields["playerLocation"] = show(c.wstring())
        fields["gameDate"] = show(c.wstring())
        fields["playerRace"] = show(c.wstring())
        fields["playerSex"] = c.u16()
        fields["playerCurExp"] = round(c.f32(), 4)
        fields["playerLvlupExp"] = round(c.f32(), 4)
        fields["filetime"] = c.u64()
        fields["shotWidth"] = c.u32()
        fields["shotHeight"] = c.u32()
        if fields["saveVersion"] >= SE_SAVE_VERSION:   # the SE family only; LE has no compression type
            fields["compressionType"] = c.u16()
    except SaveError as exc:
        problems.append("header: %s" % exc)
    declared = HEADER_START + fields.get("headerSize", 0)
    if "compressionType" in fields and declared != c.pos:
        problems.append("header: headerSize %d puts the header end at %d, the fields end at %d"
                        % (fields["headerSize"], declared, c.pos))
    return fields, c.pos, problems


def read_body(data, fields, header_end, problems):
    """Unpack the body. Returns (body or None, offset of the compressed block); None means INCONCLUSIVE."""
    width, height = fields.get("shotWidth"), fields.get("shotHeight")
    if not width or not height or width > 8192 or height > 8192:
        problems.append("body: the screenshot size %sx%s is not usable, so the body cannot be located"
                        % (width, height))
        return None, -1
    shot_end = header_end + 4 * width * height        # SE stores RGBA pixels, four bytes each
    if shot_end + 8 > len(data):
        problems.append("body: a %dx%d screenshot ends at %d, past the end of the %d byte file"
                        % (width, height, shot_end, len(data)))
        return None, -1
    kind = fields.get("compressionType", COMPRESSION_NONE)
    if kind == COMPRESSION_NONE:
        return data[shot_end:], shot_end
    if kind != COMPRESSION_LZ4:
        problems.append("body: compression type %d is neither none (0) nor LZ4 (2); this tool cannot unpack it"
                        % kind)
        return None, shot_end
    c = Cursor(data, shot_end)
    try:
        uncompressed = c.u32()
        compressed = c.u32()
    except SaveError as exc:
        problems.append("body: %s" % exc)
        return None, shot_end
    start = c.pos
    if uncompressed <= 0 or compressed <= 0 or start + compressed > len(data):
        problems.append("body: the block at %d claims %d byte(s) holding %d uncompressed, the file holds %d "
                        "byte(s) from there" % (start, compressed, uncompressed, len(data) - start))
        return None, start
    if start + compressed != len(data):
        problems.append("body: %d byte(s) trail the compressed block (block %d..%d, file %d)"
                        % (len(data) - start - compressed, start, start + compressed, len(data)))
    try:
        body = lz4_decompress(data[start:start + compressed], uncompressed)
    except SaveError as exc:
        problems.append("body: %s" % exc)
        return None, start
    if len(body) != uncompressed:
        problems.append("body: the block inflated to %d byte(s), the header declares %d"
                        % (len(body), uncompressed))
    return body, start


def read_plugins(body, problems):
    """The plugin table inside the decompressed body: formVersion, pluginInfoSize, regular and light lists."""
    info = {"formVersion": None, "pluginInfoSize": None, "regular": [], "light": [], "end": None}
    c = Cursor(body)
    try:
        info["formVersion"] = c.u8()
        info["pluginInfoSize"] = c.u32()
    except SaveError as exc:
        problems.append("plugins: %s" % exc)
        return info
    block_start = c.pos
    block_end = block_start + info["pluginInfoSize"]
    if block_end > len(body):
        problems.append("plugins: pluginInfoSize %d at offset %d runs past the %d byte body"
                        % (info["pluginInfoSize"], block_start - 4, len(body)))
    try:
        count = c.u8()
        for _ in range(count):
            name = c.wstring()
            if not name or len(name) > PLUGIN_NAME_MAX:
                raise SaveError("regular plugin %d of %d at offset %d has an impossible name length %d"
                                % (len(info["regular"]) + 1, count, c.pos, len(name)))
            info["regular"].append(show(name))
        light_count = c.u16()
        for _ in range(light_count):
            name = c.wstring()
            if not name or len(name) > PLUGIN_NAME_MAX:
                raise SaveError("light plugin %d of %d at offset %d has an impossible name length %d"
                                % (len(info["light"]) + 1, light_count, c.pos, len(name)))
            info["light"].append(show(name))
    except SaveError as exc:
        problems.append("plugins: %s" % exc)
        return info
    if block_end <= len(body) and c.pos != block_end:
        problems.append("plugins: pluginInfoSize %d ends the plugin table at %d, the names end at %d"
                        % (info["pluginInfoSize"], block_end, c.pos))
    info["end"] = c.pos
    return info


LOCATION_OFFSETS = ("formIDArrayCountOffset", "unknown3TableOffset", "globalDataTable1Offset",
                    "globalDataTable2Offset", "changeFormsOffset", "globalDataTable3Offset")
LOCATION_COUNTS = ("globalDataTable1Count", "globalDataTable2Count", "globalDataTable3Count",
                   "changeFormCount")
# The order the offsets are stored in is not the order the tables are written in; these are the same
# six entries sorted by where the data sits, which is what the checks below verify.
LOCATION_DATA_ORDER = ("globalDataTable1Offset", "globalDataTable2Offset", "changeFormsOffset",
                       "globalDataTable3Offset", "formIDArrayCountOffset", "unknown3TableOffset")
LOCATION_UNUSED = 15


def read_location_table(body, pos, base_hint, problems):
    """The file location table: six absolute offsets, four counts, then fifteen unused words.

    The offsets are absolute in the save's uncompressed layout, and this body is that layout from the
    compression pair onwards, so the base differs from zero. It is derived and checked, never assumed:
    the first table entry must land at the end of this table, and every entry must stay inside the body.
    """
    table = {}
    c = Cursor(body, pos)
    try:
        for name in LOCATION_OFFSETS + LOCATION_COUNTS:
            table[name] = c.u32()
        for _ in range(LOCATION_UNUSED):
            c.u32()
    except SaveError as exc:
        problems.append("location table at %d: %s" % (pos, exc))
        return table
    table["tableEnd"] = c.pos
    complaints = []
    for base in (base_hint, 0):
        complaint = offset_complaint(table, c.pos, len(body), base)
        if complaint is None:
            table["offsetBase"] = base
            return table
        complaints.append("base %d: %s" % (base, complaint))
    problems.append("location table at %d: no base makes its offsets fit the body (%s)"
                    % (pos, "; ".join(complaints)))
    return table


def offset_complaint(table, pos, body_len, base):
    """Why these offsets cannot share this base, or None when they can.

    `pos` is where the location table ends: the first global data table starts exactly there, and the
    six offsets must then climb in data order and stay inside the body.
    """
    if base < 0 or base > body_len:
        return "the base is outside the body"
    if table["globalDataTable1Offset"] - base != pos:
        return "globalDataTable1Offset %d does not land at %d where the table ends" % (
            table["globalDataTable1Offset"], pos)
    values = [(table[name] - base, name) for name in LOCATION_DATA_ORDER]
    for value, name in values:
        if value < pos or value > body_len:
            return "%s points at %d, outside %d..%d" % (name, value, pos, body_len)
    for (a, an), (b, bn) in zip(values, values[1:]):
        if a > b:
            return "%s (%d) comes after %s (%d)" % (an, a, bn, b)
    return None


def read_form_id_array(body, table, problems):
    """The FormID array the location table points at: a count, then that many little-endian FormIDs."""
    base = table.get("offsetBase")
    if base is None:
        problems.append("formIDArray: the location table offsets could not be anchored to the body")
        return None, []
    pos = table.get("formIDArrayCountOffset", -1) - base
    if pos < 0 or pos + 4 > len(body):
        problems.append("formIDArray: no usable formIDArrayCountOffset (%s)" % table.get("formIDArrayCountOffset"))
        return None, []
    c = Cursor(body, pos)
    try:
        count = c.u32()
    except SaveError as exc:
        problems.append("formIDArray: %s" % exc)
        return None, []
    if pos + 4 + 4 * count > len(body):
        problems.append("formIDArray: %d FormIDs from %d need %d byte(s), the body holds %d"
                        % (count, pos, pos + 4 + 4 * count, len(body)))
        return count, []
    return count, [struct.unpack_from("<I", body, pos + 4 + 4 * i)[0] for i in range(count)]


def load(path):
    """Parse a save end to end: (result, file bytes, body, plugin table, FormID array)."""
    with open(path, "rb") as fh:
        data = fh.read()
    result = {"filePath": os.path.abspath(path), "fileSize": len(data)}
    problems = result["problems"] = []
    fields, header_end, header_problems = parse_header(data)
    problems.extend(header_problems)
    result.update(fields)
    version = fields.get("saveVersion")
    result["format"] = ("SSE (SE/AE/VR)" if version == SE_SAVE_VERSION
                        else "Skyrim LE" if version == 9 else "unrecognised save version %s" % version)
    if version != SE_SAVE_VERSION:
        problems.append("format: save version %s is not the SSE layout this tool was checked against (12)"
                        % version)
    body, comp_offset = read_body(data, fields, header_end, problems)
    result["compressionOffset"] = comp_offset
    result["decompressedSize"] = len(body) if body is not None else None
    plugins, form_ids = {}, []
    if body is not None:
        plugins = read_plugins(body, problems)
        result.update({"formVersion": plugins["formVersion"], "pluginInfoSize": plugins["pluginInfoSize"],
                       "regularPlugins": len(plugins["regular"]), "lightPlugins": len(plugins["light"]),
                       "totalPlugins": len(plugins["regular"]) + len(plugins["light"])})
        if plugins.get("end") is not None:
            # The compressed block took the place of the data it replaces, so the table offsets are
            # absolute from the two length fields that sit there; an uncompressed body starts there too.
            base_hint = comp_offset - 8 if fields.get("compressionType") == COMPRESSION_LZ4 else comp_offset
            table = read_location_table(body, plugins["end"], base_hint, problems)
            result["locationTable"] = {k: v for k, v in table.items() if k != "unused"}
            count, form_ids = read_form_id_array(body, table, problems)
            result["formIDArrayCount"] = count
    result.setdefault("locationTable", {})
    result.setdefault("formIDArrayCount", None)
    result["complete"] = not problems
    return result, data, body, plugins, form_ids


# --------------------------------------------------------------------------------------------------
# Raw searches: heuristic by design, every hit is a place to look, never a parsed reference


def context(body, pos, needle_len, before=32, after=32):
    return body[max(0, pos - before):min(len(body), pos + needle_len + after)]


def ascii_context(raw):
    return "".join(chr(b) if 32 <= b < 127 else "." for b in raw)


def search_string(body, query, limit):
    hits = Matches(limit)
    needle = query.encode("utf-8", "replace")
    if not needle:
        raise SaveError("the string search pattern is empty")
    start = 0
    while True:
        pos = body.find(needle, start)
        if pos < 0:
            return hits
        raw = context(body, pos, len(needle))
        hits.add({"offset": pos, "context": ascii_context(raw), "hex": raw.hex()})
        start = pos + 1


def search_formid(body, formid, limit):
    hits = Matches(limit)
    needle = struct.pack("<I", formid)
    start = 0
    while True:
        pos = body.find(needle, start)
        if pos < 0:
            return hits
        hits.add({"offset": pos, "hex": context(body, pos, 4, 16, 16).hex()})
        start = pos + 1


def search_hex(body, pattern, limit):
    hits = Matches(limit)
    needle = bytes.fromhex(pattern)
    if not needle:
        raise SaveError("the hex search pattern is empty")
    start = 0
    while True:
        pos = body.find(needle, start)
        if pos < 0:
            return hits
        hits.add({"offset": pos, "hex": context(body, pos, len(needle), 16, 16).hex()})
        start = pos + 1


def printable_runs(body, min_len, limit, grep):
    """Length-bounded ASCII runs: script names and EditorIDs are stored as plain text in the body."""
    out, run, start = [], bytearray(), 0
    stop = len(body)
    for i in range(stop + 1):
        b = body[i] if i < stop else None
        if b is not None and 32 <= b < 127:
            if not run:
                start = i
            run.append(b)
            continue
        if len(run) >= min_len:
            text = run.decode("ascii")
            if not grep or grep.lower() in text.lower():
                out.append({"offset": start, "text": text})
                if len(out) >= limit:
                    return out
        run = bytearray()
    return out


# --------------------------------------------------------------------------------------------------
# Saves folder discovery (the caller may name a folder instead of a file)


def documents_dir():
    """The user's Documents folder: SHGetFolderPathW(CSIDL_PERSONAL), with a USERPROFILE fallback."""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value:
            return buf.value
    except (AttributeError, OSError, ValueError):
        pass
    return os.path.join(os.path.expanduser("~"), "Documents")


GAME_FOLDERS = ("Skyrim Special Edition", "Skyrim Special Edition GOG", "Skyrim Special Edition EPIC",
                "Skyrim VR")


def saves_candidates():
    """Folders to look in, most likely first: the SE Documents folder, its GOG/EPIC variants, VR, MO2 profiles."""
    override = os.environ.get("SKYRIM_DOCUMENTS_DIR")
    out = []
    if override:
        # the game folder under My Games (what scripts/logs means by it), a Saves folder, or a Documents folder
        out.append(os.path.join(override, "Saves"))
        if has_saves(override):
            out.append(override)
        else:
            out.extend(os.path.join(override, "My Games", name, "Saves") for name in GAME_FOLDERS)
    my_games = os.path.join(documents_dir(), "My Games")
    out.extend(os.path.join(my_games, name, "Saves") for name in GAME_FOLDERS)
    mo2 = os.environ.get("SKYRIM_MO2_DIR")
    profiles = os.path.join(mo2, "profiles") if mo2 else ""
    if profiles and os.path.isdir(profiles):
        for profile in sorted(os.listdir(profiles)):
            out.append(os.path.join(profiles, profile, "saves"))
    return out


def has_saves(folder):
    try:
        return any(name.lower().endswith(".ess") for name in os.listdir(folder))
    except OSError:
        return False


def saves_dir():
    """The first candidate folder that holds .ess files, or None."""
    for folder in saves_candidates():
        if has_saves(folder):
            return folder
    return None


def picked_saves(folder):
    """[(mtime, path)] for the .ess files in a folder, newest first."""
    try:
        names = os.listdir(folder)
    except OSError as exc:
        raise SaveError("cannot list %s: %s" % (folder, exc))
    out = []
    for name in names:
        if name.lower().endswith(".ess"):
            path = os.path.join(folder, name)
            try:
                out.append((os.path.getmtime(path), path))
            except OSError:
                continue
    out.sort(reverse=True)
    return out


def resolve_save(argument):
    """A save path, or a folder taken as "the newest .ess in it"."""
    if os.path.isdir(argument):
        saves = picked_saves(argument)
        if not saves:
            raise SaveError("no .ess file in the folder %s" % argument)
        return saves[0][1]
    if not os.path.isfile(argument):
        raise SaveError("no such file: %s" % argument)
    return argument


# --------------------------------------------------------------------------------------------------
# Commands


def emit(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def number(argv, flag, default):
    """Read "--flag N" out of argv; returns (value, argv without the flag and its value)."""
    if flag not in argv:
        return default, argv
    index = argv.index(flag)
    if index + 1 >= len(argv):
        raise SaveError("%s needs a value" % flag)
    try:
        return int(argv[index + 1]), argv[:index] + argv[index + 2:]
    except ValueError:
        raise SaveError("%s needs a number, not %r" % (flag, argv[index + 1]))


def cmd_list(argv):
    folder = None
    if "--dir" in argv:
        index = argv.index("--dir")
        if index + 1 >= len(argv):
            raise SaveError("--dir needs a folder")
        folder = argv[index + 1]
        argv = argv[:index] + argv[index + 2:]
    if argv:
        raise SaveError("list takes no operand besides --dir FOLDER (got %r)" % argv[0])
    if folder is None:
        folder = saves_dir()
    if not folder:
        print("no saves folder found; tried:\n  " + "\n  ".join(saves_candidates()))
        return 2
    saves = picked_saves(folder)
    print("dir: %s" % os.path.abspath(folder))
    if not saves:
        print("no .ess file here")
        return 0
    print("%-19s %11s  %-6s  %s" % ("modified", "size", "cosave", "name"))
    for mtime, path in saves:
        stem = os.path.splitext(path)[0]
        cosave = "yes" if os.path.isfile(stem + ".skse") else "no"
        print("%-19s %11d  %-6s  %s" % (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime)),
                                        os.path.getsize(path), cosave, os.path.basename(path)))
    return 0


def cmd_info(argv):
    if len(argv) != 1:
        raise SaveError("info takes exactly one save file or folder")
    path = resolve_save(argv[0])
    result, _data, _body, _plugins, _form_ids = load(path)
    result["scope"] = "uncompressed header, LZ4 body, plugin table, file location table; raw scanner"
    emit(result)
    return 0 if result["complete"] else 1


def cmd_plugins(argv):
    if len(argv) != 1:
        raise SaveError("plugins takes exactly one save file or folder")
    path = resolve_save(argv[0])
    result, _data, body, plugins, _form_ids = load(path)
    if body is None or not plugins:
        emit({"error": "the body could not be unpacked; the plugin table is unavailable",
              "complete": False, "problems": result["problems"]})
        return 1
    emit({"complete": not result["problems"],
          "scope": "the plugin table of the decompressed body: the load order the save was written with",
          "path": result["filePath"], "saveVersion": result["saveVersion"],
          "formVersion": plugins["formVersion"],
          "regularPlugins": len(plugins["regular"]), "lightPlugins": len(plugins["light"]),
          "totalPlugins": len(plugins["regular"]) + len(plugins["light"]),
          "regular": plugins["regular"], "light": plugins["light"],
          "problems": result["problems"]})
    return 0 if result["complete"] else 1


def cmd_search(argv):
    if not argv:
        raise SaveError("search needs a save")
    path = resolve_save(argv[0])
    limit, rest = number(argv[1:], "--limit", MAX_SHOWN)
    scope, kind, value = "body", None, None
    if "--scope" in rest:
        index = rest.index("--scope")
        if index + 1 >= len(rest):
            raise SaveError("--scope needs a value")
        scope = rest[index + 1]
        rest = rest[:index] + rest[index + 2:]
        if scope not in ("body", "header", "both"):
            raise SaveError("--scope takes body, header or both, not %r" % scope)
    for flag in ("--string", "--hex", "--formid"):
        if flag in rest:
            index = rest.index(flag)
            if index + 1 >= len(rest):
                raise SaveError("%s needs a value" % flag)
            if kind is not None:
                raise SaveError("search takes exactly one of --string, --formid, --hex")
            kind, value = flag[2:], rest[index + 1]
            rest = rest[:index] + rest[index + 2:]
    if rest:
        raise SaveError("unknown argument %r" % rest[0])
    if kind is None:
        raise SaveError("search needs one of --string, --formid, --hex")
    if limit <= 0:
        raise SaveError("--limit must be positive")
    # Validate the query before the file is read: a bad pattern is a usage error (exit 2), not a partial
    # parse of a save that was never searched.
    formid = None
    if kind == "string":
        if not value:
            raise SaveError("--string needs a non-empty value")
    elif kind == "formid":
        try:
            formid = int(value, 16)
        except ValueError:
            raise SaveError("--formid takes hexadecimal, for example 0001ABCD")
    else:
        if not value:
            raise SaveError("--hex needs a value")
        try:
            bytes.fromhex(value)
        except ValueError:
            raise SaveError("--hex takes hexadecimal bytes, for example DEADBEEF")
    result, data, body, _plugins, _form_ids = load(path)
    if body is None:
        emit({"error": "the body could not be unpacked; search needs it", "complete": False,
              "problems": result["problems"]})
        return 1
    regions = []
    if scope in ("header", "both"):
        cut = result.get("compressionOffset") or 0
        regions.append(("header", data[:cut] if cut > 0 else data))
    if scope in ("body", "both"):
        regions.append(("body", body))
    problems = list(result["problems"])
    out = {"filePath": result["filePath"], "query": value, "type": kind, "scope": scope, "regions": []}
    found = 0
    for name, region in regions:
        if kind == "string":
            hits = search_string(region, value, limit)
        elif kind == "formid":
            hits = search_formid(region, formid, limit)
        else:
            hits = search_hex(region, value, limit)
        found += hits.total
        out["regions"].append({"region": name, "matchCount": hits.total, "shown": len(hits),
                               "truncated": hits.total > len(hits), "matches": list(hits)})
    out["matchCount"] = found
    out["scopeNote"] = "raw bytes; a hit is a place to look, not a resolved FormID or a script instance"
    out["problems"] = problems
    emit(out)
    return 1 if problems else 0


def cmd_strings(argv):
    if not argv:
        raise SaveError("strings needs a save")
    path = resolve_save(argv[0])
    limit, rest = number(argv[1:], "--limit", 200)
    min_len, rest = number(rest, "--min", 4)
    grep = None
    if "--grep" in rest:
        index = rest.index("--grep")
        if index + 1 >= len(rest):
            raise SaveError("--grep needs a value")
        grep = rest[index + 1]
        rest = rest[:index] + rest[index + 2:]
    if rest:
        raise SaveError("unknown argument %r" % rest[0])
    if min_len < 1 or limit < 1:
        raise SaveError("--min and --limit must be positive")
    result, _data, body, _plugins, _form_ids = load(path)
    if body is None:
        emit({"error": "the body could not be unpacked; the string scan needs it",
              "complete": False, "problems": result["problems"]})
        return 1
    runs = printable_runs(body, min_len, limit, grep)
    emit({"filePath": result["filePath"], "minLength": min_len, "grep": grep, "shown": len(runs),
          "truncated": len(runs) >= limit, "strings": runs, "problems": result["problems"],
          "scopeNote": "printable ASCII runs of the decompressed body in offset order; script names and "
                       "EditorIDs appear here, and so does ordinary text"})
    return 1 if result["problems"] else 0


def cmd_forms(argv):
    if not argv:
        raise SaveError("forms needs a save")
    path = resolve_save(argv[0])
    by_plugin = "--by-plugin" in argv
    rest = [a for a in argv[1:] if a != "--by-plugin"]
    limit, rest = number(rest, "--limit", 0)
    if rest:
        raise SaveError("forms takes one save; %r is extra" % rest[0])
    result, _data, _body, plugins, form_ids = load(path)
    count = result.get("formIDArrayCount")
    if count is None or (count and not form_ids):
        emit({"error": "the FormID array could not be read", "complete": False,
              "problems": result["problems"]})
        return 1
    order = (plugins.get("regular", []) + plugins.get("light", [])) if plugins else []
    buckets = {}
    for fid in form_ids:
        index = fid >> 24
        name = order[index] if index < len(order) else "index %02X not in the plugin table" % index
        buckets[name] = buckets.get(name, 0) + 1
    out = {"filePath": result["filePath"], "formIDArrayCount": count, "listed": len(form_ids),
           "distinctPlugins": len(buckets),
           "byPlugin": [{"plugin": name, "formIDs": n}
                        for name, n in sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))],
           "problems": result["problems"],
           "scopeNote": "the save's own FormID array, indexed by the high byte, which selects a plugin in the "
                        "save's plugin table; counts, not resolved records"}
    if by_plugin or limit:
        out["formIDs"] = ["%08X" % fid for fid in (form_ids[:limit] if limit else form_ids)]
    emit(out)
    return 1 if result["problems"] else 0


COMMANDS = {"list": cmd_list, "info": cmd_info, "plugins": cmd_plugins, "search": cmd_search,
            "strings": cmd_strings, "forms": cmd_forms}


def main(argv):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if argv else 2
    command = COMMANDS.get(argv[0])
    if command is None:
        print("unknown command %r; one of: %s" % (argv[0], ", ".join(sorted(COMMANDS))), file=sys.stderr)
        print(__doc__.strip(), file=sys.stderr)
        return 2
    try:
        return command(argv[1:])
    except (SaveError, OSError, struct.error) as exc:
        print("ess_scan: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    code = main(sys.argv[1:])
    if code == 1:
        print("INCONCLUSIVE: the report above is a partial parse; see \"problems\"", file=sys.stderr)
    sys.exit(code)
