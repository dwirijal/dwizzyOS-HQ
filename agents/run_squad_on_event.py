"""Bus-driven squad runner: run ONE squad when its trigger event fires.

Unlike run_sloane (whole SequentialAgent DAG in fixed order), this listens on
the event bus and runs only the squad whose upstream event arrived — true
event-driven autonomy, no cron, no full-DAG re-run.

Example: a new source scraped out-of-band emits sloane.scrape.done -> only
the processor squad runs (enrich), not lead+scraper+store. Faster, cheaper.

Usage:
  python run_squad_on_event.py sloane   # listens for sloane.* events, runs
                                         # the matching squad agent per the chain.

ponytail: 1 process per tribe. The process owns a long-lived PG LISTEN conn
+ an ADK Runner per squad. Add a supervisor (systemd/pm2) for 24/7 restarts.
"""
from __future__ import annotations
import asyncio
import threading

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part

from shared.event_bus import listen, on, emit
from shared.memory_service import GroupMemoryService
from agents.tribe_sloane import build_tribe_sloane

# event -> (squad_agent_name, task_prompt)
SLOANE_SQUADS = {
    "sloane.scrape.done": ("sloane_processor",
        "Processor squad: enrich pending canonicals with MAL IDs. "
        "Call enrich_pending_canonicals limit=5. Then emit sloane.enrich.done."),
    "sloane.enrich.done": ("sloane_store",
        "Store squad: run DB governance. Call store_health_check. "
        "Report lean flag. Then emit sloane.store.done with the result."),
}


def _run_squad(tribe_app: str, agent_name: str, prompt: str, payload: dict) -> None:
    """Run one squad agent with the event payload as context. Sync wrapper."""
    async def _run():
        tribe = build_tribe_sloane()
        agent = next(a for a in tribe.sub_agents if a.name == agent_name)
        sessions = InMemorySessionService()
        memory = GroupMemoryService()
        runner = Runner(agent=agent, app_name=tribe_app,
                        session_service=sessions, memory_service=memory)
        s = await sessions.create_session(app_name=tribe_app, user_id="bus")
        text = f"{prompt} Context: {payload}"
        async for ev in runner.run_async(
            user_id="bus", session_id=s.id,
            new_message=Content(role="user", parts=[Part(text=text)]),
        ):
            if ev.content and ev.content.parts:
                for p in ev.content.parts:
                    if p.text and p.text.strip():
                        print(f"[{agent_name}] {p.text.strip()[:300]}")
    try:
        asyncio.run(_run())
    except Exception as e:
        print(f"[{agent_name}] error: {e}", flush=True)


def run_tribe_on_bus(tribe: str = "sloane") -> None:
    """Listen for tribe events, run the matching squad, emit downstream events."""
    squads = SLOANE_SQUADS if tribe == "sloane" else {}
    if not squads:
        raise ValueError(f"no bus wiring for tribe '{tribe}' yet")

    def handler(event: str, payload: dict) -> None:
        if event not in squads:
            return
        agent_name, prompt = squads[event]
        print(f"[bus] {event} -> {agent_name}", flush=True)
        _run_squad(f"tribe_{tribe}", agent_name, prompt, payload)
        # the agent itself emits downstream events via its tools/instruction;
        # if it didn't, emit a generic completion so chains don't stall.
        downstream = {"sloane.scrape.done": "sloane.enrich.done",
                      "sloane.enrich.done": "sloane.store.done"}.get(event)
        if downstream:
            emit(downstream, {"triggered_by": event, **payload})

    # start listener in foreground (blocks)
    print(f"[bus] {tribe} listening for: {list(squads)}")
    listen(list(squads), handler)


if __name__ == "__main__":
    import sys
    tribe = sys.argv[1] if len(sys.argv) > 1 else "sloane"
    run_tribe_on_bus(tribe)
