"""Compare two Skyrim plugins record by record, or summarise what a plugin adds and overrides.

Ported from skyrim-ai-assistant-toolkit (c) 2026 WingedGuardian, MIT License.
READ-ONLY: the bytes are parsed directly (nested GRUPs, compressed records, XXXX subrecords), never written
and never handed to xEdit, so a result both agree on is not one tool's opinion repeated. A structure this
parser cannot walk stops the run with the byte offset; a record it can only read partly (a body that does
not inflate, a FormID that appears twice, a FormID past the master list, malformed subrecords) is listed as
a PROBLEM and the run says INCONCLUSIVE instead of reporting a clean result.

python espdiff.py diff OLD NEW        what was ADDED, REMOVED or CHANGED, and in which subrecords
python espdiff.py summary PLUGIN [PLUGIN ...] [--list-overrides]
                                      masters, new records by type, overrides by type and by master

Records are matched by FormID in each plugin's own master numbering, so when the master lists differ an
override can shift and show as removed + added: read the masters lines first. A record is an override when
its FormID's high byte indexes one of the plugin's own masters; which plugin finally wins that record in a
load order is a different question.

diff exit: 0 header and every record identical - 1 something differs, or a plugin was read only partly
(INCONCLUSIVE) - 2 usage, or a file this parser cannot walk.
summary exit: 0 every plugin read cleanly - 1 a plugin was read only partly - 2 usage, or a file this
parser cannot walk.
"""
import collections
import hashlib
import os
import struct
import sys
import zlib

COMPRESSED_FLAG = 0x00040000
HEADER_FLAGS = ((0x1, "ESM"), (0x80, "localized"), (0x200, "ESL"))
RECORD_HEADER = 24
MAX_GROUP_DEPTH = 64        # real plugins nest a few levels; a crafted file must not reach Python's limit
MAX_NAME = 512


class PluginError(ValueError):
    """The file is not a plugin this parser can walk; the message names the byte offset."""


Record = collections.namedtuple("Record", "type formid edid flags sha1 body")


class Plugin:
    def __init__(self, header, records, problems):
        self.header = header                   # the TES4 record
        self.records = records                 # every record in file order, duplicates included
        self.problems = problems               # what was read only partly; empty for a clean plugin
        self.masters = masters(header.body)
        self.by_formid = {}
        for record in records:
            self.by_formid.setdefault(record.formid, record)

    def is_override(self, record):
        return (record.formid >> 24) < len(self.masters)

    def master_of(self, record):
        return self.masters[record.formid >> 24] if self.is_override(record) else ""

    def header_flag_names(self):
        return [name for bit, name in HEADER_FLAGS if self.header.flags & bit]


def text(raw):
    """Decode a stored string for display: UTF-8 first, then the cp1251 most Russian mods use, then latin-1."""
    for codec in ("utf-8", "cp1251"):
        try:
            return raw.decode(codec)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def subrecords(body, problems=None):
    """Split a record body into [(tag, bytes)], validating every boundary.

    XXXX sizes exactly the following ordinary subrecord. Without a problem list, malformed bytes raise
    PluginError; with one, the valid prefix is returned and the fault is reported. An invalid payload is
    never handed back as if it were complete.
    """
    out, i, big = [], 0, None

    def fail(reason):
        message = "subrecord at body offset %d: %s" % (i, reason)
        if problems is None:
            raise PluginError(message)
        problems.append(message)
        return out

    while i < len(body):
        if i + 6 > len(body):
            return fail("truncated subrecord header")
        tag = body[i:i + 4].decode("latin-1")
        size = struct.unpack_from("<H", body, i + 4)[0]
        if tag == "XXXX":
            if size != 4:
                return fail("an XXXX length must be four bytes")
            if big is not None:
                return fail("XXXX has no following ordinary subrecord")
            if i + 10 > len(body):
                return fail("truncated XXXX payload")
            big = struct.unpack_from("<I", body, i + 6)[0]
            i += 10
            continue
        if big is not None:
            size, big = big, None
        if i + 6 + size > len(body):
            return fail("%s payload length %d runs past the record body" % (tag, size))
        out.append((tag, body[i + 6:i + 6 + size]))
        i += 6 + size
    if big is not None:
        return fail("dangling XXXX without its following subrecord")
    return out


