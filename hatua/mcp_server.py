"""hatua-mcp: Hatua's own MCP server (stdio). Run: python3 -m hatua.mcp_server"""
from __future__ import annotations

from . import tools

INSTRUCTIONS = (
    "Tools for building a cited, teacher-approved CBC learner profile. "
    "Never assign a pathway, track or label. Never rank or compare learners. "
    "Every claim must cite R-/N-/A- evidence ids. Approval is done by a named teacher "
    "outside this server; update_profile is blocked until then."
)
TOOLS = (tools.list_learners, tools.ingest_record, tools.review_queue, tools.find_patterns,
         tools.get_evidence, tools.draft_summary, tools.update_profile)

try:  # mcp 2.x
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server

server = _Server(name="hatua-mcp", instructions=INSTRUCTIONS, log_level="WARNING")
for fn in TOOLS:
    server.add_tool(fn)


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
