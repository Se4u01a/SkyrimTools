"""Survey an SKSE co-save (.skse / .skseco) structurally and print JSON: header fields, then a chunk inventory.

Ported from skyrim-ai-assistant-toolkit (c) 2026 WingedGuardian, MIT License.
READ-ONLY: never writes a co-save. This is a survey of the chunk STRUCTURE - magic, versions and the
{opcode, version, length} walk - not a decoder of each chunk's payload (those are per-plugin and several
are undocumented). The walk resyncs when it desyncs (it scans forward to the next plausible opcode) and
reports how much of the file it covered, so a partial view is never passed off as a complete one.

python cosave_info.py COSAVE.skse              header fields + inventory (count and bytes per opcode)
python cosave_info.py COSAVE.skse --chunks     also list every chunk, in file order
python cosave_info.py COSAVE.skse --top 5      inventory: only the five largest opcodes

The inventory says WHICH mods stashed co-save data and HOW MUCH: REGS/PLGN/REGE are SKSE's own
registrations, JSTR is JContainers, STRV/STFV/STRL are PapyrusUtil StorageUtil, P3PE is po3's extender;
any other opcode is mod-specific and is reported raw, by size, for the load order's owner to identify.

Exit: 0 parsed, coverage high enough to trust - 1 parsed, but coverage under 90% or no chunk found, so
the totals are indicative only - 2 not a co-save, or usage.
"""
import json
import struct
import sys

LEGEND = {
    "PLGN": "plugin list (load order at save time)",
    "MODS": "full mod list (likely)",
    "LMOD": "light plugin (ESL) list",
    "REGS": "SKSE script event registration",
    "REGE": "registration list end",
    "MENR": "menu-open event registrations",
    "KEYR": "key event registrations",
    "CTLR": "control event registrations",
    "JSTR": "JContainers serialized state (likely)",
    "STRV": "PapyrusUtil StorageUtil string vars (likely)",
    "STFV": "PapyrusUtil StorageUtil form vars (likely)",
    "STRL": "PapyrusUtil StorageUtil data (likely)",
    "P3PE": "PO3 Papyrus Extender state (likely)",
}
HEADER_SIZE = 32               # "SKSE", seven uint32 fields, then the chunks
MAX_CHUNKS = 100000            # a crafted file must not turn the walk into an endless list


class CosaveError(ValueError):
    """The input is not a co-save this tool can walk; the message says what it found instead."""


def survey(path, with_chunks=False, top=0):
    """Read the co-save and return the report as a dict; raises CosaveError on anything unusable."""
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        raise CosaveError("cannot read %s: %s" % (path, exc))
    size = len(data)
    if size < HEADER_SIZE:
        raise CosaveError("%s is %d byte(s), too short for a co-save header" % (path, size))
    if data[:4] != b"SKSE":
        raise CosaveError("not an SKSE co-save: magic is %r, not b'SKSE'" % (data[:4],))
    u32 = lambda o: struct.unpack_from("<I", data, o)[0]

    def opcode(offset):
        """Stored little-endian, so the human form is the byte order reversed."""
        return data[offset:offset + 4][::-1].decode("latin-1")

    def printable(offset):
        return offset + 4 <= size and all(0x20 <= c <= 0x7E for c in data[offset:offset + 4])

    report = {"ok": True, "op": "cosave-info", "path": path, "size": size, "magic": "SKSE",
              "formatVersion": u32(4), "skseVersion": "0x%08x" % u32(8),
              "runtimeVersion": "0x%08x" % u32(12),
              "headerFields": [u32(16), u32(20), u32(24), u32(28)]}
    off, chunks, resyncs = HEADER_SIZE, [], 0
    while off + 12 <= size:
        if not printable(off) or off + 12 + u32(off + 8) > size:
            # Desync: scan forward for the next plausible opcode, and say that it happened.
            nxt, found = off + 1, False
            while nxt + 12 <= size:
                if printable(nxt) and nxt + 12 + u32(nxt + 8) <= size and u32(nxt + 8) < size:
                    off, found = nxt, True
                    resyncs += 1
                    break
                nxt += 1
            if not found:
                break
        chunks.append((opcode(off), u32(off + 4), u32(off + 8), off))
        if len(chunks) > MAX_CHUNKS:
            raise CosaveError("%s: more than %d chunks, so this is not the flat chunk layout" % (path, MAX_CHUNKS))
        off += 12 + chunks[-1][2]

    totals = {}
    for op, _version, length, _offset in chunks:
        entry = totals.setdefault(op, {"count": 0, "bytes": 0})
        entry["count"] += 1
        entry["bytes"] += length
    inventory = [{"opcode": op, "count": value["count"], "bytes": value["bytes"],
                  "meaning": LEGEND.get(op, "")}
                 for op, value in sorted(totals.items(), key=lambda kv: -kv[1]["bytes"])]
    if top > 0:
        inventory = inventory[:top]
    covered = sum(12 + chunk[2] for chunk in chunks)
    report.update({
        "chunkCount": len(chunks),
        "distinctOpcodes": len(totals),
        "resyncs": resyncs,
        "walkEnd": off,
        "bytesCovered": covered + HEADER_SIZE,
        "coveragePct": round(min(100.0, 100.0 * (covered + HEADER_SIZE) / size), 1),
        "inventory": inventory,
        "note": "structural survey; decoding a chunk's payload (StorageUtil/JContainers values, the PLGN "
                "mod list) is a separate job. resyncs>0 means a nested boundary the flat walk skipped, so "
                "the opcode and size totals stay indicative.",
    })
    if with_chunks:
        report["chunks"] = [{"opcode": op, "version": version, "length": length, "offset": offset}
                            for op, version, length, offset in chunks]
    return report


def usage_error(message):
    print("cosave_info: %s" % message, file=sys.stderr)
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
    path, with_chunks, top = None, False, 0
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--chunks":
            with_chunks = True
            i += 1
            continue
        if arg == "--top":
            if i + 1 >= len(argv):
                return usage_error("--top needs a number")
            try:
                top = int(argv[i + 1])
            except ValueError:
                return usage_error("--top needs a number, not %r" % argv[i + 1])
            if top < 0:
                return usage_error("--top cannot be negative")
            i += 2
            continue
        if arg.startswith("-"):
            return usage_error("unknown flag %r" % arg)
        if path is not None:
            return usage_error("takes one co-save; %r is extra" % arg)
        path = arg
        i += 1
    if path is None:
        return usage_error("name one co-save file")
    try:
        report = survey(path, with_chunks, top)
    except (CosaveError, struct.error) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(report, indent=2, ensure_ascii=False))
    # Three outcomes, not two: a caller that gates on the exit code alone must not read a file the walk
    # could not follow as a clean survey. 1 means "parsed, but the totals are not a complete picture".
    if report["coveragePct"] < 90 or report["chunkCount"] == 0:
        print(json.dumps({"warning": "low coverage or no chunk parsed: the inventory above is a partial "
                                     "view, not a complete one"}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
