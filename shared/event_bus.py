"""Event bus for agent-to-agent triggering. PG LISTEN/NOTIFY, zero dep.

Replaces cron polling with sub-second event chaining. An agent finishes a
step -> emit(event, payload) -> PG NOTIFY -> listeners wake the next agent.

Spec (user): "lead squad sloane processing dipanggil ketika squad scrapper
selesai scrape". This wires exactly that: scraper emits sloane.scrape.done,
processor's hook wakes on it.

Cross-tribe (sloane->avicella) works because all agents share one PG.
Intra-agent hooks could also use ADK after_agent_callback, but the bus is
the single primitive for both (no special-casing).

Usage:
  emit("sloane.scrape.done", {"raw_ids": [1,2,3], "source": "oploverz"})
  # in a listener process:
  listen(["sloane.scrape.done"], on_event)   # blocks, calls on_event(name, payload)

ponytail: one NOTIFY channel "agent_events" carrying JSON. A separate
dispatch table maps event names -> (tribe, squad, agent, hook) tuples.
No message queue, no Redis — PG is already our store. Scale ceiling: ~1k
events/sec; switch to Redis Streams if a tribe ever exceeds that.
"""
from __future__ import annotations
import json
import os
import select
import threading
from typing import Callable

import psycopg

from shared.config import pg_dsn

CHANNEL = "agent_events"

# event_name -> list of (tribe, squad, agent, hook) listeners.
# Register via on(). Dispatched by the listener loop.
_LISTENERS: dict[str, list[tuple[str, str, str, Callable]]] = {}


def emit(event: str, payload: dict, dsn: str | None = None) -> None:
    """Publish an event. Non-blocking; wakes any LISTENing process."""
    dsn = dsn or pg_dsn()
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT pg_notify(%s, %s)",
            (CHANNEL, json.dumps({"event": event, "payload": payload})),
        )
        conn.commit()


def on(event: str, tribe: str, squad: str, agent: str, hook: Callable) -> None:
    """Register a listener. hook(event, payload) called when event fires."""
    _LISTENERS.setdefault(event, []).append((tribe, squad, agent, hook))


def listen(events: list[str] | None = None,
           handler: Callable[[str, dict], None] | None = None,
           dsn: str | None = None) -> None:
    """Block on PG LISTEN, dispatch events.

    If handler given: dispatch matching events to it. Additionally, ALL events
    (matching or not) are dispatched to on()-registered listeners via _dispatch,
    so callers can use either pattern. Runs forever.
    """
    dsn = dsn or pg_dsn()
    conn = psycopg.connect(dsn, autocommit=True)

    def _on_notify(notify):
        try:
            msg = json.loads(notify.payload)
            name, payload = msg["event"], msg["payload"]
            _dispatch(name, payload)  # always dispatch to on() listeners
            if handler and (events is None or name in events):
                handler(name, payload)
        except Exception:
            pass  # malformed payload: drop, keep listening

    conn.add_notify_handler(_on_notify)
    conn.execute(f"LISTEN {CHANNEL}")
    while True:
        try:
            conn.execute("SELECT 1")  # drain any queued NOTIFY
            select.select([], [], [], 0.5)  # idle between polls
        except Exception:
            break


def _dispatch(name: str, payload: dict) -> None:
    """Dispatch to all registered in-process listeners for an event."""
    for tribe, squad, agent, hook in _LISTENERS.get(name, []):
        try:
            hook(name, payload)
        except Exception:
            pass  # one listener failing must not break others


# --- built-in wiring (sloane chain + lead delegation + cross-cutting) ---
# Two patterns: (a) pipeline chain (squad.squad.done -> next squad),
# (b) lead.task.<role> -> a member of that role in the lead's squad/chapter.
# Leads delegate via emit("lead.task.<role>", {...}) -> the member filling that
# role wakes. Chapter leads can fan out cross-tribe the same way.
# ponytail: hooks are no-ops until real runner functions are wired; the table
# documents the contract. run_* register real callables.
SLOANE_CHAIN = [
    # pipeline chain
    ("sloane.scrape.done", "sloane", "squad_processor", "sloane_processor"),
    ("sloane.enrich.done", "sloane", "squad_store", "sloane_store"),
    ("sloane.store.lean", "avicenna", "squad_avicenna", "avicenna_lead"),
    # lead -> member delegation (squad lead hands a task to a role)
    ("sloane.lead.task.backend", "sloane", "squad_scraper", "sloane_scraper"),
    ("sloane.lead.task.qa", "sloane", "squad_store", "sloane_qa"),
    # cross-cutting (chapter/guild scope, fan-out)
    ("pr.opened", "*", "chapter_qa", "qa_agent"),
    ("ci.red", "*", "*", "squad_lead"),
    ("budget.80pct", "*", "chapter_devops", "gebelin_devops"),
]


if __name__ == "__main__":
    # self-check: emit/listen round-trip on real PG
    import time
    got = []
    def h(name, payload):
        got.append((name, payload))
    t = threading.Thread(target=listen, args=(["test.ping"], h), daemon=True)
    t.start()
    time.sleep(1.0)  # let LISTEN register
    emit("test.ping", {"v": 1})
    for _ in range(30):  # wait up to 3s for delivery
        if got:
            break
        time.sleep(0.1)
    assert got == [("test.ping", {"v": 1})], f"round-trip failed: {got}"
    print("event_bus self-check OK")
