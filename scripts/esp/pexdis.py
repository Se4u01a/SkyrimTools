"""Minimal Skyrim .pex disassembler: python pexdis.py file.pex [...]"""
import struct
import sys

OPS = {0: ("nop", 0), 1: ("iadd", 3), 2: ("fadd", 3), 3: ("isub", 3), 4: ("fsub", 3), 5: ("imul", 3), 6: ("fmul", 3),
       7: ("idiv", 3), 8: ("fdiv", 3), 9: ("imod", 3), 10: ("not", 2), 11: ("ineg", 2), 12: ("fneg", 2),
       13: ("assign", 2), 14: ("cast", 2), 15: ("cmp_eq", 3), 16: ("cmp_lt", 3), 17: ("cmp_le", 3),
       18: ("cmp_gt", 3), 19: ("cmp_ge", 3), 20: ("jmp", 1), 21: ("jmpt", 2), 22: ("jmpf", 2),
       23: ("callmethod", 3), 24: ("callparent", 2), 25: ("callstatic", 3), 26: ("return", 1), 27: ("strcat", 3),
       28: ("propget", 3), 29: ("propset", 3), 30: ("array_create", 2), 31: ("array_length", 2),
       32: ("array_get", 3), 33: ("array_set", 3), 34: ("array_find", 4), 35: ("array_rfind", 4)}
VARARG = {23, 24, 25}


class R:
    def __init__(self, b):
        self.b, self.p = b, 0

    def u(self, fmt):
        v = struct.unpack_from(">" + fmt, self.b, self.p)
        self.p += struct.calcsize(">" + fmt)
        return v[0]

    def ws(self):
        n = self.u("H")
        s = self.b[self.p:self.p + n].decode("cp1251", "replace")
        self.p += n
        return s


def main(path):
    r = R(open(path, "rb").read())
    assert r.u("I") == 0xFA57C0DE
    r.u("B"); r.u("B"); r.u("H"); r.u("Q")
    src = r.ws(); r.ws(); r.ws()
    st = [r.ws() for _ in range(r.u("H"))]
    S = lambda i: st[i]
    if r.u("B"):
        r.u("Q")
        for _ in range(r.u("H")):
            r.u("H"); r.u("H"); r.u("H"); r.u("B")
            n = r.u("H"); r.p += 2 * n
    for _ in range(r.u("H")):
        r.u("H"); r.u("B")

    def data():
        t = r.u("B")
        if t == 0: return "None"
        if t == 1: return S(r.u("H"))
        if t == 2: return repr(S(r.u("H")))
        if t == 3: return str(r.u("i"))
        if t == 4: return repr(round(r.u("f"), 6))
        if t == 5: return str(bool(r.u("B")))
        raise ValueError(t)

    def func(name):
        ret = S(r.u("H")); r.u("H"); r.u("I"); fl = r.u("B")
        params = [(S(r.u("H")), S(r.u("H"))) for _ in range(r.u("H"))]
        locs = [(S(r.u("H")), S(r.u("H"))) for _ in range(r.u("H"))]
        print("  FUNCTION %s %s(%s)%s" % (ret, name, ", ".join("%s %s" % (t, n) for n, t in params),
                                         " native" if fl & 2 else ""))
        if locs:
            print("    locals:", ", ".join("%s %s" % (t, n) for n, t in locs))
        for i in range(r.u("H")):
            op = r.u("B")
            nm, n = OPS[op]
            args = [data() for _ in range(n)]
            if op in VARARG:
                cnt = int(data())
                args += [data() for _ in range(cnt)]
            print("    %3d %s %s" % (i, nm, ", ".join(args)))

    print("### %s (%s)" % (path, src))
    for _ in range(r.u("H")):
        name = S(r.u("H")); r.u("I"); parent = S(r.u("H")); r.u("H"); r.u("I"); r.u("H")
        print("SCRIPTNAME %s extends %s" % (name, parent))
        for _ in range(r.u("H")):
            vn = S(r.u("H")); vt = S(r.u("H")); r.u("I")
            print("  var %s %s = %s" % (vt, vn, data()))
        for _ in range(r.u("H")):
            pn = S(r.u("H")); pt = S(r.u("H")); r.u("H"); r.u("I"); fl = r.u("B")
            if fl & 4:
                print("  property %s %s auto -> %s" % (pt, pn, S(r.u("H"))))
            else:
                print("  property %s %s" % (pt, pn))
                if fl & 1: func("get")
                if fl & 2: func("set")
        for _ in range(r.u("H")):
            sn = S(r.u("H"))
            print(" STATE '%s'" % sn)
            for _ in range(r.u("H")):
                func(S(r.u("H")))


if __name__ == "__main__":
    help_flag = "-h" in sys.argv[1:] or "--help" in sys.argv[1:]
    if help_flag or len(sys.argv) < 2:
        print(__doc__.strip())
        sys.exit(0 if help_flag else 2)
    for p in sys.argv[1:]:
        main(p)
        print()
