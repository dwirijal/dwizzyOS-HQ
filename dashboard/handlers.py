"""Dashboard route handlers — render HTML for each page.

Routes: / (control room), /agent/<id> (cubicle), /tribe/<name>, /chapter/<name>.
Single PG connection per render (closes over caller's conn). Stdlib only.
"""
from __future__ import annotations
import html

from shared.org import ORG
from shared.souls import SOULS, soul_block
from shared.agent_registry import agent_meta, REGISTRY
from dashboard.styles import CSS


def _q(conn, sql, args=None):
    with conn.cursor() as cur:
        cur.execute(sql, args or ())
        return cur.fetchall()


def _esc(s) -> str:
    return html.escape(str(s) if s is not None else "")


# --- online detection: agent ran in last cycle? ---
def _online_agents(conn) -> set[str]:
    """Agents whose agent_memory was written in the last 20 min = 'at desk'."""
    try:
        rows = _q(conn, "SELECT DISTINCT author FROM agent_memory "
                        "WHERE created_at > now() - interval '20 minutes'")
        return {r[0] for r in rows}
    except Exception:
        return set()


# === CONTROL ROOM (/) ===
def render_home(conn) -> str:
    online = _online_agents(conn)
    org = _render_org_tree(conn, online)
    kanban = _render_kanban(conn)
    budget = _render_budgets(conn)
    dash = _render_metrics(conn)
    return f"""<!doctype html><html><head><meta charset=utf-8><title>dwizzyOS-HQ</title>
<style>{CSS}</style></head><body>
<header><h1>🏢 dwizzyOS-HQ</h1><nav><a href="/">Control Room</a></nav>
<div class="sub">CompanyOS · Spotify-tribe · live PG read</div></header>
<div class="wrap">
<div class="grid">
  <div class="panel"><h2>Org Structure</h2>{org}</div>
  <div class="panel"><h2>Dashboard</h2>{dash}</div>
</div>
<div class="panel" style="margin-top:20px"><h2>Kanban Board</h2>{kanban}</div>
<div class="panel" style="margin-top:20px"><h2>Budgets</h2>{budget}</div>
</div></body></html>"""


def _render_org_tree(conn, online) -> str:
    out = []
    for tribe, squads in ORG.items():
        out.append(f'<div class="tree-node tribe">▸ <a href="/tribe/{tribe}">{_esc(tribe)}</a></div>')
        tg = _q(conn, "SELECT text,status FROM goals WHERE scope='tribe' AND owner=%s AND status='active'", (tribe,))
        for text, status in tg:
            out.append(f'<div class="goal {"done" if status=="done" else ""}" style="margin-left:8px;font-size:11px">🎯 {_esc(text)}</div>')
        for squad, roles in squads.items():
            out.append(f'<div class="tree-node squad">▸ <a href="/tribe/{tribe}#{_esc(squad)}">{_esc(squad)}</a></div>')
            sg = _q(conn, "SELECT text,status FROM goals WHERE scope='squad' AND owner=%s AND status='active'", (squad,))
            for text, status in sg:
                out.append(f'<div class="goal {"done" if status=="done" else ""}" style="margin-left:24px;font-size:11px">🎯 {_esc(text)}</div>')
            for role, agent_id in roles.items():
                on = "on" if agent_id in online else "off"
                out.append(f'<div class="tree-node agent"><span class="dot {on}"></span>'
                           f'<a href="/agent/{agent_id}">{_esc(agent_id)}</a> '
                           f'<span class="badge role-{role}">{role}</span></div>')
    return "".join(out)


def _render_kanban(conn) -> str:
    cols = [("todo", "To Do"), ("doing", "Doing"), ("review", "Review"), ("done", "Done")]
    tasks = _q(conn, "SELECT id,title,tribe,squad,assignee,status,gh_pr_url FROM tasks ORDER BY priority DESC, id")
    by = {}
    for t in tasks:
        by.setdefault(t[5], []).append(t)
    out = ['<div class="kanban">']
    for status, label in cols:
        items = by.get(status, [])
        out.append(f'<div class="kanban-col"><h3 class="{status}">{label} ({len(items)})</h3>')
        for tid, title, tribe, squad, assignee, st, pr in items:
            pr_link = f'<br><a href="{_esc(pr)}" target="_blank">PR ↗</a>' if pr else ""
            out.append(f'<div class="card"><b>#{tid}</b> {_esc(title)}<br>'
                       f'<span class="squad">{_esc(squad)}</span> · {_esc(assignee or "unassigned")}{pr_link}</div>')
        out.append("</div>")
    out.append("</div>")
    return "".join(out)


