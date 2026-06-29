"""Static agent registry: agent_id -> {soul role, chapter, skills, tools, extensions}.

Mirrors the tool lists wired in tribe_factory.py / avicenna_tribe.py /
sloane/agents/*.py. Hand-maintained because agent tool-sets are defined in code,
not DB — introspecting built tribes at import-time would import litellm/ADK and
spin MCP servers on every dashboard render.

ponytail: hand dict now; if agents drift from this, add a one-time build-step
that dumps tool names to a JSON the dashboard reads. Update this when a squad
gains a tool.
"""
from __future__ import annotations

# skills = reusable capabilities (the agent CAN do this); tools = concrete
# FunctionTool/MCP names it calls; extensions = MCP servers wired.
REGISTRY: dict[str, dict] = {
    # ---- sloane (3 squads) ----
    "sloane_lead": {"role": "lead", "chapter": None, "skills": ["planning", "delegation", "issue-authoring"], "tools": ["gh_create_issue"], "extensions": []},
    "sloane_scraper": {"role": "scraper", "chapter": "backend", "skills": ["http-fetch", "normalize", "dedup-merge"], "tools": ["fetch_source", "write_entities"], "extensions": []},
    "sloane_processor": {"role": "processor", "chapter": "backend", "skills": ["enrichment", "mal-id-resolve"], "tools": ["enrich_pending_canonicals"], "extensions": []},
    "sloane_store": {"role": "store", "chapter": "devops", "skills": ["db-governance", "lean-ratio", "orphan-detect"], "tools": ["store_health_check"], "extensions": []},
    "sloane_qa": {"role": "qa", "chapter": "qa", "skills": ["quality-gate", "contract-assert", "count-check"], "tools": ["assert_quality"], "extensions": []},
    # ---- avicenna (Go) ----
    "avicenna_lead": {"role": "lead", "chapter": None, "skills": ["planning", "delegation", "issue-authoring"], "tools": ["gh_create_issue"], "extensions": []},
    "avicenna_backend_go": {"role": "backend", "chapter": "backend", "skills": ["go-build", "vet", "ci-wiring", "github-flow"], "tools": ["write_ci_workflow", "gh_create_branch", "gh_commit_push"], "extensions": ["context7"]},
    "avicenna_frontend": {"role": "frontend", "chapter": "frontend", "skills": ["ui", "design-tokens"], "tools": [], "extensions": []},
    "avicenna_qa": {"role": "qa", "chapter": "qa", "skills": ["quality-gate", "ci-verify", "pr-flow"], "tools": ["gh_create_pr", "gh_check_ci"], "extensions": []},
    # ---- jawatch (Next.js+bun) ----
    "jawatch_lead": {"role": "lead", "chapter": None, "skills": ["planning", "delegation", "issue-authoring"], "tools": ["gh_create_issue"], "extensions": []},
    "jawatch_frontend_next": {"role": "frontend", "chapter": "frontend", "skills": ["nextjs", "bun", "ui", "design-tokens"], "tools": ["write_ci_workflow", "gh_create_branch", "gh_commit_push"], "extensions": ["context7"]},
    "jawatch_bff": {"role": "backend", "chapter": "backend", "skills": ["bff", "api-proxy"], "tools": ["write_ci_workflow", "gh_create_branch", "gh_commit_push"], "extensions": ["context7"]},
    "jawatch_qa": {"role": "qa", "chapter": "qa", "skills": ["quality-gate", "ci-verify", "pr-flow"], "tools": ["gh_create_pr", "gh_check_ci"], "extensions": []},
    # ---- heimdall (auth/gateway) ----
    "heimdall_lead": {"role": "lead", "chapter": None, "skills": ["planning", "delegation", "issue-authoring"], "tools": ["gh_create_issue"], "extensions": []},
    "heimdall_backend": {"role": "backend", "chapter": "backend", "skills": ["bun", "auth", "session", "ci-wiring"], "tools": ["write_ci_workflow", "gh_create_branch", "gh_commit_push"], "extensions": ["context7"]},
    "heimdall_qa": {"role": "qa", "chapter": "qa", "skills": ["quality-gate", "ci-verify", "pr-flow"], "tools": ["gh_create_pr", "gh_check_ci"], "extensions": []},
    "heimdall_devops": {"role": "devops", "chapter": "devops", "skills": ["infra", "secrets", "healthcheck"], "tools": ["write_ci_workflow", "gh_create_branch", "gh_commit_push"], "extensions": ["context7"]},
    # ---- gebelin (infra) ----
    "gebelin_lead": {"role": "lead", "chapter": None, "skills": ["planning", "delegation", "issue-authoring"], "tools": ["gh_create_issue"], "extensions": []},
    "gebelin_devops": {"role": "devops", "chapter": "devops", "skills": ["docker-compose", "cloudflare-tunnel", "pg", "valkey"], "tools": ["write_ci_workflow", "gh_create_branch", "gh_commit_push"], "extensions": ["context7"]},
    "gebelin_backend": {"role": "backend", "chapter": "backend", "skills": ["ci-wiring", "github-flow"], "tools": ["write_ci_workflow", "gh_create_branch", "gh_commit_push"], "extensions": ["context7"]},
    "gebelin_qa": {"role": "qa", "chapter": "qa", "skills": ["quality-gate", "ci-verify", "pr-flow"], "tools": ["gh_create_pr", "gh_check_ci"], "extensions": []},
    # ---- chronos (timeseries UI) ----
    "chronos_lead": {"role": "lead", "chapter": None, "skills": ["planning", "delegation", "issue-authoring"], "tools": ["gh_create_issue"], "extensions": []},
    "chronos_frontend": {"role": "frontend", "chapter": "frontend", "skills": ["ui", "timeseries-viz", "design-tokens"], "tools": ["write_ci_workflow", "gh_create_branch", "gh_commit_push"], "extensions": ["context7"]},
    "chronos_bff": {"role": "backend", "chapter": "backend", "skills": ["go", "bff", "ci-wiring"], "tools": ["write_ci_workflow", "gh_create_branch", "gh_commit_push"], "extensions": ["context7"]},
    "chronos_qa": {"role": "qa", "chapter": "qa", "skills": ["quality-gate", "ci-verify", "pr-flow"], "tools": ["gh_create_pr", "gh_check_ci"], "extensions": []},
}


def agent_meta(agent_id: str) -> dict:
    """Return registry entry for an agent_id (empty defaults if unknown)."""
    base = REGISTRY.get(agent_id, {})
    return {
        "role": base.get("role", "unknown"),
        "chapter": base.get("chapter"),
        "skills": base.get("skills", []),
        "tools": base.get("tools", []),
        "extensions": base.get("extensions", []),
    }
