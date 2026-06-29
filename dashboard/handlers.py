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
  <div class="role-line">role: <span class="badge role-{meta['role']}">{_esc(meta['role'])}</span> · chapter: {_esc(chapter or 'none')}</div>
  <h3 style="margin:14px 0 6px;font-size:13px">🛠️ Skills</h3><div>{skills}</div>
  <h3 style="margin:12px 0 6px;font-size:13px">🔧 Tools</h3><div>{tools}</div>
  <h3 style="margin:12px 0 6px;font-size:13px">🔌 Extensions</h3><div>{exts}</div>
</div>
<div class="panel" style="margin-top:14px"><h2>💀 Soul</h2><pre style="white-space:pre-wrap;font-size:12px">{_esc(soul_block(meta['role']) if soul else soul)}</pre></div>
<div class="panel" style="margin-top:14px"><h2>👥 Groups</h2><table><tr><th>Group</th><th>Type</th><th>Role</th></tr>{groups_html}</table></div>
<div class="panel" style="margin-top:14px"><h2>🧠 Memory (last 20)</h2><table><tr><th>Content</th><th>Author</th><th>When</th></tr>{mem_html}</table></div>
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
    return f"""<!doctype html><html><head><meta charset=utf-8><title>{_esc(tribe)} tribe</title>
<style>{CSS}</style></head><body>
<header><h1>🏢 dwizzyOS-HQ</h1><nav><a href="/">Control Room</a></nav>
<div class="sub">tribe · {_esc(tribe)}</div></header>
<div class="wrap">
<div class="breadcrumb"><a href="/">← control room</a></div>
<div class="panel"><h2>Tribal Goals</h2>{goal_html}{b_html}</div>
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
    mem_html = "".join(f'<div class="tree-node agent"><a href="/agent/{_esc(a)}">{_esc(a)}</a></div>' for (a,) in members) or '<p class="muted">no members</p>'
    return f"""<!doctype html><html><head><meta charset=utf-8><title>{_esc(chapter)} chapter</title>
<style>{CSS}</style></head><body>
<header><h1>🏢 dwizzyOS-HQ</h1><nav><a href="/">Control Room</a></nav>
<div class="sub">chapter · {_esc(chapter)}</div></header>
<div class="wrap">
<div class="breadcrumb"><a href="/">← control room</a></div>
<div class="panel"><h2>📖 Chapter Rules</h2><pre style="white-space:pre-wrap;font-size:13px">{_esc(rules_text)}</pre></div>
<div class="panel" style="margin-top:14px"><h2>👥 Members</h2>{mem_html}</div>
</div></body></html>"""
