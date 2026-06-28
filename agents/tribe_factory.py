"""Tribe factory: build a product tribe DAG from one config dict.

One function replaces N copy-paste tribe files. Each product tribe =
SequentialAgent lead(orchestrate+open issue) -> backend(write CI, branch, push)
-> qa(open PR, check CI). Full GH flow (issue/branch/PR/CI) per squad rule.

Dynamic agent positions: config maps role->agent_id; swap agent_id per cycle
without touching the DAG shape. 1 squad = 1 feature (product's primary feature).

ponytail: 1 squad per product for now — the squad's roles ARE the feature's
roles. Split into N squads when a product has >=2 independent features
requiring separate pipelines. Then call build_product_tribe N times.
"""
from __future__ import annotations
import os
from dataclasses import dataclass

from google.adk.agents import Agent, SequentialAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.function_tool import FunctionTool

from shared.chapters import CHAPTER_BACKEND, CHAPTER_QA
from shared.souls import soul_block
from shared.mcp_tools import context7_toolset
from shared.github_ops import (
    gh_issue_tool, gh_branch_tool, gh_commit_push, gh_pr_tool, gh_ci_tool,
    write_ci_workflow,
)
from shared.config import ROUTER_BASE_URL, ROUTER_API_KEY, MODEL_LEAD, MODEL_WORKER

try:
    import litellm
    litellm.success_callback = []; litellm.failure_callback = []; litellm.set_verbose = False
except Exception:
    pass


@dataclass(frozen=True)
class TribeConfig:
    name: str            # tribe slug e.g. "jawatch"
    product: str         # human label e.g. "media catalog UI"
    repo: str            # "dwirijal/Jawatch"
    cwd: str             # local repo dir
    branch: str          # feature branch to create
    lang: str            # go | nextjs-bun
    issue_title: str
    issue_body: str
    commit_msg: str
    pr_title: str
    base: str = "main"   # default branch name (chronos uses master)
    # ECC skills to apply per role in this tribe (injected into instructions).
    # Agents reference these so they follow battle-tested patterns, not guess.
    skills: dict[str, list[str]] = None  # role -> skill names


def _llm(model_id: str) -> LiteLlm:
    key = ROUTER_API_KEY or os.environ.get("OPENAI_API_KEY", "")
    return LiteLlm(model=f"openai/{model_id}", api_base=ROUTER_BASE_URL, api_key=key)


# ECC skill map per (lang, role). Agents get tribe+role-appropriate skills
# injected into their instruction so they follow proven patterns, not improvise.
# Source: ~/.claude/plugins/marketplaces/ecc/skills/
SKILLS = {
    "go": {
        "backend": ["golang-patterns", "golang-testing", "api-design"],
        "qa": ["golang-testing", "e2e-testing", "ai-regression-testing"],
        "lead": ["plan-orchestrate", "agentic-engineering", "github-ops"],
        "devops": ["docker-patterns", "github-ops"],
    },
    "nextjs-bun": {
        "frontend": ["frontend-patterns", "frontend-design-direction", "frontend-a11y", "bun-runtime"],
        "backend": ["bun-runtime", "api-design", "backend-patterns"],
        "qa": ["e2e-testing", "browser-qa", "ai-regression-testing"],
        "lead": ["plan-orchestrate", "agentic-engineering", "github-ops"],
    },
    "compose": {
        "devops": ["docker-patterns", "homelab-network-setup"],
        "backend": ["backend-patterns", "api-design"],
        "qa": ["e2e-testing"],
        "lead": ["plan-orchestrate", "agentic-engineering", "github-ops"],
    },
}


def _skill_block(lang: str, role: str) -> str:
    """Render the skill list as an instruction snippet for an agent."""
    skills = (SKILLS.get(lang, {}) or {}).get(role, [])
    if not skills:
        return ""
    return ("\nApply these ECC skills (proven patterns, do not improvise): "
            + ", ".join(skills) + ".\n")


