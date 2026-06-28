"""Run avicenna squad: lead->backend->qa, full GH flow. Prints each agent +
the opened PR URL. The squad proves it can drive issue->branch->PR->CI on
dwirijal/avicenna autonomously.
"""
from __future__ import annotations
import asyncio
import os
import sys

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part

from agents.avicenna_tribe import build_tribe_avicenna
from shared.config import ROUTER_API_KEY

TASK = (
    "avicenna squad task: wire Go CI (build + vet) for dwirijal/avicenna using "
    "full GitHub features: open issue, branch, commit/push, open PR, check CI. "
    "Branch name: ci/add-go-workflow."
)


async def main() -> int:
    if not (ROUTER_API_KEY or os.environ.get("OPENAI_API_KEY")):
        print("ERROR: set OPENAI_API_KEY", file=sys.stderr); return 2
    tribe = build_tribe_avicenna()
    sessions = InMemorySessionService()
    runner = Runner(agent=tribe, app_name="tribe_avicenna", session_service=sessions)
    session = await sessions.create_session(app_name="tribe_avicenna", user_id="operator")
    qa_text = ""
    async for ev in runner.run_async(
        user_id="operator", session_id=session.id,
        new_message=Content(role="user", parts=[Part(text=TASK)]),
    ):
        who = ev.author or "?"
        for p in (ev.content.parts if ev.content else []):
            if getattr(p, "text", None):
                print(f"[{who}] {p.text.strip()[:300]}")
                if who == "avicenna_qa":
                    qa_text += p.text
    passed = "PASS" in qa_text.upper() and "FAIL" not in qa_text.upper()
    print("\nAVICENNA SQUAD:", "PASS ✅" if passed else "FAIL ❌")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
