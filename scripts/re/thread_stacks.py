"""Snapshot every thread of a running process: start address, RIP, and the return-address candidates on its stack.

python thread_stacks.py [pid | SkyrimSE.exe] [--max N] [--busy] [--ids]
  default process: SkyrimSE.exe
  --max N   return addresses per thread (default 24)
  --busy    only threads not waiting in the kernel (RIP outside ntdll / win32u): a loop or a spin shows here
  --ids     name SkyrimSE.exe frames by Address Library ID (and the function, when a source we have names it)
Each thread is suspended only while its context and stack are read. Read-only otherwise. Take two or three
snapshots: a frame that stays put across them is where the thread is stuck.

The return addresses are candidates (values on the stack that follow a call), not an unwound stack: stale ones
from earlier calls show too. The innermost few and those repeated across snapshots are the ones to trust.
"""
import ctypes
import ctypes.wintypes as wt
import os
import sys

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)
ntdll = ctypes.WinDLL("ntdll")

TH32CS_SNAPTHREAD = 0x4
PROCESS_ALL = 0x0410 | 0x0010  # query info + vm read
THREAD_ALL = 0x0002 | 0x0008 | 0x0010 | 0x0040  # suspend/resume, get context, query info


class THREADENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ThreadID", wt.DWORD), ("th32OwnerProcessID", wt.DWORD),
                ("tpBasePri", wt.LONG), ("tpDeltaPri", wt.LONG), ("dwFlags", wt.DWORD)]


class M128A(ctypes.Structure):
    _fields_ = [("Low", ctypes.c_ulonglong), ("High", ctypes.c_longlong)]


class CONTEXT(ctypes.Structure):
    _pack_ = 16
    _fields_ = [("P1Home", ctypes.c_ulonglong), ("P2Home", ctypes.c_ulonglong), ("P3Home", ctypes.c_ulonglong),
                ("P4Home", ctypes.c_ulonglong), ("P5Home", ctypes.c_ulonglong), ("P6Home", ctypes.c_ulonglong),
                ("ContextFlags", wt.DWORD), ("MxCsr", wt.DWORD),
                ("SegCs", wt.WORD), ("SegDs", wt.WORD), ("SegEs", wt.WORD), ("SegFs", wt.WORD), ("SegGs", wt.WORD), ("SegSs", wt.WORD),
                ("EFlags", wt.DWORD),
                ("Dr0", ctypes.c_ulonglong), ("Dr1", ctypes.c_ulonglong), ("Dr2", ctypes.c_ulonglong), ("Dr3", ctypes.c_ulonglong),
                ("Dr6", ctypes.c_ulonglong), ("Dr7", ctypes.c_ulonglong),
                ("Rax", ctypes.c_ulonglong), ("Rcx", ctypes.c_ulonglong), ("Rdx", ctypes.c_ulonglong), ("Rbx", ctypes.c_ulonglong),
                ("Rsp", ctypes.c_ulonglong), ("Rbp", ctypes.c_ulonglong), ("Rsi", ctypes.c_ulonglong), ("Rdi", ctypes.c_ulonglong),
                ("R8", ctypes.c_ulonglong), ("R9", ctypes.c_ulonglong), ("R10", ctypes.c_ulonglong), ("R11", ctypes.c_ulonglong),
                ("R12", ctypes.c_ulonglong), ("R13", ctypes.c_ulonglong), ("R14", ctypes.c_ulonglong), ("R15", ctypes.c_ulonglong),
                ("Rip", ctypes.c_ulonglong),
                ("FltSave", ctypes.c_byte * 512),
                ("VectorRegister", M128A * 26), ("VectorControl", ctypes.c_ulonglong),
                ("DebugControl", ctypes.c_ulonglong), ("LastBranchToRip", ctypes.c_ulonglong), ("LastBranchFromRip", ctypes.c_ulonglong),
                ("LastExceptionToRip", ctypes.c_ulonglong), ("LastExceptionFromRip", ctypes.c_ulonglong)]


class MODULEINFO(ctypes.Structure):
    _fields_ = [("lpBaseOfDll", ctypes.c_void_p), ("SizeOfImage", wt.DWORD), ("EntryPoint", ctypes.c_void_p)]


