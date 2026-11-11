"""Adds the keys of the dist ini missing from the deployed one. Every existing value and line stays as it is.

    python merge_ini.py <dist.ini> <deployed.ini>      (writes deployed.ini only when a key was added; keeps its BOM/EOL)
"""
import re
import sys

help_flag = "-h" in sys.argv[1:] or "--help" in sys.argv[1:]
if help_flag or len(sys.argv) < 3:
    print(__doc__.strip())
    sys.exit(0 if help_flag else 2)


def parse(lines):
    section, keys = None, {}
    for line in lines:
        m = re.match(r"\s*\[(.+?)\]", line)
        if m:
            section = m.group(1).lower()
            keys.setdefault(section, set())
        elif section and not line.lstrip().startswith(";"):
            k = line.split("=", 1)[0].strip().lower() if "=" in line else None
            if k:
                keys[section].add(k)
    return keys


dist_path, deployed_path = sys.argv[1:3]
raw = open(deployed_path, "rb").read()
newline = "\r\n" if b"\r\n" in raw else "\n"
encoding = "utf-8-sig" if raw.startswith(b"\xef\xbb\xbf") else "utf-8"
deployed = raw.decode(encoding).splitlines()
dist = open(dist_path, encoding="utf-8").read().splitlines()
have = parse(deployed)

section, comments, added = None, [], []
for line in dist:
    m = re.match(r"\s*\[(.+?)\]", line)
    if m:
        section, comments = m.group(1), []
        continue
    if line.lstrip().startswith(";"):
        comments.append(line)
        continue
    if not section or "=" not in line:
        comments = []
        continue
    key = line.split("=", 1)[0].strip()
    low = section.lower()
    if key.lower() not in have.get(low, set()):
        block = comments + [line]
        if low not in have:
            deployed += ["", f"[{section}]"] + block
            have[low] = set()
        else:
            at = next(i for i, l in enumerate(deployed) if re.match(rf"\s*\[{re.escape(section)}\]", l, re.I))
            end = at + 1
            while end < len(deployed) and not deployed[end].lstrip().startswith("["):
                end += 1
            while end > at + 1 and not deployed[end - 1].strip():
                end -= 1
            deployed[end:end] = block
        have[low].add(key.lower())
        added.append(f"[{section}] {key}")
    comments = []

if added:
    with open(deployed_path, "wb") as f:
        f.write((newline.join(deployed) + newline).encode(encoding))
print("added:", added or "nothing")
