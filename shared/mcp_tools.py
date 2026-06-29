"""MCP toolsets for tribe agents — external capabilities via Model Context Protocol.

Spec (user): "pastikan agents bisa memakai skill, tools, mcp". MCP gives agents
live access to docs (Context7) and the local filesystem without hand-coding each
as a FunctionTool. Each tribe gets the toolsets appropriate to its language.

MCPToolset is deprecated in ADK 2.3.0 → use McpToolset (lowercase c).
StdioConnectionParams replaces StdioServerParameters (recommended form).

ponytail: one stdio MCP per broadly-useful capability. Don't wrap every MCP
server — add only when an agent demonstrably needs it. Context7 (docs) + a
filesystem server cover 90% of dev work; git ops already handled by github_ops
FunctionTools (no MCP needed).
"""
from __future__ import annotations

from mcp import StdioServerParameters  # still accepted, just not "recommended"
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset


def context7_toolset() -> McpToolset:
    """Context7 docs MCP — resolve library IDs + query up-to-date docs.

    Useful for every tribe: agents look up Next.js/Go/Supabase/ADK API behavior
    instead of guessing from training data.
    """
    return McpToolset(connection_params=StdioServerParameters(
        command="npx",
        args=["-y", "@upstash/context7-mcp"],
    ))


def puppeteer_toolset() -> McpToolset:
    """Puppeteer MCP — browser interaction and scraping."""
    return McpToolset(connection_params=StdioServerParameters(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-puppeteer"],
    ))


# lang -> list of MCP toolsets that tribe's agents get
MCP_BY_LANG: dict[str, list] = {
    "go": [],  # Go docs via Context7 only (shared below); no lang-specific MCP
    "nextjs-bun": [],
    "compose": [],
}


def mcp_tools_for(lang: str) -> list:
    """Return MCP toolsets for a tribe language. Empty list = none wired yet.

    ponytail: Context7 is shared across all langs (added by caller at agent
    level, not per-lang). Per-lang MCP servers added here when a real need
    surfaces. Today: agents have github_ops (GH) + chapter standards + ECC
    skills + Context7 (docs). That covers the dev loop end-to-end.
    """
    return MCP_BY_LANG.get(lang, [])
