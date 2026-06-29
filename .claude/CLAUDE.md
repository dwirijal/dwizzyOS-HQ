# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repo Is

`dwizzyOS-HQ` is the **autonomous agent fleet control plane** for dwizzyOS. It is NOT a normal app — it is the orchestrator that builds and runs a company of AI agents ("tribes" of "squads") that build and maintain the other dwizzyOS products (avicenna, jawatch, heimdall, gebelin, chronos, sloane).

Two concerns coexist here:
1. **Agent control plane** (Python, Google ADK + LiteLLM) — the actual code.
2. **Documentation vault** — every action/decision/plan/issue is logged and auto-committed to GitHub.

## Commands

```bash
# Python env: ~/Projects/dwizzyOS/.venv-adk (Python 3.12, uv-managed). Use that interpreter, not system python.
PY=~/Projects/dwizzyOS/.venv-adk/bin/python

# Secrets (source FIRST — ROUTER_API_KEY, OPENAI_API_KEY, GH_TOKEN, DOS_PGB_URL). Gitignored, never commit.
source .secrets/env.sh

# PYTHONPATH must include the sloane sibling repo (tribe_sloane imports sloane.agents.tools).
# Always run from repo root.
cd ~/Projects/dwizzyOS/dwizzyOS-HQ
export PYTHONPATH=.:~/Projects/dwizzyOS

# Run a tribe smoke (DAG: lead→backend→qa). sloane = lead→scraper→processor→store→qa.
$PY -m agents.run_sloane
$PY -m agents.run_product_tribe jawatch     # factory tribe: heimdall|gebelin|chronos

# Run ALL tribes in sequence (24/7 supervisor cycle — gates on work hours 06-22 GMT+7, weekends 24h)
$PY -m agents.run_all_tribes

# Event-driven single-squad runner (PG LISTEN/NOTIFY; runs only the squad whose upstream event fired)
$PY -m agents.run_squad_on_event sloane

# Dashboard (read-only stdlib HTTP, 0.0.0.0:8485, per-route 10s cache)
$PY -m dashboard.server

# Vault logging (also auto-fired by .claude/hooks.json on Write/Edit)
~/dwizzyOS/dwizzyOS-vault/vault-log.sh note "what happened"
```

**Hard runtime prerequisites** (see memory `hq-runtime-recovery-2026-06-29`):
- **Cloudflare WARP must be connected** — the Supabase DB host is IPv6-only and the host ISP gives no IPv6. `warp-cli --accept-tos connect` (note: `--accept-tos` is a GLOBAL flag, goes BEFORE the subcommand). The 9router on localhost is split-tunneled and still reachable through WARP.
- **DB = Supabase project "gbrain"** (ref `uuszrqudpbenwcifdsbz`), NOT local Docker. `DOS_PGB_URL` in `.secrets/env.sh` points at the direct host. Migrations are applied via the Supabase MCP `execute_sql` tool (plain psycopg `ensure_schema` works too once connected).
- **LLM = 9router on localhost** (`http://localhost:20128/v1`), OpenAI-compatible, NOT Anthropic. Model IDs `HIGH` (lead) / `9r/9router/R9/glm-5.2` (worker) — `AGENTS`/`AGENTS-LEAD` are NOT registered on this 9router. Verify with `curl -H "Authorization: Bearer $ROUTER_API_KEY" http://localhost:20128/v1/models`.


There is **no test suite, no requirements.txt, no Makefile, no docker-compose here.** The Postgres/Valkey containers live in a sibling repo (`Gebelin`); this repo connects to them over the docker network. Python deps (google-adk, litellm, psycopg, pgvector) are expected pre-installed in the host env.

## Architecture

### Org model (data, not code): tribe → squad → role
A **tribe** owns a product; a **squad** owns one feature (1 feature = 1 squad = 1 pipeline); **roles** (lead/backend/qa/frontend/devops) are dynamic positions — an `agent_id` fills a role key this cycle and can swap next cycle. Defined as data in `shared/org.py` (`ORG` dict), mirrored as PG rows in `agent_groups`/`agent_memberships`. Hierarchy chain CTO→tribe_lead→squad_lead→member enforced in `shared/hierarchy.py` (`can_assign`); GitHub scope (one repo + branch prefix per squad) is structural via `shared/github_ops.py` closures.

### Agent DAGs (Google ADK `SequentialAgent`)
Each tribe is a `lead → backend → qa` (sloane adds scraper→processor→store) `SequentialAgent`. **Lazy activation**: 1 worker per squad + shared lead/qa, not lead+worker+qa per squad.
- `agents/tribe_factory.py` — one `build_product_tribe(TribeConfig)` replaces N copy-paste files; `PRODUCTS` dict configures jawatch/heimdall/gebelin/chronos. Closures bind `gh_*` tools to each product's `cwd`.
- `agents/tribe_sloane.py`, `agents/avicenna_tribe.py` — legacy tribes with own DAG shapes (sloane: 5-agent ingestion pipeline).
- Every squad MUST drive the full GitHub flow: issue → branch → commit → push → PR → CI. Agents never bypass this gate.

