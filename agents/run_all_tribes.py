"""Run every product tribe DAG in sequence. Used by the 24/7 supervisor.

Cycles: factory tribes (jawatch/heimdall/gebelin/chronos) via run_product_tribe,
then legacy tribes (avicenna=go, sloane=python) via their own runners as
subprocesses. Each tribe: lead→backend→qa DAG, opens issue/branch/PR, checks CI.

Verdict = subprocess exit code (0=PASS), NOT a "FAIL" substring — BLOCKED
reasons legitimately contain "failed" and would false-positive. The factory
run() and legacy runners both exit 0 on PASS, 1 on FAIL.

ponytail: sequential, not parallel — parallel hammers the 9router LLM endpoint
+ GitHub API (rate limits). One-at-a-time is simpler, cheaper, CI unambiguous.
"""
from __future__ import annotations
import subprocess
import sys

from agents.run_product_tribe import run
from agents.tribe_factory import PRODUCTS

PY = sys.executable
# legacy tribes with own runners (not in factory PRODUCTS): (name, module)
LEGACY_TRIBES = [
    ("avicenna", "agents.run_avicenna"),  # Go data hub
    ("sloane", "agents.run_sloane"),      # python data pipeline
]


def _within_hours() -> bool:
    """Agents work 06:00-22:00 local. Outside → skip cycle, exit 0."""
    import time
    # tm_gmtoff-aware: localtime hour in system TZ.
    return 6 <= time.localtime().tm_hour < 22


def main() -> int:
    if not _within_hours():
        print("outside work hours (06-22) — skipping cycle", flush=True)
        return 0
    failures: list[str] = []
    # factory tribes (in-process)
    for name in PRODUCTS:
        print(f"\n=== tribe {name} ===", flush=True)
        try:
            joined = run(name)
            # verdict on [GATE] tag (run() prints its own SMOKE line); trust
            # absence of GATE-fail. Re-check here only for hard errors.
            if "[GATE] FAIL" in joined.upper() or "GATE FAIL" in joined.upper():
                failures.append(name)
        except Exception as e:
            print(f"[{name}] ERROR: {e}", flush=True)
            failures.append(name)
    # legacy tribes (subprocess — isolate their litellm/SystemExit state)
    for name, module in LEGACY_TRIBES:
        print(f"\n=== tribe {name} (subprocess) ===", flush=True)
        r = subprocess.run([PY, "-m", module], timeout=900)
        if r.returncode != 0:
            failures.append(name)
    total = len(PRODUCTS) + len(LEGACY_TRIBES)
    print(f"\n=== cycle done: {total} tribes, {len(failures)} failed: {failures} ===", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
