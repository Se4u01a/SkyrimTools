"""Name the functions at RVAs of a DLL from its .pdb (dbghelp). python pdbsym.py <dll> <rva hex>..."""
import ctypes
import ctypes.wintypes as wt
import os
import sys

dbg = ctypes.WinDLL("dbghelp")


class SYMBOL_INFOW(ctypes.Structure):
    _fields_ = [("SizeOfStruct", wt.ULONG), ("TypeIndex", wt.ULONG), ("Reserved", ctypes.c_ulonglong * 2), ("Index", wt.ULONG),
                ("Size", wt.ULONG), ("ModBase", ctypes.c_ulonglong), ("Flags", wt.ULONG), ("Value", ctypes.c_ulonglong),
                ("Address", ctypes.c_ulonglong), ("Register", wt.ULONG), ("Scope", wt.ULONG), ("Tag", wt.ULONG),
                ("NameLen", wt.ULONG), ("MaxNameLen", wt.ULONG), ("Name", wt.WCHAR * 1024)]


class IMAGEHLP_LINEW64(ctypes.Structure):
    _fields_ = [("SizeOfStruct", wt.DWORD), ("Key", ctypes.c_void_p), ("LineNumber", wt.DWORD), ("FileName", wt.LPWSTR),
                ("Address", ctypes.c_ulonglong)]


# dbghelp checks SizeOfStruct against sizeof(SYMBOL_INFOW) with a one-char Name, padded to 8 (= 88 on x64); any other
# value fails with ERROR_INVALID_PARAMETER and every lookup prints "?".
SYMBOL_INFOW_SIZE = (SYMBOL_INFOW.Name.offset + ctypes.sizeof(wt.WCHAR) + 7) & ~7

if len(sys.argv) < 3 or sys.argv[1] in ("-h", "--help"):
    print(__doc__.strip())
    sys.exit(0 if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help") else 2)
dll = os.path.abspath(sys.argv[1])
h = wt.HANDLE(0x1234)
dbg.SymSetOptions(0x2 | 0x10)  # undname, load lines; no SYMOPT_DEFERRED_LOADS: deferred, the .pdb is never loaded here
dbg.SymInitializeW(h, ctypes.c_wchar_p(os.path.dirname(dll)), False)
base = 0x10000000
dbg.SymLoadModuleExW.restype = ctypes.c_ulonglong
got = dbg.SymLoadModuleExW(h, None, ctypes.c_wchar_p(dll), None, ctypes.c_ulonglong(base), 0, None, 0)
print("loaded at", hex(got))
for a in sys.argv[2:]:
    addr = base + int(a, 16)
    s = SYMBOL_INFOW()
    s.SizeOfStruct = SYMBOL_INFOW_SIZE
    s.MaxNameLen = 1024
    disp = ctypes.c_ulonglong()
    if dbg.SymFromAddrW(h, ctypes.c_ulonglong(addr), ctypes.byref(disp), ctypes.byref(s)):
        line = IMAGEHLP_LINEW64()
        line.SizeOfStruct = ctypes.sizeof(line)
        d2 = wt.DWORD()
        where = ""
        if dbg.SymGetLineFromAddrW64(h, ctypes.c_ulonglong(addr), ctypes.byref(d2), ctypes.byref(line)):
            where = " %s:%d" % (line.FileName, line.LineNumber)
        print("+%s  %s+0x%X%s" % (a, s.Name, disp.value, where))
    else:
        print("+%s  ?" % a)
