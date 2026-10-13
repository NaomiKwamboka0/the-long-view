"""hatua-mcp: Hatua's own MCP server (stdio). Run: python3 -m hatua.mcp_server"""
from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from . import tools

server = MCPServer(
    name="hatua-mcp",
    instructions=(
        "Tools for building a cited, teacher-approved CBC learner profile. "
        "Never assign a pathway, track or label. Never rank or compare learners. "
        "Every claim must cite R-/N-/A- evidence ids. Approval is done by a named teacher "
        "outside this server; update_profile is blocked until then."
    ),
)

for fn in (tools.list_learners, tools.ingest_record, tools.find_patterns,
           tools.get_evidence, tools.draft_summary, tools.update_profile):
    server.add_tool(fn)


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
