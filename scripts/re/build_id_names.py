"""Names for Skyrim SE REL::IDs, from every source that uses them (CommonLibSSE-NG, and our own plugins).

python build_id_names.py [SRC_DIR ...]   ->  SkyrimTools\\data\\se_id_names.tsv  (id, name, where)
Without SRC_DIR: the maintainer's source trees in ROOTS. The shipped table is already built; nobody else needs this.

A use is RELOCATION_ID(se, ae) / REL::RelocationID(se, ae) (the SE id is the first) or REL::ID(n). Its name is the
enclosing class plus the function or variable it sits in, guessed from the lines above; for RE/Offsets.h-style
constants the constant's own name. Good enough to read a stack; check the file when it matters.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOTS = [
    r"D:\Games\Issen\CommonLibSSE-NG\include",
    r"D:\Games\Issen\CommonLibSSE-NG\src",
    r"D:\Games\Issen\IssenFramework\src",
    r"D:\Games\Issen\ReactiveDodgeFramework\src",
    r"D:\Games\Issen\SkyrimSE_DismemberingFramework\src",
]
OUT = os.path.join(HERE, "..", "..", "data", "se_id_names.tsv")

USE = re.compile(r"(?:RELOCATION_ID|RelocationID)\(\s*(\d+)\s*,|REL::ID\(\s*(\d+)\s*\)|REL::ID\{\s*(\d+)\s*\}")
CLASS = re.compile(r"^\s*(?:class|struct)\s+(?:RE_\w+\s+)?(\w+)(?:\s*final)?\s*(?::|$|\{)")
NAMESPACE = re.compile(r"^\s*namespace\s+([\w:]+)")
FUNC = re.compile(r"([~\w:<>]+)\s*\([^;{}]*\)\s*(?:const)?\s*(?:noexcept)?\s*(?:override)?\s*(?:->\s*[\w:<>*&]+)?\s*\{?\s*$")
VAR = re.compile(r"(?:constexpr|inline|static)\s+[\w:<>]+(?:\s+[\w:<>]+)*\s+(\w+)\s*[\({=]")
KEYWORDS = {"if", "for", "while", "switch", "return", "sizeof", "static_assert", "decltype", "RELOCATION_ID", "REL"}


def name_for(lines, k, use_line):
    v = VAR.search(use_line)
    own = v.group(1) if v and v.group(1) not in ("func", "singleton", "vtbl", "target", "addr", "hook") else None
    func = None
    cls = None
    ns = None
    for j in range(k - 1, max(-1, k - 400), -1):
        line = lines[j]
        if func is None:
            m = FUNC.search(line.split("//")[0])
            if m and m.group(1).split("::")[-1] not in KEYWORDS:
                func = m.group(1)
        if cls is None:
            m = CLASS.search(line)
            if m:
                cls = m.group(1)
        if ns is None:
            m = NAMESPACE.search(line)
            if m:
                ns = m.group(1)
        if cls and func:
            break
    if v and v.group(1) == "singleton":
        func = "singleton"
    if v and v.group(1) == "vtbl":
        func = "vtable"
    parts = [p for p in (cls if cls else (ns or ""), own or func or "?") if p]
    return "::".join(parts)


def main():
    roots = sys.argv[1:] or ROOTS
    base = os.path.commonpath([os.path.dirname(os.path.abspath(r)) for r in roots])
    rows = {}
    for root in roots:
        for dirpath, _, files in os.walk(root):
            if "third_party" in dirpath:
                continue
            for fn in files:
                if not fn.endswith((".h", ".hpp", ".cpp", ".inl")):
                    continue
                path = os.path.join(dirpath, fn)
                try:
                    lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
                except OSError:
                    continue
                for k, line in enumerate(lines):
                    for m in USE.finditer(line):
                        i = int(next(g for g in m.groups() if g))
                        rel = os.path.relpath(path, base)
                        name = name_for(lines, k, line)
                        rows.setdefault(i, []).append((name, "%s:%d" % (rel, k + 1)))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("id\tname\twhere\n")
        for i in sorted(rows):
            seen = []
            for name, where in rows[i]:
                if name not in seen:
                    seen.append(name)
            f.write("%d\t%s\t%s\n" % (i, " | ".join(seen[:3]), rows[i][0][1]))
    print("%d ids -> %s" % (len(rows), os.path.normpath(OUT)))


if __name__ == "__main__":
    main()