def _render_budgets(conn) -> str:
    rows = _q(conn, "SELECT tribe,period,limit_tokens,spent_tokens,spent_usd FROM budgets ORDER BY tribe")
    if not rows:
        return "<p class='muted'>No budgets set.</p>"
    out = ["<table><tr><th>Tribe</th><th>Period</th><th>Spent / Limit (tokens)</th><th>USD</th><th>Usage</th></tr>"]
    for tribe, period, lim, spent, usd in rows:
        pct = (spent / lim * 100) if lim else 0
        out.append(f"<tr><td class='tribe'>{_esc(tribe)}</td><td>{_esc(period)}</td>"
                   f"<td>{spent:,} / {lim:,}</td><td>${usd}</td>"
                   f"<td><div class='bar'><div class='fill' style='width:{min(pct,100):.0f}%'></div></div> {pct:.1f}%</td></tr>")
    out.append("</table>")
    return "".join(out)


def _render_metrics(conn) -> str:
    raw, canon, links, ext, mem = _q(conn,
        "SELECT (SELECT count(*) FROM raw_entities),"
        "(SELECT count(*) FROM canonical_entities),"
        "(SELECT count(*) FROM entity_source_links),"
        "(SELECT count(*) FROM external_ids),"
        "(SELECT count(*) FROM agent_memory)")[0]
    agents = _q(conn, "SELECT DISTINCT agent_id FROM agent_memberships ORDER BY agent_id")
    return (f"<table><tr><th>Metric</th><th>Value</th></tr>"
            f"<tr><td>Raw entities</td><td>{raw}</td></tr>"
            f"<tr><td>Canonical</td><td>{canon}</td></tr>"
            f"<tr><td>Source links</td><td>{links}</td></tr>"
            f"<tr><td>Registry IDs</td><td>{ext}</td></tr>"
            f"<tr><td>Memory entries</td><td>{mem}</td></tr>"
            f"<tr><td>Agents</td><td>{len(agents)}</td></tr></table>")


