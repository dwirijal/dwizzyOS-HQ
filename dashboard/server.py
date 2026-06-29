"""dwizzyOS-HQ dashboard. Stdlib HTTP server, no deps, no build step.

4 panels per corporate-control-room spec:
  - Org structure: tribes -> squads -> agents + chapter/guild memberships.
  - Kanban: tasks across todo/doing/review/done, squad-scoped.
  - Budgets: per-tribe token spend vs limit.
  - Dashboard: entity counts, merge methods, memory count, agent list.

Reads PG via shared.config.pg_dsn(). Read-only. Bind 127.0.0.1:8485.
ponytail: static HTML string + one query pass. No JS framework, no SSE
auto-refresh (manual reload). Add WebSocket live-updates when operators
actually watch it continuously.
"""
from __future__ import annotations
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import psycopg

from shared.config import pg_dsn

CSS = """
body{font:14px/1.5 system-ui,sans-serif;background:#0d1117;color:#c9d1d9;margin:0;padding:20px}
h1{color:#58a6ff;margin:0 0 4px;font-size:20px}
h2{color:#79c0ff;border-bottom:1px solid #30363d;padding-bottom:4px;margin:24px 0 12px;font-size:16px}
.sub{color:#8b949e;font-size:12px;margin-bottom:16px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}
.panel{background:#161b22;border:1px solid #30363d;border-radius:6px;padding:14px}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{border:1px solid #30363d;padding:6px 8px;text-align:left}
th{background:#21262d;color:#8b949e;font-weight:600}
.badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;background:#30363d;color:#c9d1d9}
.tribe{color:#f0883e;font-weight:600}.squad{color:#a371f7}.lead{background:#1f6feb;color:#fff}
.todo{color:#8b949e}.doing{color:#d29922}.review{color:#a371f7}.done{color:#3fb950}
.bar{height:8px;background:#30363d;border-radius:4px;overflow:hidden}
.fill{height:100%;background:#1f6feb}
ul{margin:0;padding-left:18px}
.kanban-col{flex:1;min-width:0}
.kanban{display:flex;gap:10px}
.card{background:#0d1117;border:1px solid #30363d;border-radius:4px;padding:8px;margin-bottom:8px;font-size:12px}
a{color:#58a6ff}
"""


def _q(sql, args=None, conn=None):
    if conn is not None:
        with conn.cursor() as cur:
            cur.execute(sql, args or ())
            return cur.fetchall()
    with psycopg.connect(pg_dsn()) as c, c.cursor() as cur:
        cur.execute(sql, args or ())
        return cur.fetchall()

# ponytail: render cache — page is read-only, 10s TTL kills the 5× docker-bridge
# handshake-per-refresh lag. Drop to 0 if operators need sub-10s freshness.
_CACHE: tuple[float, bytes] = (0.0, b"")


def _org_panel():
    rows = _q("""
        WITH RECURSIVE tree AS (
          SELECT id,name,kind,parent_id,0 AS depth FROM agent_groups WHERE parent_id IS NULL
          UNION ALL
          SELECT g.id,g.name,g.kind,g.parent_id,t.depth+1 FROM agent_groups g JOIN tree t ON g.parent_id=t.id
        )
        SELECT t.id,t.name,t.kind,t.depth,
               (SELECT string_agg(agent_id||'('||role||')',', ')
                FROM agent_memberships m WHERE m.group_id=t.id) AS members
        FROM tree t ORDER BY t.depth,t.kind,t.name
    """)
    out = ["<table><tr><th>Group</th><th>Type</th><th>Members (role)</th></tr>"]
    for _id, name, kind, depth, members in rows:
        cls = {"tribe": "tribe", "squad": "squad"}.get(kind, "")
        indent = "&nbsp;" * (depth * 2)
        out.append(f"<tr><td>{indent}<span class='{cls}'>{html.escape(name)}</span></td>"
                   f"<td><span class='badge'>{kind}</span></td>"
                   f"<td>{html.escape(members or '')}</td></tr>")
    out.append("</table>")
    return "".join(out)


