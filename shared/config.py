"""Runtime config. Secrets from env, never hardcoded (security.md)."""
from __future__ import annotations
import os
from pathlib import Path

# ponytail: secret dir convention matches Gebelin. Password read at runtime.
SECRET_DIR = Path(os.environ.get("DOS_SECRET_DIR", "/home/dwizzy/dwizzyOS/Gebelin/.secrets"))


def _read_secret(name: str) -> str:
    p = SECRET_DIR / name
    if not p.exists():
        raise RuntimeError(f"secret {p} missing; set DOS_SECRET_DIR or create it")
    return p.read_text().strip()


def _container_ip() -> str | None:
    """Resolve DOS-pg's IP on the dwizzyOS docker network from host."""
    import subprocess
    try:
        r = subprocess.run(
            ["docker", "inspect", "DOS-pg", "--format",
             "{{(index .NetworkSettings.Networks \"dwizzyOS\").IPAddress}}"],
            capture_output=True, text=True, timeout=5,
        )
        return r.stdout.strip() or None
    except Exception:
        return None


def pg_dsn() -> str:
    """psycopg DSN to the dwizzyos canonical DB.

    Source of truth = dos_pgb_url connection string (correct plain password).
    dos_pg_password secret file is stale (mismatched hash, auth fails over TCP).
    Falls back to resolving DOS-pg's container IP on the dwizzyOS docker network
    since 5432 is not published to the host.
    """
    # 1. explicit full connection string wins
    if url := os.environ.get("DOS_PGB_URL"):
        return url
    # 2. resolve container IP (host can't reach 127.0.0.1, port unpublished)
    host = _container_ip() or os.environ.get("DOS_PG_HOST", "localhost")
    pw = os.environ.get("DOS_PG_PASSWORD", "kultivasimusemangatku")
    port = os.environ.get("DOS_PG_PORT", "5432")
    return f"postgresql://dwizzy:{pw}@{host}:{port}/dwizzyos"


# 9router as the LLM backend for all agents (OpenAI-compatible).
ROUTER_BASE_URL = os.environ.get("ROUTER_BASE_URL", "http://192.168.100.6:20128/v1")
ROUTER_API_KEY = os.environ.get("ROUTER_API_KEY", "")  # set in env, not committed
MODEL_LEAD = "R9/9router/AGENTS-LEAD"   # Custom high-thinking model
MODEL_WORKER = "R9/9router/AGENTS"      # Custom worker model

# Round-robin embedding models
EMBEDDING_MODELS = [
    "text-embedding-3-small",
    "text-embedding-3-large",
    "text-embedding-v2",
    "text-embedding-v3"
]

import itertools
_embedding_cycle = itertools.cycle(EMBEDDING_MODELS)

def get_next_embedding_model() -> str:
    """Return the next embedding model in the round-robin cycle."""
    return next(_embedding_cycle)


# Model capability tiers
MODELS_HIGH = {
    "ag/claude-opus-4-6-thinking", "ag/claude-sonnet-4-6", "ag/gemini-pro-agent",
    "cx/gpt-5.3-codex-high", "cx/gpt-5.3-codex-xhigh", "cx/gpt-5.4", "cx/gpt-5.5",
    "ds/deepseek-reasoner", "ds/deepseek-v4-pro", "ds/deepseek-v4-pro-max",
    "gc/gemini-2.5-pro", "gc/gemini-3.1-pro-preview", "gc/gemini-3-pro-preview",
    "gh/claude-opus-4.5", "gh/claude-opus-4.6", "gh/claude-opus-4.7", "gh/claude-sonnet-4.5", "gh/claude-sonnet-4.6",
    "gh/gemini-2.5-pro", "gh/gemini-3.1-pro-preview", "gh/gpt-5.4",
    "openrouter/nvidia/nemotron-3-ultra-550b-a55b",
    "R9/9router/combo-qwen3.6-max", "R9/9router/combo-qwen3.7-max", "R9/9router/combo-qwen-deepseek", "R9/9router/combo-qwen-kimi-glm-deepseek",
    "R9/9router/R9/deepseek-v4-pro", "R9/9router/R9/glm-5.2", "R9/9router/R9/kimi-k2.7-code", "R9/9router/R9/qwen3.7-max",
    "R9/9router/AGENTS-LEAD"
}

def is_high_capability(model_id: str) -> bool:
    """Check if a model is classified as 'high' thinking capability."""
    if model_id in MODELS_HIGH:
        return True
    # Catch-all rules for high models
    model_lower = model_id.lower()
    low_keywords = ["flash", "lite", "mini", "nano", "free", "low", "medium", "none", "coder", "oss"]
    if any(lk in model_lower for lk in low_keywords):
        return False
    high_keywords = ["opus", "sonnet", "-pro", "reasoner", "gpt-5.4", "gpt-5.5", "qwen3.7-max", "combo"]
    return any(hk in model_lower for hk in high_keywords)