# === AGENT CUBICLE (/agent/<id>) ===
def render_agent(conn, agent_id) -> str:
    meta = agent_meta(agent_id)
    soul = SOULS.get(meta["role"], "No soul defined for this role.")
    # reports-to + prod-deploy authority
    from shared.hierarchy import _resolve_supervisor, can_deploy_to_prod, roles_of
    try:
        supervisor = _resolve_supervisor(agent_id, conn)
    except Exception:
        supervisor = "?"
    try:
        can_prod = can_deploy_to_prod(agent_id, conn)[0]
    except Exception:
        can_prod = False
    rs = roles_of(agent_id, conn) if conn else set()
    chapter = meta["chapter"]
    rules_row = _q(conn, "SELECT rules FROM chapter_rules WHERE chapter=%s", (chapter,)) if chapter else []
    rules = rules_row[0][0] if rules_row else None
    # memory: all rows in groups this agent is a member of
    mem = _q(conn,
        "SELECT m.content, m.author, m.created_at FROM agent_memory m "
        "JOIN agent_memberships am ON am.group_id=m.group_id AND am.agent_id=%s "
        "ORDER BY m.created_at DESC LIMIT 20", (agent_id,))
    # squads/tribes this agent belongs to
    groups = _q(conn,
        "SELECT g.name, g.kind, am.role FROM agent_memberships am "
        "JOIN agent_groups g ON g.id=am.group_id WHERE am.agent_id=%s "
        "ORDER BY g.kind", (agent_id,))
    skills = "".join(f'<span class="tag">{_esc(s)}</span>' for s in meta["skills"]) or '<span class="muted">none</span>'
    tools = "".join(f'<span class="tag">{_esc(t)}</span>' for t in meta["tools"]) or '<span class="muted">none</span>'
    exts = "".join(f'<span class="tag">{_esc(e)}</span>' for e in meta["extensions"]) or '<span class="muted">none</span>'
    mem_html = "".join(f"<tr><td>{_esc(c[:120])}</td><td>{_esc(a)}</td><td>{_esc(cr)}</td></tr>"
                       for c, a, cr in mem) or '<tr><td class="muted" colspan=3>no memory yet</td></tr>'
    groups_html = "".join(f"<tr><td>{_esc(n)}</td><td><span class='badge'>{_esc(k)}</span></td><td>{_esc(r)}</td></tr>"
                          for n, k, r in groups) or '<tr><td class="muted" colspan=3>none</td></tr>'
    rules_html = f'<div class="panel" style="margin-top:14px"><h2>📖 Chapter Rules ({_esc(chapter)})</h2><pre style="white-space:pre-wrap;font-size:12px">{_esc(rules)}</pre></div>' if rules else ""
    # reports: filed by this agent (up) + received from reports (down)
    filed = _q(conn, "SELECT report_type,content,created_at FROM reports WHERE reporter=%s ORDER BY created_at DESC LIMIT 10", (agent_id,))
    received = _q(conn, "SELECT reporter,report_type,content,created_at FROM reports WHERE recipient=%s ORDER BY created_at DESC LIMIT 10", (agent_id,))
    filed_html = "".join(f"<tr><td><span class='badge'>{_esc(rt)}</span></td><td>{_esc(c[:100])}</td><td>{_esc(cr)}</td></tr>" for rt, c, cr in filed) or '<tr><td class="muted" colspan=3>none filed</td></tr>'
    recv_html = "".join(f"<tr><td>{_esc(r)}</td><td><span class='badge'>{_esc(rt)}</span></td><td>{_esc(c[:100])}</td><td>{_esc(cr)}</td></tr>" for r, rt, c, cr in received) or '<tr><td class="muted" colspan=4>none received</td></tr>'
    reports_html = (f'<div class="grid" style="margin-top:14px">'
                    f'<div class="panel"><h2>📤 Reports Filed (up)</h2><table><tr><th>Type</th><th>Content</th><th>When</th></tr>{filed_html}</table></div>'
                    f'<div class="panel"><h2>📥 Reports Received (down)</h2><table><tr><th>From</th><th>Type</th><th>Content</th><th>When</th></tr>{recv_html}</table></div></div>')
    initial = agent_id[0].upper() if agent_id else "?"
    return f"""<!doctype html><html><head><meta charset=utf-8><title>{_esc(agent_id)}</title>
<style>{CSS}</style></head><body>
<header><h1>🏢 dwizzyOS-HQ</h1><nav><a href="/">Control Room</a></nav>
<div class="sub">cubicle · {_esc(agent_id)}</div></header>
<div class="wrap">
<div class="breadcrumb"><a href="/">← all agents</a></div>
<div class="panel">
  <div class="avatar role-{meta['role']}">{initial}</div>
  <h2 style="border:0;margin:0">{_esc(agent_id)}</h2>
  <div class="role-line">role: <span class="badge role-{meta['role']}">{_esc(meta['role'])}</span> · chapter: {_esc(chapter or 'none')} · roles: {_esc(', '.join(sorted(rs)) or 'none')} · reports to: <a href="/agent/{_esc(supervisor)}">{_esc(supervisor)}</a> · prod-ship: {"✅ tribe_lead" if can_prod else "❌ no"}</div>
  <h3 style="margin:14px 0 6px;font-size:13px">🛠️ Skills</h3><div>{skills}</div>
  <h3 style="margin:12px 0 6px;font-size:13px">🔧 Tools</h3><div>{tools}</div>
  <h3 style="margin:12px 0 6px;font-size:13px">🔌 Extensions</h3><div>{exts}</div>
</div>
<div class="panel" style="margin-top:14px"><h2>💀 Soul</h2><pre style="white-space:pre-wrap;font-size:12px">{_esc(soul_block(meta['role']) if soul else soul)}</pre></div>
<div class="panel" style="margin-top:14px"><h2>👥 Groups</h2><table><tr><th>Group</th><th>Type</th><th>Role</th></tr>{groups_html}</table></div>
<div class="panel" style="margin-top:14px"><h2>🧠 Memory (last 20)</h2><table><tr><th>Content</th><th>Author</th><th>When</th></tr>{mem_html}</table></div>
{reports_html}
{rules_html}
</div></body></html>"""


