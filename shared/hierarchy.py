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
    """Who a role reports up to (single role passed)."""
    return {"member": "squad_lead", "squad_lead": "tribe_lead",
            "chapter_lead": CTO, "tribe_lead": CTO}.get(reporter_role, CTO)


def report_recipient_for(agent: str, conn) -> str:
    """Who an agent reports to, considering ALL its roles. A squad member (or
    squad_lead) reports up the squad line (squad_lead->tribe_lead->CTO).
    A pure chapter_lead (no squad role) reports straight to CTO. Squad line
    takes precedence: work happens in squads, chapters are cross-cutting."""
    rs = roles_of(agent, conn)
    if "tribe_lead" in rs:
        return CTO
    if "squad_lead" in rs:
        return "tribe_lead"  # tribe_lead agent_id resolved by caller? No—return role, map needed
    if "member" in rs:
        return "squad_lead"
    if "chapter_lead" in rs:
        return CTO
    return CTO


def github_scope(squad: str) -> dict:
    """The repo + branch-prefix a squad is allowed to touch."""
    tribe = SQUAD_TRIBE.get(squad, "")
    return {"repo": TRIBE_REPO.get(tribe, ""), "branch_prefix": f"{squad}/", "tribe": tribe}


def can_deploy_to_prod(agent: str, conn) -> tuple[bool, str]:
    """Production deploy is TRIBE_LEAD only. Devops prepares, tribe_lead ships."""
    rs = roles_of(agent, conn)
    if "tribe_lead" in rs:
        return True, "ok"
    return False, "production deploy is tribe_lead only"


def can_use_credential(agent: str, cred: str, conn) -> tuple[bool, str]:
    """An agent may use a tool/credential only if its expertise (registry skills)
    matches the cred's domain. Enforces 'tools sesuai keahlianannya'.
    """
    from shared.agent_registry import agent_meta
    meta = agent_meta(agent)
    skills = set(meta["skills"])
    role = meta["role"]
    # map credential domains -> required skill/role keywords
    domain_skill = {
        "github": {"github-flow", "ci-wiring", "planning", "issue-authoring"},
        "supabase": {"db-governance", "infra", "bff"},
        "cloudflare": {"infra", "cloudflare-tunnel", "docker-compose"},
        "vercel": {"nextjs", "ui", "ui", "infra"},
        "pg": {"db-governance", "infra", "enrichment"},
        "jikan": {"enrichment", "mal-id-resolve"},
        "openai": {"planning", "enrichment", "quality-gate"},
    }
    required = domain_skill.get(cred, set())
    if not required:
        return True, "ok"  # unknown cred domain = allow (no policy yet)
    if skills & required:
        return True, "ok"
    return False, f"{agent} (role {role}) lacks expertise for credential '{cred}': needs one of {required}"


def _resolve_supervisor(reporter: str, conn) -> str:
    """Resolve the concrete agent_id the reporter reports to.

    - squad member -> squad_lead of that squad
    - squad_lead   -> tribe_lead of that squad's tribe
    - tribe_lead / chapter_lead -> CTO
    Squad line takes precedence over chapter line.
    """
    rs = roles_of(reporter, conn)
    if "tribe_lead" in rs or "chapter_lead" in rs and "squad_lead" not in rs and "member" not in rs:
        return CTO
    with conn.cursor() as cur:
        if "squad_lead" in rs:
            # find the tribe of a squad this agent leads, then its tribe_lead
            cur.execute(
                "SELECT tl.agent_id FROM agent_memberships me "
                "JOIN agent_groups sq ON sq.id=me.group_id AND sq.kind='squad' AND me.role='squad_lead' "
                "JOIN agent_memberships sqm ON sqm.group_id=sq.parent_id "
                "JOIN agent_memberships tl ON tl.group_id=sqm.group_id AND tl.role='tribe_lead' "
                "WHERE me.agent_id=%s LIMIT 1", (reporter,))
            r = cur.fetchone()
            if r:
                return r[0]
        if "member" in rs:
            # find squad_lead of a squad this agent is a member of
            cur.execute(
                "SELECT sl.agent_id FROM agent_memberships me "
                "JOIN agent_groups sq ON sq.id=me.group_id AND sq.kind='squad' AND me.role='member' "
                "JOIN agent_memberships sl ON sl.group_id=sq.id AND sl.role='squad_lead' "
                "WHERE me.agent_id=%s LIMIT 1", (reporter,))
            r = cur.fetchone()
            if r:
                return r[0]
    return CTO


def file_report(reporter: str, report_type: str, content: str, conn) -> dict:
    """File a report up the chain to the reporter's concrete supervisor agent."""
    recipient = _resolve_supervisor(reporter, conn)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO reports (reporter, recipient, report_type, content) "
            "VALUES (%s,%s,%s,%s) RETURNING id", (reporter, recipient, report_type, content))
        rid = cur.fetchone()[0]
        conn.commit()
    return {"report_id": rid, "reporter": reporter, "recipient": recipient}


def ship_release(tribe: str, version: str, stage: str, released_by: str, conn) -> dict:
    """Mark a release shipped. Enforces tribe_lead-only for production."""
    if stage == "production":
        ok, reason = can_deploy_to_prod(released_by, conn)
        if not ok:
            raise ValueError(f"release denied: {reason}")
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE releases SET status='shipped', released_by=%s WHERE tribe=%s AND version=%s AND stage=%s "
            "RETURNING id", (released_by, tribe, version, stage))
        r = cur.fetchone()
        conn.commit()
    return {"shipped": bool(r), "tribe": tribe, "version": version, "stage": stage}


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
