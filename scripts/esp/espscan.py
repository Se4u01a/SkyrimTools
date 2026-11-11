"""Scan a Skyrim SE plugin for records whose data contains a byte pattern / reference a FormID.

python espscan.py plugin.esp text <substring>     records containing the ASCII/cp1251 string
python espscan.py plugin.esp ref <hexformid>      records containing the 4-byte formid
python espscan.py plugin.esp dump <hexformid>     subrecords of one record
"""
import struct
import sys
import zlib


def records(buf):
    p = 0
    stack = [len(buf)]
    while p < len(buf):
        typ = buf[p:p + 4]
        size = struct.unpack_from("<I", buf, p + 4)[0]
        if typ == b"GRUP":
            p += 24
            continue
        flags, fid = struct.unpack_from("<II", buf, p + 8)
        data = buf[p + 24:p + 24 + size]
        if flags & 0x40000:
            data = zlib.decompress(data[4:])
        yield typ.decode(), fid, data
        p += 24 + size


def subrecords(data):
    p, big = 0, None
    while p < len(data):
        t = data[p:p + 4].decode("latin1")
        n = struct.unpack_from("<H", data, p + 4)[0]
        if t == "XXXX":
            big = struct.unpack_from("<I", data, p + 6)[0]
            p += 10
            continue
        if big is not None:
            n, big = big, None
        yield t, data[p + 6:p + 6 + n]
        p += 6 + n


def edid(data):
    for t, d in subrecords(data):
        if t == "EDID":
            return d.rstrip(b"\0").decode("cp1251", "replace")
    return ""


def main():
    help_flag = "-h" in sys.argv[1:] or "--help" in sys.argv[1:]
    if help_flag or len(sys.argv) < 4:
        print(__doc__.strip())
        sys.exit(0 if help_flag else 2)
    path, mode, arg = sys.argv[1:4]
    buf = open(path, "rb").read()
    if mode == "text":
        pat = arg.encode("cp1251")
        for typ, fid, data in records(buf):
            if pat.lower() in data.lower():
                print("%s %08X %s" % (typ, fid, edid(data)))
    elif mode == "ref":
        pat = struct.pack("<I", int(arg, 16))
        for typ, fid, data in records(buf):
            if pat in data and fid != int(arg, 16):
                print("%s %08X %s" % (typ, fid, edid(data)))
    elif mode == "dump":
        want = int(arg, 16)
        for typ, fid, data in records(buf):
            if fid == want:
                print("%s %08X" % (typ, fid))
                for t, d in subrecords(data):
                    txt = d.rstrip(b"\0")
                    s = txt.decode("cp1251", "replace") if txt and all(32 <= c < 256 for c in txt) else d.hex(" ")
                    print("  %s [%d] %s" % (t, len(d), s[:400]))


if __name__ == "__main__":
    main()
