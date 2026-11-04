"""Breadth-first over direct calls from SkyrimSE.exe functions: where does a virtual call with this vtable offset happen?

python find_vcall.py <vtable byte offset, e.g. 0x568> <depth> <RVA or ID:n>...
Prints each function (by Address Library ID) that makes `call [reg + offset]`, with the call path from a root.
A function ends at the next Address Library ID (an approximation: IDs mark function starts).
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
    voff = int(sys.argv[1], 0)
    depth = int(sys.argv[2])
    _, pairs = addrlib.load(addrlib.DEFAULT_BIN)
    by_id = dict(pairs)
    starts = sorted(set(o for _, o in pairs))
    id_of = {o: i for i, o in pairs}
    roots = []
    for a in sys.argv[3:]:
        roots.append(by_id[int(a[3:])] if a.lower().startswith("id:") else int(a, 16))
    pe = pefile.PE(EXE, fast_load=True)
    ib = pe.OPTIONAL_HEADER.ImageBase
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    needle = "+ 0x%x]" % voff

    def body(rva):
        k = bisect.bisect_right(starts, rva)
        end = starts[k] if k < len(starts) else rva + 0x400
        end = min(end, rva + 0x4000)
        return md.disasm(pe.get_data(rva, end - rva), ib + rva)

    seen = set()
    frontier = [(r, [r]) for r in roots]
    for level in range(depth + 1):
        nxt = []
        for rva, path in frontier:
            if rva in seen:
                continue
            seen.add(rva)
            for ins in body(rva):
                if ins.mnemonic != "call":
                    continue
                if needle in ins.op_str and "rip" not in ins.op_str:
                    print("vcall %s at +%X in %s  path: %s" % (ins.op_str, ins.address - ib, "ID %s" % id_of.get(rva, "?"),
                                                            " -> ".join("ID %s" % id_of.get(p, "+%X" % p) for p in path)))
                elif ins.op_str.startswith("0x"):
                    t = int(ins.op_str, 16) - ib
                    if t in id_of and t not in seen:
                        nxt.append((t, path + [t]))
        frontier = nxt


if __name__ == "__main__":
    main()