def masters(header_body):
    """The plugin's master names, in order: index = the FormID high byte of an override."""
    return [text(value.rstrip(b"\0")) for tag, value in subrecords(header_body, problems=[]) if tag == "MAST"]


def parse(data):
    """Walk a plugin and return a Plugin; raises PluginError where the structure cannot be followed."""
    records, problems = [], []
    header = []

    def walk(off, end, depth=0):
        if depth > MAX_GROUP_DEPTH:
            raise PluginError("GRUPs nested deeper than %d at offset %d" % (MAX_GROUP_DEPTH, off))
        while off < end:
            if off + RECORD_HEADER > end:
                raise PluginError("truncated record header at offset %d" % off)
            marker = data[off:off + 4]
            size = struct.unpack_from("<I", data, off + 4)[0]
            if marker == b"GRUP":
                # A GRUP's size includes its own header; anything smaller would walk in place forever.
                if size < RECORD_HEADER or off + size > end:
                    raise PluginError("GRUP at offset %d has an impossible size %d" % (off, size))
                walk(off + RECORD_HEADER, off + size, depth + 1)
                off += size
                continue
            if off + RECORD_HEADER + size > end:
                raise PluginError("record %s at offset %d runs past its group or the file"
                                  % (marker.decode("latin-1"), off))
            flags, formid = struct.unpack_from("<II", data, off + 8)
            body = data[off + RECORD_HEADER:off + RECORD_HEADER + size]
            name = marker.decode("latin-1")
            if flags & COMPRESSED_FLAG:
                try:
                    body = zlib.decompress(body[4:])
                except zlib.error as exc:
                    problems.append("%s %08X at offset %d: the compressed body does not inflate (%s); its "
                                    "hash is of the raw bytes" % (name, formid, off, exc))
            edid, issues = "", []
            for tag, value in subrecords(body, problems=issues):
                if tag == "EDID":
                    edid = text(value.rstrip(b"\0"))
                    break
            problems.extend("%s %08X at offset %d: %s" % (name, formid, off, issue) for issue in issues)
            record = Record(name, formid, edid, flags & ~COMPRESSED_FLAG,
                            hashlib.sha1(body).hexdigest(), body)
            if marker == b"TES4" and not header and off == 0:
                header.append(record)
            else:
                records.append(record)
            off += RECORD_HEADER + size

    walk(0, len(data))
    if not header:
        raise PluginError("not a TES4 plugin: the file does not start with a TES4 header record")
    plugin = Plugin(header[0], records, problems)
    seen = collections.Counter(record.formid for record in records)
    for formid, count in sorted(seen.items()):
        if count > 1:
            problems.append("FormID %08X appears %d times (types: %s); indexed by the first"
                            % (formid, count, ",".join(record.type for record in records
                                                       if record.formid == formid)))
    for record in records:
        if record.formid >> 24 > len(plugin.masters):
            problems.append("%s %08X %s: master index %02X is past the %d master(s)"
                            % (record.type, record.formid, record.edid, record.formid >> 24,
                               len(plugin.masters)))
    return plugin


def read(path):
    """(Plugin, sha256 of the raw file)."""
    with open(path, "rb") as fh:
        data = fh.read()
    return parse(data), hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------------------------------
# The two jobs


def changed_tags(body_old, body_new):
    """Which subrecord tags differ, ignoring values that merely changed order."""
    issues = []
    old = collections.Counter(subrecords(body_old, problems=issues))
    new = collections.Counter(subrecords(body_new, problems=issues))
    if issues:
        return "(malformed subrecords)"
    tags = sorted({tag for (tag, _value) in (old - new) + (new - old)})
    return ",".join(tags) if tags else "(same subrecords, different order)"