# === TRIBE PAGE (/tribe/<name>) ===
def render_tribe(conn, tribe) -> str:
    goals = _q(conn, "SELECT text,status FROM goals WHERE scope='tribe' AND owner=%s ORDER BY id", (tribe,))
    goal_html = "".join(f'<div class="goal {"done" if st=="done" else ""}">🎯 {_esc(t)}</div>' for t, st in goals) or '<p class="muted">no goals</p>'
    squads = ORG.get(tribe, {})
    sq_html = []
    for squad, roles in squads.items():
        sg = _q(conn, "SELECT text,status FROM goals WHERE scope='squad' AND owner=%s ORDER BY id", (squad,))
        sg_html = "".join(f'<div class="goal {"done" if st=="done" else ""}" style="margin-left:12px">🎯 {_esc(t)}</div>' for t, st in sg)
        members = "".join(f'<div class="tree-node agent"><a href="/agent/{_esc(a)}">{_esc(a)}</a> '
                          f'<span class="badge role-{role}">{role}</span></div>' for role, a in roles.items())
        sq_html.append(f'<div class="panel" id="{_esc(squad)}"><h3 class="squad">{_esc(squad)}</h3>{sg_html}{members}</div>')
    budget = _q(conn, "SELECT limit_tokens,spent_tokens,spent_usd FROM budgets WHERE tribe=%s", (tribe,))
    b_html = ""
    if budget:
        lim, spent, usd = budget[0]
        pct = (spent / lim * 100) if lim else 0
        b_html = f'<div class="bar"><div class="fill" style="width:{min(pct,100):.0f}%"></div></div> {spent:,}/{lim:,} tokens · ${usd} ({pct:.1f}%)'
    # releases: next-version deadline + history. Tribe_lead owns prod ship.
    rels = _q(conn, "SELECT version,stage,target_at,status,released_by FROM releases WHERE tribe=%s ORDER BY target_at DESC LIMIT 10", (tribe,))
    rel_html = "".join(f"<tr><td>{_esc(v)}</td><td>{_esc(s)}</td><td>{_esc(t or '—')}</td><td class='{st}'>{_esc(st)}</td><td>{_esc(rb or '—')}</td></tr>"
                       for v, s, t, st, rb in rels) or '<tr><td class="muted" colspan=5>none</td></tr>'
    next_rel = _q(conn, "SELECT version,target_at FROM releases WHERE tribe=%s AND status='planned' ORDER BY target_at LIMIT 1", (tribe,))
    next_html = f'<div class="goal">🚀 next: {_esc(next_rel[0][0])} · target {_esc(next_rel[0][1])} (weekly cadence — tribe_lead ships to prod)</div>' if next_rel else '<p class="muted">no release scheduled</p>'
    return f"""<!doctype html><html><head><meta charset=utf-8><title>{_esc(tribe)} tribe</title>
<style>{CSS}</style></head><body>
<header><h1>🏢 dwizzyOS-HQ</h1><nav><a href="/">Control Room</a></nav>
<div class="sub">tribe · {_esc(tribe)}</div></header>
<div class="wrap">
<div class="breadcrumb"><a href="/">← control room</a></div>
<div class="panel"><h2>Tribal Goals</h2>{goal_html}{b_html}</div>
<div class="panel" style="margin-top:14px"><h2>🚀 Release Schedule</h2>{next_html}<table style="margin-top:10px"><tr><th>Version</th><th>Stage</th><th>Target</th><th>Status</th><th>Released by</th></tr>{rel_html}</table></div>
<h2 style="margin:20px 0 10px;font-size:14px;color:#79c0ff">Squads</h2>
{''.join(sq_html) or '<p class="muted">no squads</p>'}
</div></body></html>"""


# === CHAPTER PAGE (/chapter/<name>) ===
def render_chapter(conn, chapter) -> str:
    rules = _q(conn, "SELECT rules FROM chapter_rules WHERE chapter=%s", (chapter,))
    rules_text = rules[0][0] if rules else "no rules defined"
    members = _q(conn,
        "SELECT DISTINCT am.agent_id FROM agent_memberships am "
        "JOIN agent_groups g ON g.id=am.group_id WHERE g.name=%s ORDER BY am.agent_id", (f"chapter_{chapter}",))
    # agents whose registry role maps to this chapter (broader than the chapter_ group)
    from shared.agent_registry import REGISTRY
    role_members = [aid for aid, m in REGISTRY.items() if m.get("chapter") == chapter]
    all_members = sorted(set([a for (a,) in members] + role_members))
    mem_html = "".join(f'<div class="tree-node agent"><a href="/agent/{_esc(a)}">{_esc(a)}</a></div>' for a in all_members) or '<p class="muted">no members</p>'
    kpis = _q(conn, "SELECT metric,target,actual FROM kpis WHERE scope='chapter' AND owner=%s", (chapter,))
    kpi_html = "".join(f"<tr><td>{_esc(m)}</td><td>{_esc(t)}</td><td>{_esc(a or '—')}</td></tr>" for m, t, a in kpis) or '<tr><td class="muted" colspan=3>none</td></tr>'
    return f"""<!doctype html><html><head><meta charset=utf-8><title>{_esc(chapter)} chapter</title>
<style>{CSS}</style></head><body>
<header><h1>🏢 dwizzyOS-HQ</h1><nav><a href="/">Control Room</a></nav>
<div class="sub">chapter · {_esc(chapter)} (leader sets standardization)</div></header>
<div class="wrap">
<div class="breadcrumb"><a href="/">← control room</a></div>
<div class="panel"><h2>📖 Standardized Workflow (Chapter Rules)</h2><pre style="white-space:pre-wrap;font-size:13px">{_esc(rules_text)}</pre></div>
<div class="grid" style="margin-top:20px">
  <div class="panel"><h2>👥 Members</h2>{mem_html}</div>
  <div class="panel"><h2>📊 Chapter KPIs</h2><table><tr><th>Metric</th><th>Target</th><th>Actual</th></tr>{kpi_html}</table></div>
</div>
</div></body></html>"""


