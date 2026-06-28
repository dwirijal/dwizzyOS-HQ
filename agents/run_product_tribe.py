"""Generic product tribe runner. Usage: python run_product_tribe.py <tribe_name>.

Runs the tribe DAG via ADK Runner + GroupMemoryService (memory stored so agents
learn across runs). Prints each agent's final text; checks QA for PASS.
"""
from __future__ import annotations
import sys

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part

from agents.tribe_factory import build_tribe, PRODUCTS
from shared.memory_service import GroupMemoryService


def run(name: str) -> str:
    cfg = PRODUCTS[name]
    root = build_tribe(name)
    app = f"tribe_{name}"
    print(f"[{name}] tribe DAG: {cfg.product} | repo={cfg.repo} | lang={cfg.lang}")
    print(f"[{name}] agents:", [a.name for a in root.sub_agents])

    sessions = InMemorySessionService()
    memory = GroupMemoryService()
    runner = Runner(agent=root, app_name=app,
                    session_service=sessions, memory_service=memory)

    import asyncio

    async def _run():
        s = await sessions.create_session(app_name=app, user_id="hq")
        texts = []
        async for ev in runner.run_async(
            user_id="hq", session_id=s.id,
            new_message=Content(role="user", parts=[Part(text=(
                f"Run the {name} tribe squad: {cfg.product}. "
                f"Open issue, wire CI, branch, push, PR, check CI. Report PASS/FAIL."))]),
        ):
            if ev.content and ev.content.parts:
                for p in ev.content.parts:
                    if p.text and p.text.strip():
                        print(f"[{getattr(ev,'author','?')}] {p.text.strip()[:400]}")
                        texts.append(p.text)
        return texts

    out = asyncio.run(_run())
    joined = " ".join(out)
    # ponytail: verdict on the QA [GATE] tag (authoritative), not a "FAIL"
    # substring — BLOCKED reasons legitimately contain "failed" and would
    # false-positive. No [GATE] = no QA verdict = FAIL (incomplete DAG).
    upper = joined.upper()
    passed = "[GATE] PASS" in upper or "GATE PASS" in upper
    failed = "[GATE] FAIL" in upper or "GATE FAIL" in upper
    verdict = "PASS ✅" if passed and not failed else "FAIL ❌"
    print(f"[{name}] SMOKE:", verdict)
    return joined


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "jawatch"
    if name not in PRODUCTS:
        print(f"unknown tribe '{name}'; known: {list(PRODUCTS)}")
        sys.exit(2)
    run(name)