def diff(path_old, path_new):
    old, sha_old = read(path_old)
    new, sha_new = read(path_new)
    print("byte-identical: {}".format("yes" if sha_old == sha_new else "no"))
    print("masters old: {}".format(old.masters))
    print("masters new: {}".format(new.masters))
    print("header flags old/new: {:08X} {:08X}".format(old.header.flags, new.header.flags))
    print("records old={} new={}".format(len(old.records), len(new.records)))
    differs = 0
    if old.header.sha1 != new.header.sha1 or old.header.flags != new.header.flags:
        differs += 1
        print("HEADER  TES4 changed  subrecords: {}".format(
            changed_tags(old.header.body, new.header.body)))
    a, b = old.by_formid, new.by_formid
    for formid in sorted(set(a) - set(b)):
        differs += 1
        print("REMOVED {:08X} {} {}".format(formid, a[formid].type, a[formid].edid))
    for formid in sorted(set(b) - set(a)):
        differs += 1
        print("ADDED   {:08X} {} {}".format(formid, b[formid].type, b[formid].edid))
    for formid in sorted(set(a) & set(b)):
        record_old, record_new = a[formid], b[formid]
        if (record_old.sha1 != record_new.sha1 or record_old.flags != record_new.flags
                or record_old.type != record_new.type):
            differs += 1
            what = (changed_tags(record_old.body, record_new.body) if record_old.sha1 != record_new.sha1
                    else "(record flags only)")
            print("CHANGED {:08X} {} {}  subrecords: {}{}".format(
                formid, record_old.type, record_old.edid, what,
                "" if record_old.type == record_new.type else "  type -> " + record_new.type))
    problems = [("old", p) for p in old.problems] + [("new", p) for p in new.problems]
    for side, problem in problems:
        print("PROBLEM ({}) {}".format(side, problem))
    if problems:
        print("INCONCLUSIVE: {} problem(s) above; the record comparison may be incomplete".format(len(problems)))
    print("differences: {}".format(differs))
    return 1 if differs or problems else 0


def type_counts(records):
    counts = collections.Counter(record.type for record in records)
    return ", ".join("{} {}".format(tag, count) for tag, count in sorted(counts.items())) or "none"


def summarize(path, list_overrides=False):
    plugin, _sha = read(path)
    overrides = [record for record in plugin.records if plugin.is_override(record)]
    new = [record for record in plugin.records if not plugin.is_override(record)]
    print("== {}".format(os.path.basename(path)))
    print("   masters ({}): {}".format(len(plugin.masters), ", ".join(plugin.masters) or "none"))
    print("   header flags: {:08X} ({})".format(plugin.header.flags,
                                                ", ".join(plugin.header_flag_names()) or "none"))
    print("   records: {} ({} new, {} overrides)".format(len(plugin.records), len(new), len(overrides)))
    print("   new: {}".format(type_counts(new)))
    print("   overrides: {}".format(type_counts(overrides)))
    by_master = collections.Counter(plugin.master_of(record) for record in overrides)
    print("   overrides by master: {}".format(
        ", ".join("{} {}".format(name, count) for name, count in by_master.items()) or "none"))
    if list_overrides:
        for record in sorted(overrides, key=lambda r: r.formid):
            print("   OVERRIDE {:08X} {} {} ({})".format(record.formid, record.type, record.edid,
                                                         plugin.master_of(record)))
    for problem in plugin.problems:
        print("   PROBLEM {}".format(problem))
    print("   problems: {}".format(len(plugin.problems)))
    return 1 if plugin.problems else 0


# --------------------------------------------------------------------------------------------------


def usage_error(message):
    print("espdiff: %s" % message, file=sys.stderr)
    print(__doc__.strip(), file=sys.stderr)
    return 2


def main(argv):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if argv else 2
    command, rest = argv[0], argv[1:]
    try:
        if command == "diff":
            operands = [arg for arg in rest if not arg.startswith("-")]
            if len(operands) != 2 or len(operands) != len(rest):
                return usage_error("diff takes exactly two plugins: OLD NEW")
            return diff(operands[0], operands[1])
        if command == "summary":
            list_overrides = "--list-overrides" in rest
            unknown = [arg for arg in rest if arg.startswith("-") and arg != "--list-overrides"]
            paths = [arg for arg in rest if not arg.startswith("-")]
            if unknown or not paths:
                return usage_error("summary takes PLUGIN [PLUGIN ...] [--list-overrides]")
            worst = 0
            for path in paths:
                try:
                    worst = max(worst, summarize(path, list_overrides))
                except (OSError, PluginError) as exc:
                    print("espdiff: %s: %s" % (path, exc), file=sys.stderr)
                    worst = 2
            return worst
        return usage_error("unknown command %r; it is diff or summary" % command)
    except (OSError, PluginError, struct.error, zlib.error) as exc:
        print("espdiff: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