# === CTO PAGE (/cto) — top of hierarchy ===
def render_cto(conn) -> str:
    # org KPI matrix: per-tribe cycle pass + key metrics
    kpis = _q(conn, "SELECT scope,owner,metric,target,actual FROM kpis WHERE scope='tribe' ORDER BY owner")
    kpi_html = "".join(f"<tr><td class='tribe'>{_esc(o)}</td><td>{_esc(m)}</td><td>{_esc(t)}</td><td>{_esc(a or '—')}</td></tr>"
                       for _, o, m, t, a in kpis)
    # reports filed up to CTO (from tribe_lead + chapter_lead)
    reps = _q(conn, "SELECT reporter,report_type,content,created_at FROM reports WHERE recipient='dwizzy_cto' ORDER BY created_at DESC LIMIT 20")
    rep_html = "".join(f"<tr><td>{_esc(r)}</td><td><span class='badge'>{_esc(rt)}</span></td><td>{_esc(c[:140])}</td><td>{_esc(cr)}</td></tr>"
                       for r, rt, c, cr in reps) or '<tr><td class="muted" colspan=4>no reports yet</td></tr>'
    # tasks CTO assigned
    assigned = _q(conn, "SELECT id,title,assignee,assignment_scope,status FROM tasks WHERE assigner_id='dwizzy_cto' ORDER BY id DESC LIMIT 15")
    asg_html = "".join(f"<tr><td>#{i}</td><td>{_esc(t)}</td><td>{_esc(a)}</td><td>{_esc(s)}</td><td class='{st}'>{_esc(st)}</td></tr>"
                       for i, t, a, s, st in assigned) or '<tr><td class="muted" colspan=5>none</td></tr>'
    # weekly release status per tribe (CTO oversees cadence)
    rels = _q(conn, "SELECT tribe,version,stage,target_at,status FROM releases ORDER BY target_at DESC LIMIT 12")
    rel_html = "".join(f"<tr><td class='tribe'>{_esc(tr)}</td><td>{_esc(v)}</td><td>{_esc(s)}</td><td>{_esc(t or '—')}</td><td class='{st}'>{_esc(st)}</td></tr>"
                       for tr, v, s, t, st in rels) or '<tr><td class="muted" colspan=5>none</td></tr>'
    return f"""<!doctype html><html><head><meta charset=utf-8><title>CTO</title>
<style>{CSS}</style></head><body>
<header><h1>🏢 dwizzyOS-HQ</h1><nav><a href="/">Control Room</a> · <a href="/cto">CTO</a></nav>
<div class="sub">CTO · top of hierarchy</div></header>
<div class="wrap">
<div class="panel"><h2>📊 Tribe KPI Matrix</h2><table><tr><th>Tribe</th><th>Metric</th><th>Target</th><th>Actual</th></tr>{kpi_html}</table></div>
<div class="panel" style="margin-top:14px"><h2>🚀 Weekly Release Cadence (tribe_lead ships to prod)</h2><table><tr><th>Tribe</th><th>Version</th><th>Stage</th><th>Target</th><th>Status</th></tr>{rel_html}</table></div>
<div class="grid" style="margin-top:20px">
  <div class="panel"><h2>📥 Reports to CTO</h2><table><tr><th>Reporter</th><th>Type</th><th>Content</th><th>When</th></tr>{rep_html}</table></div>
  <div class="panel"><h2>📤 Tasks CTO Assigned</h2><table><tr><th>#</th><th>Title</th><th>Assignee</th><th>Scope</th><th>Status</th></tr>{asg_html}</table></div>
</div>
</div></body></html>"""


