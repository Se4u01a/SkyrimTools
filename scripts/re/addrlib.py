r"""Address Library for SKSE (SE format 1 / old AE format 2 .bin): REL::ID <-> offset of SkyrimSE.exe.

python addrlib.py id 37996 36698            offsets of these IDs
python addrlib.py off 6D4B6F 0x37B26A       the ID whose function holds each offset (nearest ID at or below it)
python addrlib.py dump out.csv              every id,offset as CSV (sorted by offset)
Names come from SkyrimTools\data\se_id_names.tsv (build_id_names.py), where a source we have uses the ID.
Options: --bin <path>  (default: the 1.5.97 bin found by skyrim_paths: SKYRIM_ADDRLIB_BIN, the MO2 mods, the game Data)

The format follows CommonLibSSE-NG src/REL/IDDB.cpp (unpack_file). An offset is an RVA: the address minus the image
base 0x140000000, the same as "SkyrimSE.exe+XXXX" in logs and crash logs.
"""
import bisect
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skyrim_paths  # noqa: E402


def default_bin():
    return skyrim_paths.address_library_bin()


def load(path):
    data = open(path, "rb").read()
    p = 0

    def rd(fmt):
        nonlocal p
        v = struct.unpack_from(fmt, data, p)
        p += struct.calcsize(fmt)
        return v[0] if len(v) == 1 else v

    fmt = rd("<i")
    if fmt not in (1, 2):
        raise SystemExit("format %d is not handled (5 = 1.7.99+ AE dense array)" % fmt)
    version = rd("<4i")
    name_len = rd("<i")
    p += name_len
    ptr_size = rd("<i")
    count = rd("<i")
    out = []
    prev_id = prev_off = 0
    for _ in range(count):
        t = data[p]
        p += 1
        lo, hi = t & 0xF, t >> 4
        if lo == 0: i = rd("<Q")
        elif lo == 1: i = prev_id + 1
        elif lo == 2: i = prev_id + rd("<B")
        elif lo == 3: i = prev_id - rd("<B")
        elif lo == 4: i = prev_id + rd("<H")
        elif lo == 5: i = prev_id - rd("<H")
        elif lo == 6: i = rd("<H")
        elif lo == 7: i = rd("<I")
        else: raise SystemExit("bad id type %d" % lo)
        tmp = prev_off // ptr_size if hi & 8 else prev_off
        h = hi & 7
        if h == 0: o = rd("<Q")
        elif h == 1: o = tmp + 1
        elif h == 2: o = tmp + rd("<B")
        elif h == 3: o = tmp - rd("<B")
        elif h == 4: o = tmp + rd("<H")
        elif h == 5: o = tmp - rd("<H")
        elif h == 6: o = rd("<H")
        elif h == 7: o = rd("<I")
        if hi & 8:
            o *= ptr_size
        out.append((i, o))
        prev_id, prev_off = i, o
    return version, out


NAMES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "se_id_names.tsv")


def names():
    out = {}
    if os.path.exists(NAMES):
        for line in open(NAMES, encoding="utf-8").read().splitlines()[1:]:
            parts = line.split("\t")
            if len(parts) >= 3:
                out[int(parts[0])] = "%s  [%s]" % (parts[1], parts[2])
    return out


def parse_num(s):
    s = s.strip().lower().replace("skyrimse.exe+", "")
    return int(s, 16) if s.startswith("0x") or any(c in "abcdef" for c in s) else int(s, 16)


def main():
    args = sys.argv[1:]
    path = None
    if "--bin" in args:
        k = args.index("--bin")
        path = args[k + 1]
        del args[k:k + 2]
    if not args:
        print(__doc__)
        return
    version, pairs = load(path or default_bin())
    known = names()
    mode, rest = args[0], args[1:]
    if mode == "id":
        by_id = dict(pairs)
        for a in rest:
            i = int(a, 0)
            o = by_id.get(i)
            print("ID %d -> %s  %s" % (i, "SkyrimSE.exe+%X (0x%X)" % (o, o + 0x140000000) if o is not None else "not in the library", known.get(i, "")))
    elif mode == "off":
        by_off = sorted((o, i) for i, o in pairs)
        offs = [o for o, _ in by_off]
        for a in rest:
            o = parse_num(a)
            k = bisect.bisect_right(offs, o) - 1
            if k < 0:
                print("+%X: below every ID" % o)
                continue
            base, i = by_off[k]
            nxt = by_off[k + 1][0] if k + 1 < len(by_off) else None
            print("+%X = ID %d +0x%X (ID at +%X%s)  %s" % (o, i, o - base, base, ", next ID at +%X" % nxt if nxt else "", known.get(i, "")))
    elif mode == "dump":
        with open(rest[0], "w") as f:
            f.write("id,offset\n")
            for i, o in sorted(pairs, key=lambda x: x[1]):
                f.write("%d,%X\n" % (i, o))
        print("%d entries, game %s" % (len(pairs), ".".join(map(str, version))))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
