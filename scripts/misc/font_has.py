"""Does a TTF/OTF font map the given code points? Minimal cmap reader (formats 4 and 12).

python font_has.py <font> [hex codepoints...]   (default: Cyrillic U+0410, U+044F, U+0401)
"""
import struct
import sys


def codepoints(path):
    data = open(path, "rb").read()
    num_tables = struct.unpack(">H", data[4:6])[0]
    cmap = None
    for i in range(num_tables):
        tag, _, offset, _ = struct.unpack(">4sIII", data[12 + 16 * i:28 + 16 * i])
        if tag == b"cmap":
            cmap = offset
    if cmap is None:
        return set()
    out = set()
    n = struct.unpack(">H", data[cmap + 2:cmap + 4])[0]
    for i in range(n):
        _, _, sub = struct.unpack(">HHI", data[cmap + 4 + 8 * i:cmap + 12 + 8 * i])
        t = cmap + sub
        fmt = struct.unpack(">H", data[t:t + 2])[0]
        if fmt == 4:
            segx2 = struct.unpack(">H", data[t + 6:t + 8])[0]
            ends = struct.unpack(f">{segx2 // 2}H", data[t + 14:t + 14 + segx2])
            starts = struct.unpack(f">{segx2 // 2}H", data[t + 16 + segx2:t + 16 + 2 * segx2])
            for s, e in zip(starts, ends):
                if s != 0xFFFF:
                    out.update(range(s, e + 1))
        elif fmt == 12:
            groups = struct.unpack(">I", data[t + 12:t + 16])[0]
            for g in range(groups):
                s, e, _ = struct.unpack(">III", data[t + 16 + 12 * g:t + 28 + 12 * g])
                out.update(range(s, e + 1))
    return out


help_flag = "-h" in sys.argv[1:] or "--help" in sys.argv[1:]
if help_flag or len(sys.argv) < 2:
    print(__doc__.strip())
    sys.exit(0 if help_flag else 2)

if __name__ == "__main__":
    cps = codepoints(sys.argv[1])
    want = [int(x, 16) for x in sys.argv[2:]] or [0x410, 0x44F, 0x401]
    print(sys.argv[1], {hex(c): c in cps for c in want})
