"""Tribe avicenna: data hub squad, full GitHub features.

Pipeline: lead (open issue) -> backend_go (write CI, build, branch, commit,
push) -> qa (open PR, check CI). Repo = dwirijal/avicenna, cwd = local avicenna.
Chapter backend/QA standards injected. Agents drive the full GH flow
(issue -> branch -> PR -> CI) per the squad rule.
"""
from __future__ import annotations
import os

from google.adk.agents import Agent, SequentialAgent
from google.adk.models.lite_llm import LiteLlm

from shared.chapters import CHAPTER_BACKEND, CHAPTER_QA
from shared.souls import soul_block
from shared.github_ops import (
    gh_issue_tool, gh_branch_tool, gh_push_tool, gh_pr_tool, gh_ci_tool,
    ci_workflow_tool, DEFAULT_AVICENNA_DIR,
)
from shared.config import ROUTER_BASE_URL, ROUTER_API_KEY, MODEL_LEAD, MODEL_WORKER

try:
    import litellm
    litellm.success_callback = []; litellm.failure_callback = []; litellm.set_verbose = False
except Exception:
    pass

REPO = "dwirijal/avicenna"
BRANCH = "ci/add-go-workflow"


def _llm(model_id: str) -> LiteLlm:
    key = ROUTER_API_KEY or os.environ.get("OPENAI_API_KEY", "")
    return LiteLlm(model=f"openai/{model_id}", api_base=ROUTER_BASE_URL, api_key=key)


LEAD_INSTRUCTION = f"""\
{soul_block('lead')}
You are the avicenna squad lead. Tribe: avicenna (Go data hub for dwizzyOS).
Open a GitHub issue on repo "{REPO}" describing the task: wire Go CI
(build + vet) so the squad uses full GH features. Then finish and hand off.
Scope: orchestration + open the issue only. repo="{REPO}".
"""

BACKEND_INSTRUCTION = f"""\
{CHAPTER_BACKEND}
{soul_block('backend')}
You are the avicenna backend engineer (Go). Repo: {REPO}. cwd: {DEFAULT_AVICENNA_DIR}.
Steps, in order, using the EXACT tool names below — these are the ONLY tools
available. There is no `Write`/`write`/`edit` tool; do not call one.
1. Call `write_ci_workflow` (no args — defaults to lang=go) to add .github/workflows/ci.yml.
2. Call `gh_create_branch` with branch="{BRANCH}".
3. Call `gh_commit_push` with message="ci(avicenna): add go build+vet workflow".
Then report the branch name and finish. Do NOT open the PR (QA's job).
"""

QA_INSTRUCTION = f"""\
{CHAPTER_QA}
{soul_block('qa')}
You are the avicenna QA engineer. Repo: {REPO}.
Steps:
1. Call `gh_create_pr` with title="ci: add Go CI workflow", head="{BRANCH}",
   body summarizing the change (build + vet on push/PR).
2. Call `gh_check_ci` with branch="{BRANCH}".
Report the PR URL and CI result. End with PASS or FAIL.
"""


def build_tribe_avicenna() -> SequentialAgent:
    lead = Agent(
        name="avicenna_lead", model=_llm(MODEL_LEAD),
        instruction=LEAD_INSTRUCTION, description="avicenna lead: open issue",
        tools=[gh_issue_tool],
    )
    backend = Agent(
        name="avicenna_backend_go", model=_llm(MODEL_WORKER),
        instruction=BACKEND_INSTRUCTION, description="backend: CI + branch + push",
        tools=[ci_workflow_tool, gh_branch_tool, gh_push_tool],
    )
    qa = Agent(
        name="avicenna_qa", model=_llm(MODEL_WORKER),
        instruction=QA_INSTRUCTION, description="QA: PR + CI check",
        tools=[gh_pr_tool, gh_ci_tool],
    )
    return SequentialAgent(
        name="tribe_avicenna",
        sub_agents=[lead, backend, qa],
        description="avicenna squad: issue->branch->push->PR->CI",
    )