def build_product_tribe(cfg: TribeConfig) -> SequentialAgent:
    """Build lead->backend->qa DAG for one product tribe. Full GH flow."""
    tools = [gh_issue_tool, write_ci_workflow, gh_branch_tool,
             gh_commit_push, gh_pr_tool, gh_ci_tool]

    lead = Agent(
        name=f"{cfg.name}_lead",
        model=_llm(MODEL_LEAD),
        instruction=(
            f"{_skill_block(cfg.lang, 'lead')}{soul_block('lead')}"
            f"You are the {cfg.name} tribe lead (product: {cfg.product}). "
            f"Make a short plan, then open a GitHub issue on repo \"{cfg.repo}\" "
            f"titled \"{cfg.issue_title}\" with body \"{cfg.issue_body}\". "
            f"Hand off to backend. Scope: orchestration + open issue only. "
            f"repo=\"{cfg.repo}\"."
        ),
        tools=[gh_issue_tool],
    )

    backend = Agent(
        name=f"{cfg.name}_backend",
        model=_llm(MODEL_WORKER),
        instruction=(
            f"{CHAPTER_BACKEND}\n{_skill_block(cfg.lang, 'backend')}{soul_block('backend')}"
            f"You are the {cfg.name} backend engineer ({cfg.lang}). "
            f"Repo: {cfg.repo}. cwd: {cfg.cwd}. Steps, exact tool names:\n"
            f"1. Call `write_ci_workflow` with lang=\"{cfg.lang}\".\n"
            f"2. Call `gh_create_branch` with branch=\"{cfg.branch}\" cwd=\"{cfg.cwd}\" base=\"{cfg.base}\".\n"
            f"3. Call `gh_commit_push` with message=\"{cfg.commit_msg}\" cwd=\"{cfg.cwd}\".\n"
            f"Report the branch name. Do NOT open the PR (QA's job)."
        ),
        tools=[FunctionTool(write_ci_workflow), gh_branch_tool,
               FunctionTool(gh_commit_push), context7_toolset()],
    )

    qa = Agent(
        name=f"{cfg.name}_qa",
        model=_llm(MODEL_WORKER),
        instruction=(
            f"{CHAPTER_QA}\n{_skill_block(cfg.lang, 'qa')}{soul_block('qa')}"
            f"You are the {cfg.name} QA. Repo: {cfg.repo}. Steps:\n"
            f"1. Call `gh_create_pr` with title=\"{cfg.pr_title}\" "
            f"body=\"CI workflow + build verification\" repo=\"{cfg.repo}\" "
            f"head=\"{cfg.branch}\" base=\"{cfg.base}\".\n"
            f"2. Call `gh_check_ci` with branch=\"{cfg.branch}\" repo=\"{cfg.repo}\".\n"
            f"End by reporting PASS or FAIL with the CI status."
        ),
        tools=[gh_pr_tool, gh_ci_tool],
    )

    return SequentialAgent(name=f"tribe_{cfg.name}", sub_agents=[lead, backend, qa])


# --- product configs (1 squad = 1 primary feature per product) ---
PRODUCTS: dict[str, TribeConfig] = {
    "jawatch": TribeConfig(
        name="jawatch", product="media catalog UI (Next.js+bun)",
        repo="dwirijal/Jawatch", cwd="/home/dwizzy/dwizzyOS/jawatch",
        branch="ci/add-bun-workflow", lang="nextjs-bun",
        issue_title="Wire Bun CI (install+build+lint)",
        issue_body="Add GitHub Actions CI using bun for build verification.",
        commit_msg="ci(jawatch): add bun build CI workflow",
        pr_title="ci: bun build workflow",
    ),
    "heimdall": TribeConfig(
        name="heimdall", product="auth/gateway/security",
        repo="dwirijal/heimdall", cwd="/home/dwizzy/dwizzyOS/heimdall",
        branch="ci/add-bun-workflow", lang="nextjs-bun",
        issue_title="Wire Bun CI (build+typecheck)",
        issue_body="Add GitHub Actions CI using bun for build + typecheck.",
        commit_msg="ci(heimdall): add bun build CI workflow",
        pr_title="ci: bun build workflow",
    ),
    "gebelin": TribeConfig(
        name="gebelin", product="infra/DB ops (PG+Supabase+Neon+Cloudflare)",
        repo="dwirijal/Gebelin", cwd="/home/dwizzy/dwizzyOS/Gebelin",
        branch="ci/add-compose-validate", lang="compose",
        issue_title="Add docker-compose config validation CI",
        issue_body="Add CI step validating docker-compose.yml (infra ops safety).",
        commit_msg="ci(gebelin): add compose config validation CI",
        pr_title="ci: compose config validation",
    ),
    "chronos": TribeConfig(
        name="chronos", product="timeseries data UI (time/astronomy/weather)",
        repo="dwirijal/chronos", cwd="/home/dwizzy/dwizzyOS/chronos",
        branch="ci/add-go-workflow", lang="go", base="master",
        issue_title="Wire Go CI (vet+build)",
        issue_body="Add GitHub Actions CI using go for vet+build verification.",
        commit_msg="ci(chronos): add go build CI workflow",
        pr_title="ci: go build workflow",
    ),
}


def build_tribe(name: str) -> SequentialAgent:
    if name not in PRODUCTS:
        raise KeyError(f"unknown tribe '{name}'; known: {list(PRODUCTS)}")
    return build_product_tribe(PRODUCTS[name])
