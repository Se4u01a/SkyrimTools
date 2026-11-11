"""Show the call before each return address (RVA offsets) in an exe, and the function start guess.

python disasm_at.py <SkyrimSE.exe> <rva>...     e.g. disasm_at.py SkyrimSE.exe 5B2FA0
"""
import sys
import pefile
import capstone

help_flag = "-h" in sys.argv[1:] or "--help" in sys.argv[1:]
if help_flag or len(sys.argv) < 3:
    print(__doc__.strip())
    sys.exit(0 if help_flag else 2)

exe = sys.argv[1]
pe = pefile.PE(exe, fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

for arg in sys.argv[2:]:
    rva = int(arg, 16)
    data = pe.get_data(rva - 0x40, 0x50)
    print("==== +%X" % rva)
    # try decode starting at several offsets to land exactly on rva
    for start in range(0, 0x40):
        ins = list(md.disasm(data[start:], base + rva - 0x40 + start))
        addrs = [i.address for i in ins]
        if base + rva in addrs:
            idx = addrs.index(base + rva)
            for i in ins[max(0, idx - 8):idx + 3]:
                mark = ">>" if i.address == base + rva else "  "
                print(" %s +%X  %s %s" % (mark, i.address - base, i.mnemonic, i.op_str))
            break
