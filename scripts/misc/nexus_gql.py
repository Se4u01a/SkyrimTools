"""Query Nexus Mods through its public GraphQL API (no key, no login). Standard library only.

  python nexus_gql.py search "summoned swords" [--game skyrimspecialedition] [--count 10] [--sort downloads|updatedAt|endorsements|relevance]
  python nexus_gql.py grep "WeaponTypeBoomerang" [--game ...]     mods whose DESCRIPTION contains the text
  python nexus_gql.py mod 99230 [--game ...]                       name, author, version, dates, counters, tags, requirements
  python nexus_gql.py desc 99230 [--game ...] [--raw]              description as plain text (BBCode stripped)
  python nexus_gql.py files 99230 [--game ...]                     file list (name, version, category, size, fileId, description)
  python nexus_gql.py raw '<graphql query>'                        any query, JSON out

Game is a domain name (default skyrimspecialedition; game id 1704). Endpoint: https://api.nexusmods.com/v2/graphql
Output is UTF-8 regardless of the console code page.
"""
import argparse
import html
import json
import re
import sys
import urllib.request

URL = "https://api.nexusmods.com/v2/graphql"
GAME_IDS = {"skyrimspecialedition": 1704, "skyrim": 110, "skyrimvr": 2698, "fallout4": 1151, "starfield": 4187}


def gql(query):
    req = urllib.request.Request(
        URL, data=json.dumps({"query": query}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0 (SkyrimTools nexus_gql)"})
    with urllib.request.urlopen(req, timeout=40) as r:
        out = json.load(r)
    if out.get("errors"):
        sys.exit("GraphQL error: " + json.dumps(out["errors"], ensure_ascii=False)[:1500])
    return out["data"]


def q(s):
    return json.dumps(s)


def strip_bbcode(t):
    t = re.sub(r"<br\s*/?>", "\n", t or "")
    t = re.sub(r"<[^>]+>", "", t)
    t = re.sub(r"\[/?(?:b|i|u|size|color|font|center|list|spoiler|code|url|img|youtube|quote)[^\]]*\]", "", t)
    t = t.replace("[*]", "- ")
    return re.sub(r"\n{3,}", "\n\n", html.unescape(t)).strip()


def game_id(domain):
    if domain not in GAME_IDS:
        sys.exit(f"unknown game '{domain}': add its id to GAME_IDS (query games(...) or game(domainName:))")
    return GAME_IDS[domain]


def cmd_search(a, field="nameStemmed"):
    sort = "" if a.sort == "relevance" else f", sort:[{{{a.sort}:{{direction:DESC}}}}]"
    flt = f'gameDomainName:[{{value:{q(a.game)}}}], {field}:[{{value:{q(a.text)}, op: MATCHES}}]'
    d = gql(f"{{ mods(filter:{{{flt}}}{sort}, count:{a.count}) {{ totalCount nodes "
            f"{{ modId name author version downloads endorsements updatedAt summary }} }} }}")["mods"]
    print(f"total {d['totalCount']}")
    for m in d["nodes"]:
        print(f"{m['modId']:>7}  {m['name']}  | {m['author']} | v{m['version']} | {m['downloads']} dl | "
              f"{m['endorsements']} end | upd {m['updatedAt'][:10]}\n         {m['summary']}")


def cmd_mod(a):
    d = gql(f"{{ mod(gameId:{game_id(a.game)}, modId:{a.id}) {{ name author uploader {{ name }} version createdAt updatedAt "
            f"downloads endorsements adultContent tags {{ name }} summary modRequirements {{ nexusRequirements "
            f"{{ nodes {{ modName notes }} }} }} }} }}")["mod"]
    if not d:
        sys.exit("mod not found")
    tags = ", ".join(t["name"] for t in d.pop("tags"))
    reqs = d.pop("modRequirements")["nexusRequirements"]["nodes"]
    for k, v in d.items():
        print(f"{k}: {v}")
    print("tags:", tags)
    print("requirements:")
    for r in reqs:
        print("  -", r["modName"], f"({r['notes']})" if r["notes"] else "")


def cmd_desc(a):
    d = gql(f"{{ mod(gameId:{game_id(a.game)}, modId:{a.id}) {{ name description }} }}")["mod"]
    print("#", d["name"])
    print(d["description"] if a.raw else strip_bbcode(d["description"]))


def cmd_files(a):
    for f in gql(f"{{ modFiles(gameId:{game_id(a.game)}, modId:{a.id}) {{ name version category date sizeInBytes fileId "
                 f"description }} }}")["modFiles"]:
        print(f"{f['fileId']}  {f['category']:<13} v{f['version']:<8} {int(f['sizeInBytes'])//1024:>7} KB  {f['name']}"
              + (f"\n          {f['description']}" if f["description"] else ""))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)
    for name in ("search", "grep"):
        s = sp.add_parser(name)
        s.add_argument("text")
        s.add_argument("--count", type=int, default=10)
        s.add_argument("--sort", default="downloads", choices=["downloads", "updatedAt", "endorsements", "relevance"])
    for name in ("mod", "desc", "files"):
        s = sp.add_parser(name)
        s.add_argument("id", type=int)
        if name == "desc":
            s.add_argument("--raw", action="store_true")
    sp.add_parser("raw").add_argument("query")
    for s in sp.choices.values():
        if s.prog.split()[-1] != "raw":
            s.add_argument("--game", default="skyrimspecialedition")
    a = p.parse_args()
    if a.cmd == "raw":
        print(json.dumps(gql(a.query), ensure_ascii=False, indent=1))
    elif a.cmd == "search":
        cmd_search(a)
    elif a.cmd == "grep":
        cmd_search(a, "description")
    else:
        {"mod": cmd_mod, "desc": cmd_desc, "files": cmd_files}[a.cmd](a)


if __name__ == "__main__":
    main()
