"""Run the sloane tribe smoke: lead->backend->qa via ADK Runner.

Wires GroupMemoryService (RBAC) as the runner's memory. Prints each agent's
final text. Exit 0 on QA PASS, 1 on FAIL.
"""
from __future__ import annotations
import asyncio
import os
import sys

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part

from agents.tribe_sloane import build_tribe_sloane
from shared.config import ROUTER_API_KEY
from shared.memory_service import GroupMemoryService

TASK = (
    "Smoke task for tribe sloane: ingest the 'oploverz' source end-to-end "
    "(fetch, write to PG) then run QA. Use oploverz."
)


async def main() -> int:
    if not ROUTER_API_KEY and not os.environ.get("OPENAI_API_KEY"):
        print("ERROR: set OPENAI_API_KEY (9router key)", file=sys.stderr)
        return 2
    tribe = build_tribe_sloane()
    sessions = InMemorySessionService()
    memory = GroupMemoryService()
    runner = Runner(
        agent=tribe, app_name="tribe-sloane",
        session_service=sessions, memory_service=memory,
    )
    session = await sessions.create_session(app_name="tribe-sloane", user_id="operator")
    qa_text = ""
    async for ev in runner.run_async(
        user_id="operator", session_id=session.id,
        new_message=Content(role="user", parts=[Part(text=TASK)]),
    ):
        who = ev.author or "?"
        if ev.content and ev.content.parts:
            for p in ev.content.parts:
                if p.text:
                    print(f"[{who}] {p.text.strip()[:300]}")
                    if who == "sloane_qa":
                        qa_text += p.text
    # verdict on QA [GATE] tag (authoritative). BLOCKED reasons / count
    # mismatches contain "fail" legitimately — substring would double-count.
    upper = qa_text.upper()
    passed = "[GATE] PASS" in upper or ("GATE PASS" in upper and "[GATE] FAIL" not in upper)
    print("\nSMOKE:", "PASS ✅" if passed else "FAIL ❌")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
