"""StillOpen MCP server (stdio). Lets Claude Code, or any MCP client, read and update your job search.

Run:  python mcp_server.py
Register with Claude Code:  claude mcp add stillopen -- <python> <path-to>/mcp_server.py

This one talks to the database on this machine only; there is no network listener. To use the website you (or somebody) host
instead, make a token under Profile > Connect an AI assistant and register the web address (see docs/MCP.md).
"""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from tracker import mcp_tools as t  # noqa: E402
from tracker.mcp_registry import build_server  # noqa: E402
from tracker.services import who  # noqa: E402

# This process acts for exactly one account: STILLOPEN_USER, else the only superuser. It never sees anyone else's data.
try:
    t.set_user(who.resolve_user(os.environ.get("STILLOPEN_USER") or None))
except who.WhoError as exc:
    sys.exit(f"stillopen MCP: {exc}")

mcp = build_server()

if __name__ == "__main__":
    mcp.run("stdio")
