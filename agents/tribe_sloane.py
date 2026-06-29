"""Tribe sloane (1 tribe) with 3 squads as a sequential DAG:
  squad_scraper   -> scraper_agent (fetch+write raw+merge)
  squad_processor -> processor_agent (enrich mal_id via Jikan)
  squad_store     -> store_agent (governance/health)
shared: lead (decompose) + qa (final gate)

Lazy activation: 1 worker per squad + shared lead/qa = 5 agents, not 9.
Scale to lead+worker+qa per squad when each squad's job is heavy enough.
Chapter backend/QA standards injected where relevant.
"""
from __future__ import annotations
import os

from google.adk.agents import Agent, SequentialAgent
from google.adk.models.lite_llm import LiteLlm

from shared.chapters import CHAPTER_BACKEND, CHAPTER_QA
from shared.souls import soul_block
from shared.config import ROUTER_BASE_URL, ROUTER_API_KEY, MODEL_LEAD, MODEL_WORKER
from sloane.agents.tools import fetch_tool, write_tool, assert_tool
from sloane.agents.squad_tools import enrich_tool, store_health_tool

try:
    import litellm
    litellm.success_callback = []; litellm.failure_callback = []; litellm.set_verbose = False
except Exception:
    pass


def _llm(model_id: str, is_lead: bool = False) -> LiteLlm:
    from shared.config import is_high_capability
    if is_lead and not is_high_capability(model_id):
        raise ValueError(f"Lead agents must use high-capability models. '{model_id}' is not permitted.")
    key = ROUTER_API_KEY or os.environ.get("OPENAI_API_KEY", "")
    return LiteLlm(model=f"openai/{model_id}", api_base=ROUTER_BASE_URL, api_key=key)


LEAD = f"""\
{soul_block('lead')}
You are the sloane tribe lead (1 tribe, 3 squads: scraper/processor/store).
Decompose: scraper fetches a source; processor enriches canonicals with MAL IDs;
store checks DB health. For this run use source "oploverz". Hand off in order.
Scope: orchestration only, no tools.
"""

SCRAPER = f"""\
{CHAPTER_BACKEND}
{soul_block('scraper')}
squad_scraper. Scope: fetch source + write raw + merge to canonical.
1. Call `fetch_source` with source_slug="oploverz".
2. Call `write_entities_tool` with the returned entities.
Report raw/canonical counts. Do NOT enrich or health-check (other squads).
"""

PROCESSOR = f"""\
{CHAPTER_BACKEND}
{soul_block('processor')}
squad_processor. Scope: enrichment ONLY. Give canonicals authoritative MAL IDs.
Call `enrich_pending_canonicals` with limit=5. Report how many mal_ids resolved.
"""

STORE = f"""\
{CHAPTER_BACKEND}
{soul_block('store')}
squad_store. Scope: DB governance/lean. Call `store_health_check`. Report the
ratio (canonical/raw), orphan raw count, and whether lean=True. Do not fix.
"""

QA = f"""\
{CHAPTER_QA}
{soul_block('qa')}
sloane QA. Final gate. Call `assert_quality` with source_slug="oploverz" only —
do NOT pass `expected` (canonical count drifts as merge consolidates duplicates;
hardcoding it false-fails). GATE fail only on real check failure (orphan_raw,
duplicates), not count. Report PASS/FAIL with failing checks. End with PASS or FAIL.
"""


def build_tribe_sloane() -> SequentialAgent:
    return SequentialAgent(name="tribe_sloane", sub_agents=[
        Agent(name="sloane_lead", model=_llm(MODEL_LEAD, is_lead=True), instruction=LEAD,
              description="tribe lead: decompose across 3 squads"),
        Agent(name="sloane_scraper", model=_llm(MODEL_WORKER), instruction=SCRAPER,
              description="squad_scraper: fetch+write+merge", tools=[fetch_tool, write_tool]),
        Agent(name="sloane_processor", model=_llm(MODEL_WORKER), instruction=PROCESSOR,
              description="squad_processor: enrich mal_id", tools=[enrich_tool]),
        Agent(name="sloane_store", model=_llm(MODEL_WORKER), instruction=STORE,
              description="squad_store: DB governance", tools=[store_health_tool]),
        Agent(name="sloane_qa", model=_llm(MODEL_WORKER), instruction=QA,
              description="QA: final quality gate", tools=[assert_tool]),
    ], description="tribe sloane: lead->scraper->processor->store->qa")
