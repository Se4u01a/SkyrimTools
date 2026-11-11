"""Decompile functions through a running pyghidra-mcp (HTTP); an ambiguous address resolves to its first named match.

%SKYRIM_RE_DIR%\\venv\\Scripts\\python %SKYRIM_TOOLS_REPO%\\scripts\\re\\decomp.py [--url http://127.0.0.1:8765/mcp] [--xrefs] <binary_name> <name-or-0xaddr>...
"""
import asyncio
import json
import re
import sys

help_flag = "-h" in sys.argv[1:] or "--help" in sys.argv[1:]
if help_flag or len(sys.argv) < 2:
    print(__doc__.strip())
    sys.exit(0 if help_flag else 2)

from mcp import ClientSession

try:
    from mcp.client.streamable_http import streamable_http_client as _http
except ImportError:
    from mcp.client.streamable_http import streamablehttp_client as _http


async def run(url, binary, targets, xrefs):
    async with _http(url) as streams:
        async with ClientSession(streams[0], streams[1]) as session:
            await session.initialize()
            for target in targets:
                for attempt in range(2):
                    res = await session.call_tool("decompile_function", {"binary_name": binary, "name_or_address": target,
                                                                         "include_xrefs": xrefs})
                    text = "".join(getattr(c, "text", "") for c in res.content)
                    try:
                        d = json.loads(text)
                    except ValueError:
                        print(text)
                        break
                    if d.get("error") and "Ambiguous" in d["error"] and attempt == 0:
                        m = re.search(r"one of these: ([^@]+?) @", d["error"])
                        if m:
                            target = m.group(1).strip()
                            continue
                    print("=" * 8, d.get("name"), "|", d.get("signature"))
                    if d.get("error"):
                        print("error:", d["error"])
                    print((d.get("code") or "").replace("\r", ""))
                    if xrefs and d.get("xrefs"):
                        print("xrefs:", json.dumps(d["xrefs"])[:3000])
                    break


if __name__ == "__main__":
    argv = sys.argv[1:]
    url = "http://127.0.0.1:8765/mcp"
    if argv[0] == "--url":
        url, argv = argv[1], argv[2:]
    xrefs = "--xrefs" in argv
    argv = [a for a in argv if a != "--xrefs"]
    asyncio.run(run(url, argv[0], argv[1:], xrefs))
