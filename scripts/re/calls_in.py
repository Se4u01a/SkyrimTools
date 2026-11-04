"""List the calls a range of SkyrimSE.exe makes, each target named by Address Library ID (and name when known).

python calls_in.py <startRVA> <endRVA> [--exe path]     e.g. calls_in.py 5B2FA0 5B3620
Direct calls show their target; indirect ones (vtable / import) show the operand.
"""
import bisect
import os
import sys

import capstone
import pefile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addrlib  # noqa: E402

import skyrim_paths  # noqa: E402
EXE = skyrim_paths.SKYRIM_EXE


def main():
    args = sys.argv[1:]
    exe = EXE
    if "--exe" in args:
        k = args.index("--exe")
        exe = args[k + 1]
        del args[k:k + 2]
    start, end = int(args[0], 16), int(args[1], 16)
    _, pairs = addrlib.load(addrlib.DEFAULT_BIN)
    known = addrlib.names()
    by_off = sorted((o, i) for i, o in pairs)
    offs = [o for o, _ in by_off]

    def name(rva):
        k = bisect.bisect_right(offs, rva) - 1
        if k < 0:
            return "?"
        base, i = by_off[k]
        n = known.get(i, "").split("  [")[0]
        return "ID %d%s%s" % (i, "+%X" % (rva - base) if rva != base else "", " " + n if n else "")

    pe = pefile.PE(exe, fast_load=True)
    ib = pe.OPTIONAL_HEADER.ImageBase
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    code = pe.get_data(start, end - start)
    prev = []
    for ins in md.disasm(code, ib + start):
        rva = ins.address - ib
        if ins.mnemonic == "call":
            op = ins.op_str
            tgt = ""
            if op.startswith("0x"):
                tgt = name(int(op, 16) - ib)
            ctx = "; ".join("%s %s" % (p.mnemonic, p.op_str) for p in prev[-2:])
            print("+%X  call %-28s %s    [%s]" % (rva, op, tgt, ctx))
        prev.append(ins)


if __name__ == "__main__":
    main()
