"""Run every product tribe DAG in sequence. Used by the 24/7 supervisor.

One process cycles through all tribes: jawatch → heimdall → avicenna → gebelin
→ chronos. Each tribe runs its lead→backend→qa DAG, reports PASS/FAIL, opens
issue/branch/PR/checks CI. Memory persists per tribe via GroupMemoryService
so agents learn across cycles.

ponytail: sequential, not parallel. Parallel tribes would hammer the 9router
LLM endpoint + GitHub API concurrently (rate limits). One-at-a-time is
simpler, cheaper, and CI status is unambiguous. Parallelize only if cycle
time becomes a real bottleneck.
"""
from __future__ import annotations
import sys

from agents.run_product_tribe import run
from agents.tribe_factory import PRODUCTS


def main() -> int:
    failures = []
    for name in PRODUCTS:
        print(f"\n=== tribe {name} ===", flush=True)
        try:
            joined = run(name)
            if "FAIL" in joined.upper():
                failures.append(name)
        except Exception as e:
            print(f"[{name}] ERROR: {e}", flush=True)
            failures.append(name)
    print(f"\n=== cycle done: {len(PRODUCTS)} tribes, {len(failures)} failed: {failures} ===", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
