"""Read a vtable slot of SkyrimSE.exe (on disk) and disassemble the function it points to.

python vtable_slot.py <vtable REL::ID (SE)> <slot index> [instructions=40] [--exe path]
"""
import os
import struct
import sys

import capstone
import pefile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addrlib  # noqa: E402

import skyrim_paths  # noqa: E402
EXE = skyrim_paths.SKYRIM_EXE


def main():
    args = sys.argv[1:]
    if "-h" in args or "--help" in args or len(args) < 2:
        print(__doc__.strip())
        sys.exit(0 if ("-h" in args or "--help" in args) else 2)
    exe = EXE
    if "--exe" in args:
        k = args.index("--exe")
        exe = args[k + 1]
        del args[k:k + 2]
    vid, slot = int(args[0], 0), int(args[1], 0)
    count = int(args[2]) if len(args) > 2 else 40
    _, pairs = addrlib.load(addrlib.default_bin())
    vt = dict(pairs).get(vid)
    if vt is None:
        sys.exit("REL::ID %d is not in the Address Library (an SE vtable ID is expected)" % vid)
    pe = pefile.PE(exe, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    target = struct.unpack("<Q", pe.get_data(vt + slot * 8, 8))[0] - base
    by_off = {o: i for i, o in pairs}
    print("vtable ID %d at +%X, slot %d -> +%X (0x%X)%s" % (vid, vt, slot, target, target + base,
                                                       ", ID %d" % by_off[target] if target in by_off else ""))
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    for n, ins in enumerate(md.disasm(pe.get_data(target, count * 15), base + target)):
        if n >= count:
            break
        print("  +%X  %s %s" % (ins.address - base, ins.mnemonic, ins.op_str))
        if ins.mnemonic in ("ret", "int3") and n > 3:
            break


if __name__ == "__main__":
    main()
