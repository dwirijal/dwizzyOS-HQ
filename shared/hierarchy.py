"""Org hierarchy + assignment enforcement + GitHub scope.

Chain: CTO -> tribe_lead -> squad_lead -> member.
  - CTO        assigns to tribe_lead OR chapter_lead.
  - tribe_lead assigns to squad_lead ONLY (within their tribe).
  - squad_lead assigns to member ONLY (within their squad).
  - member     cannot assign (leaf).

GitHub scope: a squad touches ONLY its own repo + branch prefix. The gh ops
tools (shared/github_ops.py) are already bound per-product via tribe_factory
closures, so the scope is structural. This module exposes the policy as data so
the dashboard + any new tool can check it.

No guilds — removed per operator decision (no benefit in an agents company).
"""
from __future__ import annotations

# repo per tribe/squad (GitHub scope). branch prefix = squad name.
TRIBE_REPO: dict[str, str] = {
    "sloane": "dwirijal/sloane",   # ingestion libs (rebahin/oploverz) live under sloane/
    "avicenna": "dwirijal/avicenna",
    "jawatch": "dwirijal/Jawatch",
    "heimdall": "dwirijal/heimdall",
    "gebelin": "dwirijal/Gebelin",
    "chronos": "dwirijal/chronos",
}

# squad -> tribe (from shared/org.ORG; duplicated tiny map to avoid import cycle
# at tool-use sites that don't want ADK loaded). Keep in sync with org.py.
SQUAD_TRIBE: dict[str, str] = {
    "squad_scraper": "sloane", "squad_processor": "sloane", "squad_store": "sloane",
    "squad_avicenna": "avicenna",
    "squad_catalog_ui": "jawatch",
    "squad_auth_gateway": "heimdall",
    "squad_infra": "gebelin",
    "squad_timeseries_ui": "chronos",
}

CTO = "dwizzy_cto"


def roles_of(agent_id: str, conn) -> set[str]:
    """All hierarchy roles an agent holds (an agent may be both tribe_lead + squad_lead)."""
    with conn.cursor() as cur:
        cur.execute("SELECT role FROM agent_memberships WHERE agent_id=%s", (agent_id,))
        return {r[0] for r in cur.fetchall()} or {"member"}


def role_of(agent_id: str, conn) -> str:
    """Highest hierarchy role (for display). cto>tribe_lead>chapter_lead>squad_lead>member."""
    order = {"cto": 0, "tribe_lead": 1, "chapter_lead": 2, "squad_lead": 3, "member": 4}
    rs = roles_of(agent_id, conn)
    return min(rs, key=lambda r: order.get(r, 9)) if rs else "member"


def can_assign(assigner: str, assignee: str, conn) -> tuple[bool, str]:
    """Enforce the chain. Assigner may hold several roles; try each in order.

    CTO->tribe_lead|chapter_lead; tribe_lead->squad_lead (same tribe);
    squad_lead->member (same squad). One hop only.
    """
    ar = roles_of(assigner, conn)
    br = roles_of(assignee, conn)
    # CTO
    if "cto" in ar and (br & {"tribe_lead", "chapter_lead"}):
        return True, "ok"
    # tribe_lead -> squad_lead (same tribe)
    if "tribe_lead" in ar and "squad_lead" in br:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM agent_memberships a JOIN agent_groups ga ON ga.id=a.group_id "
                "JOIN agent_memberships b ON b.group_id=a.group_id "
                "WHERE a.agent_id=%s AND a.role='tribe_lead' AND b.agent_id=%s "
                "AND b.role='squad_lead' AND ga.kind='tribe' LIMIT 1", (assigner, assignee))
            if cur.fetchone():
                return True, "ok"
            return False, "tribe_lead can only assign squad_leads in the same tribe"
    # squad_lead -> member (same squad)
    if "squad_lead" in ar and "member" in br:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM agent_memberships a JOIN agent_groups ga ON ga.id=a.group_id "
                "JOIN agent_memberships b ON b.group_id=a.group_id "
                "WHERE a.agent_id=%s AND a.role='squad_lead' AND b.agent_id=%s "
                "AND b.role='member' AND ga.kind='squad' LIMIT 1", (assigner, assignee))
            if cur.fetchone():
                return True, "ok"
            return False, "squad_lead can only assign members in the same squad"
    return False, f"{role_of(assigner,conn)} cannot assign {role_of(assignee,conn)}"


def report_recipient(reporter_role: str) -> str:
    """Who a role reports up to."""
    return {"member": "squad_lead", "squad_lead": "tribe_lead",
            "chapter_lead": CTO, "tribe_lead": CTO}.get(reporter_role, CTO)


def github_scope(squad: str) -> dict:
    """The repo + branch-prefix a squad is allowed to touch."""
    tribe = SQUAD_TRIBE.get(squad, "")
    return {"repo": TRIBE_REPO.get(tribe, ""), "branch_prefix": f"{squad}/", "tribe": tribe}


def assign_task(assigner: str, assignee: str, title: str, tribe: str,
                squad: str, conn) -> dict:
    """Insert a task honoring the hierarchy. Raises ValueError on policy breach."""
    ok, reason = can_assign(assigner, assignee, conn)
    if not ok:
        raise ValueError(f"assignment denied: {reason}")
    ar = roles_of(assigner, conn)
    # pick the most specific assigning role that fits
    if "squad_lead" in ar:
        scope = "squad_lead->member"
    elif "tribe_lead" in ar:
        scope = "tribe_lead->squad_lead"
    elif "cto" in ar:
        scope = "cto->lead"
    else:
        scope = "unknown"
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO tasks (title,tribe,squad,assignee,assigner_id,assignment_scope,status) "
            "VALUES (%s,%s,%s,%s,%s,%s,'todo') RETURNING id",
            (title, tribe, squad, assignee, assigner, scope))
        tid = cur.fetchone()[0]
        conn.commit()
    return {"task_id": tid, "assigner": assigner, "assignee": assignee, "scope": scope}