def _kanban_panel():
    cols = [("todo", "To Do"), ("doing", "Doing"), ("review", "Review"), ("done", "Done")]
    tasks = _q("SELECT id,title,tribe,squad,assignee,status,gh_pr_url FROM tasks ORDER BY priority DESC, id")
    by_status = {s: [] for s, _ in cols}
    for t in tasks:
        by_status.setdefault(t[5], []).append(t)
    out = ['<div class="kanban">']
    for status, label in cols:
        out.append(f'<div class="kanban-col"><h3 style="margin:0 0 8px;font-size:13px" class="{status}">{label} ({len(by_status.get(status,[]))})</h3>')
        for tid, title, tribe, squad, assignee, st, pr in by_status.get(status, []):
            pr_link = f'<br><a href="{html.escape(pr)}" target="_blank">PR</a>' if pr else ""
            out.append(f'<div class="card"><b>#{tid}</b> {html.escape(title)}<br>'
                       f'<span class="squad">{html.escape(squad)}</span> · {html.escape(assignee or "unassigned")}{pr_link}</div>')
        out.append("</div>")
    out.append("</div>")
    return "".join(out)


def _budget_panel():
    rows = _q("SELECT tribe,period,limit_tokens,spent_tokens,spent_usd FROM budgets ORDER BY tribe")
    if not rows:
        return "<p>No budgets set.</p>"
    out = ["<table><tr><th>Tribe</th><th>Period</th><th>Spent / Limit (tokens)</th><th>USD</th><th>Usage</th></tr>"]
    for tribe, period, lim, spent, usd in rows:
        pct = (spent / lim * 100) if lim else 0
        out.append(f"<tr><td class='tribe'>{tribe}</td><td>{period}</td>"
                   f"<td>{spent:,} / {lim:,}</td><td>${usd}</td>"
                   f"<td><div class='bar'><div class='fill' style='width:{min(pct,100):.0f}%'></div></div> {pct:.1f}%</td></tr>")
    out.append("</table>")
    return "".join(out)


def _dashboard_panel():
    raw, canon, links, ext, mem = _q("""
        SELECT (SELECT count(*) FROM raw_entities),
               (SELECT count(*) FROM canonical_entities),
               (SELECT count(*) FROM entity_source_links),
               (SELECT count(*) FROM external_ids),
               (SELECT count(*) FROM agent_memory)
    """)[0]
    agents = _q("SELECT DISTINCT agent_id FROM agent_memberships ORDER BY agent_id")
    out = [f"<table><tr><th>Metric</th><th>Value</th></tr>"
           f"<tr><td>Raw entities</td><td>{raw}</td></tr>"
           f"<tr><td>Canonical entities</td><td>{canon}</td></tr>"
           f"<tr><td>Source links</td><td>{links}</td></tr>"
           f"<tr><td>Registry IDs</td><td>{ext}</td></tr>"
           f"<tr><td>Memory entries</td><td>{mem}</td></tr>"
           f"<tr><td>Active agents</td><td>{len(agents)}</td></tr></table>"]
    out.append("<h3 style='font-size:13px;margin:12px 0 6px'>Agents</h3><ul>")
    for (a,) in agents:
        out.append(f"<li>{html.escape(a)}</li>")
    out.append("</ul>")
    return "".join(out)


def _render():
    return f"""<!doctype html><html><head><meta charset=utf-8><title>dwizzyOS-HQ Control Room</title>
<style>{CSS}</style></head><body>
<h1>dwizzyOS-HQ Control Room</h1>
<div class="sub">CompanyOS · Spotify-tribe agent org · live read from PG</div>
<div class="grid">
  <div class="panel"><h2>Org Structure</h2>{_org_panel()}</div>
  <div class="panel"><h2>Dashboard</h2>{_dashboard_panel()}</div>
</div>
<div class="panel" style="margin-top:20px"><h2>Kanban Board</h2>{_kanban_panel()}</div>
<div class="panel" style="margin-top:20px"><h2>Budgets</h2>{_budget_panel()}</div>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/":
            self.send_error(404)
            return
        try:
            import time
            now = time.time()
            ts, cached = _CACHE
            if now - ts < 10:
                body = cached
            else:
                body = _render().encode()
                globals()["_CACHE"] = (now, body)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(f"dashboard error: {e}".encode())

    def log_message(self, *a):
        pass  # quiet


def main():
    port = int(__import__("os").environ.get("HQ_DASH_PORT", "8485"))
    # ponytail: 0.0.0.0 = LAN access (192.168.100.6). No auth — read-only, internal network only.
    # Add basic-auth + TLS if ever exposed beyond trusted LAN.
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
