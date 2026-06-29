"""Per-group rate limiting for 9router smart_toy models.

The 9router smart_toy models (combo-*, R9/*) share a 10 req/min limit PER
GROUP — not per model. Concurrent tribes hitting models in the same group
saturate it → 429/reset failures. This module maps a model id to its group
and applies a blocking sliding-window throttle so agents self-pace.

Ag/gh/gc/ds/cx models are NOT rate-limited at this tier (treated as separate
groups with no enforced cap); only smart_toy groups get the 10/min bucket.

Wired as a litellm pre_api_call hook → applies to every LiteLlm call.
"""
from __future__ import annotations
import time
import threading
from collections import deque

# Rate-limited groups and their cap (req/min). smart_toy = 10 req/min shared.
GROUP_CAPS: dict[str, int] = {
    "9router-combo": 10,
    "9router-R9": 10,
    "AGENTS": 10,  # treat custom AGENTS/AGENTS-LEAD as a smart_toy group too (unknown tier → safe)
}

# model id (lowercased) -> group. Match by prefix.
def group_of(model: str) -> str | None:
    m = (model or "").lower()
    # strip the openai/ wrapper litellm adds
    m = m.removeprefix("openai/")
    if m.startswith("9router/combo-") or m.startswith("r9/9router/combo-"):
        return "9router-combo"
    if m.startswith("9router/r9/") or m.startswith("r9/9router/r9/") or m.startswith("r9/9router/r9/"):
        return "9router-R9"
    if m in ("agents", "agents-lead"):
        return "AGENTS"
    return None  # ag/gh/gc/ds/cx → no enforced cap


class _Bucket:
    """Sliding-window counter. Blocks the calling thread until a slot frees."""
    def __init__(self, cap: int, window: float = 60.0):
        self.cap = cap
        self.window = window
        self.hits: deque[float] = deque()
        self.lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self.lock:
                now = time.monotonic()
                # evict hits outside the window
                while self.hits and now - self.hits[0] >= self.window:
                    self.hits.popleft()
                if len(self.hits) < self.cap:
                    self.hits.append(now)
                    return
                # wait until the oldest hit ages out
                wait = self.window - (now - self.hits[0]) + 0.05
            if wait > 0:
                time.sleep(min(wait, self.window))


_BUCKETS: dict[str, _Bucket] = {}


def _bucket(group: str) -> _Bucket:
    if group not in _BUCKETS:
        cap = GROUP_CAPS.get(group, 10)
        _BUCKETS[group] = _Bucket(cap)
    return _BUCKETS[group]


def throttle(model: str) -> None:
    """Block until the model's group has a free slot. No-op for uncapped groups."""
    g = group_of(model)
    if g is None:
        return
    _bucket(g).acquire()


def install_hook() -> None:
    """Register a litellm pre_api_call hook that throttles before each request.

    Idempotent: safe to call multiple times (guards against duplicate hooks).
    ponytail: litellm's pre_api_call hook receives (model, messages, kwargs,
    ...) signatures that drift across versions; we read model from kwargs to
    avoid coupling to the exact arg list.
    """
    import litellm
    try:
        # litellm >=1.x: pre_api_call_hooks list
        existing = getattr(litellm, "pre_api_call_hooks", None) or []
        if any(getattr(h, "_dwizzy_throttle", False) for h in existing):
            return
    except Exception:
        existing = []

    def _hook(*args, **kwargs):
        # model id is in kwargs["model"] or args[0]
        model = kwargs.get("model") or (args[0] if args else "")
        # litellm passes the provider-prefixed form, e.g. "openai/AGENTS-LEAD"
        throttle(str(model))

    _hook._dwizzy_throttle = True  # type: ignore[attr-defined]

    try:
        litellm.pre_api_call_hooks = list(existing) + [_hook]
    except Exception:
        # older litellm: input_callbacks
        try:
            litellm.input_callback = list(getattr(litellm, "input_callback", []) or []) + [_hook]
        except Exception:
            pass