### Verdict protocol: parse `[GATE]`, never substring-match "FAIL"
QA agents end their turn with exactly one terminal tagged line: `[GATE] pass ci` / `[GATE] fail ci`. The supervisor (`run_all_tribes`, `run_sloane`) parses this **tag**, NOT a "FAIL" substring — BLOCKED reasons and count-mismatches legitimately contain "failed" and would false-positive. **No `[GATE]` line = FAIL (incomplete DAG).** This is the single most common bug source when modifying runners.

### Machine-language comms (`shared/souls.py`)
Every agent ends its turn with one tagged terminal line (Leads: `PLAN`/`HANDOFF`; workers: `DELIVERABLE`/`STATUS`; QA: `GATE`). No prose after the terminal tag — downstream agents parse the last line. `soul_block(role)` composes SOUL+COMMS; chapter standards (`shared/chapters.py`: `CHAPTER_BACKEND`/`CHAPTER_QA`/`CHAPTER_FRONTEND`) are prepended by the caller.

### LLM backend: 9router (OpenAI-compatible), not Anthropic
All agents route through `ROUTER_BASE_URL` (a self-hosted 9router) via `LiteLlm(model=f"openai/{id}")`. Models: `MODEL_LEAD="AGENTS-LEAD"` (high-capability, gated by `is_high_capability()` — leads MUST use a high model or `_llm()` raises), `MODEL_WORKER="AGENTS"`. Round-robin embeddings across 4 models (`get_next_embedding_model()`). Per-group rate limiting installed via `shared/model_groups.install_hook()` (9router smart_toy groups share 10 req/min — call it at the start of every runner).

### Memory: `GroupMemoryService` (`shared/memory_service.py`)
Custom ADK `BaseMemoryService` over Postgres + pgvector. **Group-scoped RBAC**: `app_name` = group name (e.g. `squad-sloane`, `chapter-qa`, `tribe-sloane`). Tribe memory is writable only by `tribe_lead`/`squad_lead`; squad/chapter memory writable by all members. Reads go through the `v_memory_readable` view. Embeddings optional (vector column nullable; keyword ILIKE search until wired).

### Event bus (`shared/event_bus.py`)
PG `LISTEN/NOTIFY` on one `agent_events` channel carrying JSON — zero deps, sub-second agent-to-agent chaining. Scraper emits `sloane.scrape.done` → only the processor squad wakes (no full-DAG re-run). Replaces cron polling. Ceiling ~1k events/sec.

### DB
Supabase project "gbrain" (ref `uuszrqudpbenwcifdsbz`, PG17 + pgvector), reached over Cloudflare WARP (the direct `db.*.supabase.co` host is IPv6-only; host ISP has no IPv6). `pg_dsn()` checks `DOS_PGB_URL` first (set in `.secrets/env.sh`). Schema evolved across `shared/migrations/00*.sql` (canonical entities → RBAC → three-layer raw/canonical/units → sloane squads → org leads → tasks/budgets → goals/rules → KPIs/schedule/reports → sprints/releases). Org memberships (tribes/squads/chapters/roles) are seeded by `shared/org.py` `bootstrap_org()`, not by a migration.

### Dashboard (`dashboard/`)
Stdlib `ThreadingHTTPServer`, read-only PG queries, multi-page (`/`, `/cto`, `/agent/<id>`, `/squad/<id>`, `/tribe/<name>`, `/chapter/<name>`). Per-route 10s render cache to absorb docker-bridge PG handshake lag. No auth — LAN-internal only.

## Conventions Specific To This Codebase

- **`ponytail:` comments** mark deliberate simplifications/YAGNI cuts with the named ceiling and upgrade path (26+ instances). Respect them — do not "fix" a ponytail cut by adding the abstraction it deliberately skipped. Example: `ponytail: sequential, not parallel — parallel hammers the 9router endpoint`.
- **Lazy senior developer ethos**: deletion over addition, one-liner wins, no speculative abstraction, no scaffolding "for later". `shared/chapters.py` CHAPTER_BACKEND codifies this as org standard (functions <50 lines, files <800 lines, nesting ≤4, YAGNI).
- **Secrets**: `.secrets/` is gitignored (`env.sh`, `systemd.env` hold `ROUTER_API_KEY` + `GH_TOKEN`). Read at runtime from env or secret files (`shared/config.py` `_read_secret`); never hardcode, never commit. `source .secrets/env.sh` before running anything.
- **`gh` CLI** must be authed on the host (`gh auth login`) — `github_ops.py` shells out to `gh` + `git`, not a library.
- Repo paths are absolute under `/home/dwizzy/dwizzyOS/<product>` (e.g. `/home/dwizzy/dwizzyOS/jawatch`); `cwd` in `TribeConfig` points each tribe's git ops at the right sibling checkout.

## Documentation Vault Rules (this is the central vault)

Every action, decision, plan, issue, and change MUST be documented here. Auto-logging fires from `.claude/hooks.json` (PostToolUse on Write/Edit → `vault-log.sh file_op`; Stop → auto-commit+push to `main`). When in doubt, document it.

- **Daily notes** → `daily/YYYY-MM-DD.md`
- **Issues** → `issues/<descriptive>.md`
- **Plans** → `plans/` before writing code
- **System/infra** → `system/`
- **Project docs** → `projects/<project-name>/`

Commit convention: `docs(daily|issue|plan|system|project): ...`. The watcher (`vault-watchd.sh`) auto-commits and pushes to https://github.com/dwirijal/dwizzyOS-HQ.