# === SQUAD PAGE (/squad/<name>) — dev schedule + backlog + gates ===
def render_squad(conn, squad) -> str:
    from shared.hierarchy import SQUAD_TRIBE, github_scope
    tribe = SQUAD_TRIBE.get(squad, "?")
    scope = github_scope(squad)
    sched = _q(conn, "SELECT milestone,due_at,status FROM schedules WHERE squad=%s ORDER BY id", (squad,))
    sched_html = "".join(f"<tr><td>{_esc(m)}</td><td>{_esc(d or '—')}</td><td class='{s}'>{_esc(s)}</td></tr>"
                         for m, d, s in sched) or '<tr><td class="muted" colspan=3>no schedule</td></tr>'
    tasks = _q(conn,
        "SELECT id,title,assignee,status,doc_done,test_done,audit_done,qa_done,devops_done "
        "FROM tasks WHERE squad=%s ORDER BY priority DESC,id", (squad,))
    def gates(d,t,a,q,do):
        return "".join(f"<span class='tag {'done' if g else ''}'>{n}</span>" for g,n in
                       [(d,"doc"),(t,"test"),(a,"audit"),(q,"qa"),(do,"devops")])
    task_html = "".join(f"<tr><td>#{i}</td><td>{_esc(t)}</td><td>{_esc(a or 'unassigned')}</td><td class='{st}'>{_esc(st)}</td><td>{gates(d,t,a,q,do)}</td></tr>"
                        for i, t, a, st, d, t2, a2, q, do in tasks) or '<tr><td class="muted" colspan=5>no backlog</td></tr>'
    goals = _q(conn, "SELECT text,status FROM goals WHERE scope='squad' AND owner=%s", (squad,))
    goal_html = "".join(f'<div class="goal {"done" if st=="done" else ""}">🎯 {_esc(t)}</div>' for t, st in goals)
    # PRD + 1-day sprints authored by squad_lead
    sprints = _q(conn, "SELECT day_index,goal,status,prd_text FROM sprints WHERE squad=%s ORDER BY day_index", (squad,))
    prd = sprints[0][3] if sprints else None
    prd_html = f'<div class="panel"><h2>📄 PRD (squad_lead-authored)</h2><pre style="white-space:pre-wrap;font-size:12px">{_esc(prd)}</pre></div>' if prd else '<p class="muted">no PRD yet — squad_lead must author one</p>'
    sp_html = "".join(f"<tr><td>Day {i}</td><td>{_esc(g)}</td><td class='{s}'>{_esc(s)}</td></tr>" for i, g, s, _ in sprints) or '<tr><td class="muted" colspan=3>no sprints (1 working-day each)</td></tr>'
    return f"""<!doctype html><html><head><meta charset=utf-8><title>{_esc(squad)}</title>
<style>{CSS}</style></head><body>
<header><h1>🏢 dwizzyOS-HQ</h1><nav><a href="/">Control Room</a></nav>
<div class="sub">squad · {_esc(squad)} (tribe {_esc(tribe)})</div></header>
<div class="wrap">
<div class="breadcrumb"><a href="/tribe/{tribe}">← {_esc(tribe)} tribe</a> · github scope: {_esc(scope['repo'])} · branch prefix {_esc(scope['branch_prefix'])}</div>
<div class="panel"><h2>🎯 Squad Goals</h2>{goal_html or '<p class=muted>none</p>'}</div>
<div style="margin-top:14px">{prd_html}</div>
<div class="grid" style="margin-top:20px">
  <div class="panel"><h2>🏃 1-Day Sprints</h2><table><tr><th>Day</th><th>Goal</th><th>Status</th></tr>{sp_html}</table></div>
  <div class="panel"><h2>📅 Milestones</h2><table><tr><th>Milestone</th><th>Due</th><th>Status</th></tr>{sched_html}</table></div>
</div>
<div class="panel" style="margin-top:20px"><h2>📋 Backlog + Process Gates</h2><table><tr><th>#</th><th>Title</th><th>Assignee</th><th>Status</th><th>Gates</th></tr>{task_html}</table></div>
</div></body></html>"""