def modules(hproc):
    arr = (ctypes.c_void_p * 2048)()
    needed = wt.DWORD()
    psapi.EnumProcessModulesEx(hproc, arr, ctypes.sizeof(arr), ctypes.byref(needed), 3)
    out = []
    for i in range(needed.value // ctypes.sizeof(ctypes.c_void_p)):
        h = arr[i]
        name = ctypes.create_unicode_buffer(260)
        psapi.GetModuleBaseNameW(hproc, ctypes.c_void_p(h), name, 260)
        mi = MODULEINFO()
        psapi.GetModuleInformation(hproc, ctypes.c_void_p(h), ctypes.byref(mi), ctypes.sizeof(mi))
        out.append((mi.lpBaseOfDll, mi.lpBaseOfDll + mi.SizeOfImage, name.value))
    out.sort()
    return out


def where(mods, a):
    for b, e, n in mods:
        if b <= a < e:
            return "%s+%X" % (n, a - b)
    return None


def read(hproc, addr, size):
    buf = ctypes.create_string_buffer(size)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(hproc, ctypes.c_void_p(addr), buf, size, ctypes.byref(got)):
        # shrink until readable (stack top)
        while size > 0x1000 and not got.value:
            size //= 2
            if k32.ReadProcessMemory(hproc, ctypes.c_void_p(addr), buf, size, ctypes.byref(got)):
                break
    return buf.raw[:got.value]


def is_after_call(hproc, mods, a):
    # a call precedes the return address: E8 rel32 (5 bytes) or FF /2 (2..7 bytes)
    code = read(hproc, a - 7, 7)
    if len(code) < 7:
        return False
    if code[2] == 0xE8:
        return True
    for n in (2, 3, 6, 7):
        if code[7 - n] == 0xFF and ((code[7 - n + 1] >> 3) & 7) == 2:
            return True
    return False


def find_pid(name):
    import subprocess
    out = subprocess.run(["tasklist", "/FO", "CSV", "/NH", "/FI", "IMAGENAME eq " + name], capture_output=True, text=True, encoding="oem", errors="replace").stdout or ""
    for line in out.splitlines():  # tasklist prints in the OEM codepage (cp866 on Russian Windows), not UTF-8
        parts = [x.strip('"') for x in line.split('","')]
        if len(parts) > 1 and parts[0].lower() == name.lower():
            return int(parts[1])
    return None


def main():
    args = sys.argv[1:]
    if "-h" in args or "--help" in args:
        print(__doc__.strip())
        return
    limit = 24
    if "--max" in args:
        k = args.index("--max")
        limit = int(args[k + 1])
        del args[k:k + 2]
    busy_only = "--busy" in args
    with_ids = "--ids" in args
    args = [a for a in args if a not in ("--busy", "--ids")]
    target = args[0] if args else "SkyrimSE.exe"
    pid = int(target) if target.isdigit() else find_pid(target)
    if not pid:
        print("no process", target, "(is the game running?)", file=sys.stderr)
        sys.exit(1)
    namer = None
    if with_ids:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import addrlib
        import bisect
        _, pairs = addrlib.load(addrlib.default_bin())
        known = addrlib.names()
        by_off = sorted((o, i) for i, o in pairs)
        offs = [o for o, _ in by_off]

        def namer(w):
            if not w.lower().startswith("skyrimse.exe+"):
                return w
            o = int(w.split("+")[1], 16)
            k = bisect.bisect_right(offs, o) - 1
            if k < 0:
                return w
            base, i = by_off[k]
            name = known.get(i, "").split("  [")[0]
            return "%s(ID %d+%X%s)" % (w, i, o - base, " " + name if name else "")
    k32.OpenProcess.restype = wt.HANDLE
    k32.OpenThread.restype = wt.HANDLE
    hproc = k32.OpenProcess(PROCESS_ALL, False, pid)
    if not hproc:
        print("OpenProcess failed", ctypes.get_last_error())
        return
    mods = modules(hproc)
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
    te = THREADENTRY32()
    te.dwSize = ctypes.sizeof(te)
    tids = []
    ok = k32.Thread32First(snap, ctypes.byref(te))
    while ok:
        if te.th32OwnerProcessID == pid:
            tids.append(te.th32ThreadID)
        ok = k32.Thread32Next(snap, ctypes.byref(te))
    k32.CloseHandle(snap)
    print("pid %d: %d threads, %d modules" % (pid, len(tids), len(mods)))
    for tid in tids:
        ht = k32.OpenThread(THREAD_ALL, False, tid)
        if not ht:
            print("thread %d: open failed" % tid)
            continue
        start = ctypes.c_void_p()
        ntdll.NtQueryInformationThread(wt.HANDLE(ht), 9, ctypes.byref(start), ctypes.sizeof(start), None)
        ctx = CONTEXT()
        ctx.ContextFlags = 0x100003  # CONTEXT_AMD64 | CONTROL | INTEGER
        k32.SuspendThread(wt.HANDLE(ht))
        try:
            if not k32.GetThreadContext(wt.HANDLE(ht), ctypes.byref(ctx)):
                print("thread %d: no context" % tid)
                continue
            stack = read(hproc, ctx.Rsp, 0x10000)
        finally:
            k32.ResumeThread(wt.HANDLE(ht))
            k32.CloseHandle(wt.HANDLE(ht))
        rets = []
        for off in range(0, len(stack) - 7, 8):
            v = int.from_bytes(stack[off:off + 8], "little")
            w = where(mods, v)
            if w and not w.lower().startswith(("ntdll", "kernel")) or (w and len(rets) < 3):
                if is_after_call(hproc, mods, v):
                    rets.append(w)
            if len(rets) >= limit:
                break
        rip = where(mods, ctx.Rip) or hex(ctx.Rip)
        if busy_only and rip.lower().startswith(("ntdll.dll", "win32u.dll")):
            continue
        if namer:
            rets = [namer(r) for r in rets]
            rip = namer(rip)
        print("thread %d start=%s rip=%s" % (tid, where(mods, start.value or 0) or hex(start.value or 0), rip))
        print("    " + " ".join(rets))


if __name__ == "__main__":
    main()
