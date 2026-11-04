"""Skim the ActionScript 2 of a .swf (Scaleform / Skyrim UI): per action block, its constant pool and loop markers.

python swf_as2.py file.swf [--names]     blocks with backward jumps (loops), timers, onEnterFrame, getTimer
--names also prints every constant pool. FWS / CWS (zlib) only; ZWS (lzma) is reported and skipped.

A backward ActionJump / ActionIf is a loop. Not a decompiler: use JPEXS FFDec for the full source.
"""
import struct
import sys
import zlib

TAG_NAMES = {12: "DoAction", 59: "DoInitAction", 39: "DefineSprite", 26: "PlaceObject2", 70: "PlaceObject3"}
WATCH = ("setInterval", "clearInterval", "setTimeout", "onEnterFrame", "getTimer", "CurrentTime", "gotoAndPlay",
         "onLoad", "Update", "while", "for")


def rect_bits(data, p):
    nbits = data[p] >> 3
    total = 5 + nbits * 4
    return p + (total + 7) // 8


def tags(data, p, end):
    while p < end:
        code_len = struct.unpack_from("<H", data, p)[0]
        p += 2
        code, length = code_len >> 6, code_len & 0x3F
        if length == 0x3F:
            length = struct.unpack_from("<I", data, p)[0]
            p += 4
        yield code, p, length
        p += length
        if code == 0:
            break


def actions(data, p, end):
    """(offset, code, payload) of each action of a block."""
    while p < end:
        code = data[p]
        if code == 0:
            yield p, 0, b""
            return
        if code >= 0x80:
            n = struct.unpack_from("<H", data, p + 1)[0]
            yield p, code, data[p + 3:p + 3 + n]
            p += 3 + n
        else:
            yield p, code, b""
            p += 1


def scan_block(data, p, end, where, show_names, out):
    pool = []
    loops = 0
    for off, code, payload in actions(data, p, end):
        if code == 0x88:  # ActionConstantPool
            count = struct.unpack_from("<H", payload, 0)[0]
            q = 2
            pool = []
            for _ in range(count):
                z = payload.index(b"\0", q)
                pool.append(payload[q:z].decode("latin1"))
                q = z + 1
        elif code in (0x99, 0x9D):  # ActionJump / ActionIf
            rel = struct.unpack_from("<h", payload, 0)[0]
            if rel < 0:
                loops += 1
    hits = [w for w in WATCH if any(w.lower() == s.lower() or (len(w) > 5 and w.lower() in s.lower()) for s in pool)]
    if loops or hits or show_names:
        out.append("%s: %d backward jump(s)%s" % (where, loops, ("; " + ", ".join(hits)) if hits else ""))
        if show_names:
            out.append("    pool: " + ", ".join(pool))


def walk(data, p, end, where, show_names, out, depth=0):
    for code, q, length in tags(data, p, end):
        if code in (12, 59):
            body = q + (2 if code == 59 else 0)
            scan_block(data, body, q + length, "%s %s@%X" % (where, TAG_NAMES[code], q), show_names, out)
        elif code == 39:
            sprite_id = struct.unpack_from("<H", data, q)[0]
            walk(data, q + 4, q + length, "%s sprite%d" % (where, sprite_id), show_names, out, depth + 1)
        elif code in (26, 70):
            # clip actions (onClipEvent) live at the end of PlaceObject2/3; flag bit 7
            flags = data[q]
            if flags & 0x80:
                out.append("%s PlaceObject@%X has clip actions (onClipEvent / onEnterFrame-style)" % (where, q))


def main():
    path = sys.argv[1]
    show_names = "--names" in sys.argv
    raw = open(path, "rb").read()
    sig, version, size = raw[:3], raw[3], struct.unpack_from("<I", raw, 4)[0]
    if sig == b"CWS":
        data = raw[:8] + zlib.decompress(raw[8:])
    elif sig == b"FWS":
        data = raw
    else:
        print("%s: %s (lzma) not handled" % (path, sig))
        return
    p = rect_bits(data, 8) + 4  # frame rate + frame count
    out = []
    walk(data, p, len(data), "root", show_names, out)
    print("== %s (SWF %d, %d bytes)" % (path, version, len(data)))
    for line in out:
        print("  " + line)


if __name__ == "__main__":
    main()
