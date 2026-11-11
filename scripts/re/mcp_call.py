"""Call a running pyghidra-mcp (streamable HTTP) from the command line; run with re\\venv\\Scripts\\python.

python mcp_call.py [--url http://127.0.0.1:8000/mcp] tools                      list the tools and their arguments
python mcp_call.py [--url ...] <tool> '{"arg": "value", ...}'                     call one tool, print its result
"""
import asyncio
import json
import sys

help_flag = "-h" in sys.argv[1:] or "--help" in sys.argv[1:]
if help_flag or len(sys.argv) < 2:
    print(__doc__.strip())
    sys.exit(0 if help_flag else 2)

from mcp import ClientSession

try:  # MCP Python SDK 2
    from mcp.client.streamable_http import streamable_http_client as _http
except ImportError:  # SDK 1
    from mcp.client.streamable_http import streamablehttp_client as _http


async def main(url, tool, args):
    async with _http(url) as streams:
        read, write = streams[0], streams[1]
        async with ClientSession(read, write) as session:
            await session.initialize()
            if tool == "tools":
                for t in (await session.list_tools()).tools:
                    schema = getattr(t, "input_schema", None) or getattr(t, "inputSchema", None) or {}
                    props = schema.get("properties", {})
                    print("%s(%s): %s" % (t.name, ", ".join(props), (t.description or "").strip().splitlines()[0] if t.description else ""))
                return
            result = await session.call_tool(tool, args)
            for c in result.content:
                print(getattr(c, "text", c))


if __name__ == "__main__":
    argv = sys.argv[1:]
    url = "http://127.0.0.1:8000/mcp"
    if argv and argv[0] == "--url":
        url = argv[1]
        argv = argv[2:]
    tool = argv[0] if argv else "tools"
    args = json.loads(argv[1]) if len(argv) > 1 else {}
    asyncio.run(main(url, tool, args))
