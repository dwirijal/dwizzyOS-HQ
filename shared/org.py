"""Org bootstrap: tribes, squads, chapters, guilds seeded into agent_groups.

Idempotent. Run once at startup. Maps the org structure to group rows so
GroupMemoryService RBAC applies. tribe-* groups are locked to tribe_lead +
squad_lead; chapter_*/guild_* writable by members.
"""
from __future__ import annotations
import psycopg

from shared.config import pg_dsn

# org: tribe -> squads; each squad has role -> agent_id
# Dynamic positions: a role key maps to whatever agent_id fills it this cycle;
# agents can swap roles across squads. 1 squad = 1 product feature (spec).
ORG: dict[str, dict[str, dict[str, str]]] = {
    # sloane = universal data ingestion. 3 squads: scraper/processor/store.
    "sloane": {
        "squad_scraper": {
            "lead": "sloane_lead",
            "backend": "sloane_scraper",
            "qa": "sloane_qa",
        },
        "squad_processor": {
            "lead": "sloane_lead",
            "backend": "sloane_processor",
            "qa": "sloane_qa",
        },
        "squad_store": {
            "lead": "sloane_lead",
            "backend": "sloane_store",
            "qa": "sloane_qa",
        },
    },
    "avicenna": {
        "squad_avicenna": {
            "lead": "avicenna_lead",
            "backend": "avicenna_backend_go",
            "qa": "avicenna_qa",
            "frontend": "avicenna_frontend",
        },
    },
    # jawatch = media catalog UI (Next.js+bun), consumes avicenna data.
    "jawatch": {
        "squad_catalog_ui": {
            "lead": "jawatch_lead",
            "frontend": "jawatch_frontend_next",
            "backend": "jawatch_bff",
            "qa": "jawatch_qa",
        },
    },
    # heimdall = auth/gateway/security.
    "heimdall": {
        "squad_auth_gateway": {
            "lead": "heimdall_lead",
            "backend": "heimdall_backend",
            "qa": "heimdall_qa",
            "devops": "heimdall_devops",
        },
    },
    # Gebelin = infra/DB ops (PG + Supabase + Neon free PG + Cloudflare speed).
    "gebelin": {
        "squad_infra": {
            "lead": "gebelin_lead",
            "devops": "gebelin_devops",
            "backend": "gebelin_backend",
            "qa": "gebelin_qa",
        },
    },
    # chronos = UI showing time/astronomy/weather data (sloane ingests it).
    "chronos": {
        "squad_timeseries_ui": {
            "lead": "chronos_lead",
            "frontend": "chronos_frontend",
            "backend": "chronos_bff",
            "qa": "chronos_qa",
        },
    },
}

CHAPTERS = ["backend", "qa", "frontend", "devops"]
GUILDS = ["web_perf", "cloudflare", "best_practice"]  # persona guilds (memory only)


def bootstrap_org(dsn: str | None = None) -> None:
    dsn = dsn or pg_dsn()
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        # chapters + guilds (org-wide)
        for ch in CHAPTERS:
            cur.execute(
                "INSERT INTO agent_groups (name, kind) VALUES (%s,'chapter') "
                "ON CONFLICT (name) DO NOTHING", (f"chapter_{ch}",))
        for g in GUILDS:
            cur.execute(
                "INSERT INTO agent_groups (name, kind) VALUES (%s,'guild') "
                "ON CONFLICT (name) DO NOTHING", (f"guild_{g}",))
        # tribes + squads + memberships
        for tribe, squads in ORG.items():
            cur.execute(
                "INSERT INTO agent_groups (name, kind) VALUES (%s,'tribe') "
                "ON CONFLICT (name) DO NOTHING", (f"tribe_{tribe}",))
            tribe_id = cur.execute(
                "SELECT id FROM agent_groups WHERE name=%s", (f"tribe_{tribe}",)).fetchone()[0]
            for squad, roles in squads.items():
                cur.execute(
                    "INSERT INTO agent_groups (name, kind, parent_id) VALUES (%s,'squad',%s) "
                    "ON CONFLICT (name) DO NOTHING", (squad, tribe_id))
                sq_id = cur.execute(
                    "SELECT id FROM agent_groups WHERE name=%s", (squad,)).fetchone()[0]
                for role, agent_id in roles.items():
                    is_lead = role == "lead"
                    role_in_squad = "squad_lead" if is_lead else "member"
                    cur.execute(
                        "INSERT INTO agent_memberships (agent_id, group_id, role) "
                        "VALUES (%s,%s,%s) ON CONFLICT (agent_id, group_id) DO NOTHING",
                        (agent_id, sq_id, role_in_squad))
                    # tribe membership: tribe_lead (distinct from squad_lead) can write tribe
                    # memory; members read via view. ponytail: tribe_lead RBAC per spec.
                    cur.execute(
                        "INSERT INTO agent_memberships (agent_id, group_id, role) "
                        "VALUES (%s,%s,%s) ON CONFLICT (agent_id, group_id) DO NOTHING",
                        (agent_id, tribe_id, "tribe_lead" if is_lead else "member"))
                    # chapter membership: first agent in a chapter becomes chapter_lead
                    # (1 per chapter), subsequent are members. Dynamic — whoever bootstraps
                    # first leads. ponytail: explicit lead election when chapters grow.
                    if role in CHAPTERS:
                        ch_id = cur.execute(
                            "SELECT id FROM agent_groups WHERE name=%s",
                            (f"chapter_{role}",)).fetchone()[0]
                        has_lead = cur.execute(
                            "SELECT 1 FROM agent_memberships WHERE group_id=%s AND role='chapter_lead'",
                            (ch_id,)).fetchone()
                        ch_role = "member" if has_lead else "chapter_lead"
                        cur.execute(
                            "INSERT INTO agent_memberships (agent_id, group_id, role) "
                            "VALUES (%s,%s,%s) ON CONFLICT (agent_id, group_id) DO NOTHING",
                            (agent_id, ch_id, ch_role))
        conn.commit()
