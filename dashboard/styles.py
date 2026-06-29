"""Dashboard CSS — cubicle/control-room aesthetic. Dark, intentional, not a
default template. Kept in its own module so server.py stays <800 lines.
"""
CSS = """
*{box-sizing:border-box}
body{font:14px/1.5 system-ui,sans-serif;background:#0a0e14;color:#c9d1d9;margin:0;padding:0}
a{color:#58a6ff;text-decoration:none}a:hover{text-decoration:underline}
header{background:#161b22;border-bottom:1px solid #30363d;padding:14px 24px;display:flex;align-items:center;gap:20px;position:sticky;top:0;z-index:10}
header h1{margin:0;font-size:18px;color:#58a6ff}
header nav{display:flex;gap:16px;font-size:13px}
header .sub{color:#8b949e;font-size:12px;margin-left:auto}
.wrap{max-width:1280px;margin:0 auto;padding:20px 24px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}
.panel{background:#0d1117;border:1px solid #30363d;border-radius:8px;padding:16px}
.panel h2{margin:0 0 12px;font-size:14px;color:#79c0ff;border-bottom:1px solid #30363d;padding-bottom:8px}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{border:1px solid #21262d;padding:7px 10px;text-align:left;vertical-align:top}
th{background:#161b22;color:#8b949e;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.5px}
.badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:600}
.tribe{color:#f0883e}.squad{color:#a371f7}.lead-role{background:#1f6feb;color:#fff}
.role-lead{background:#1f6feb}.role-backend{background:#238636}.role-qa{background:#da3633}
.role-frontend{background:#8957e5}.role-devops{background:#d29922}.role-scraper{background:#1f6feb}
.role-processor{background:#238636}.role-store{background:#8957e5}
.todo{color:#8b949e}.doing{color:#d29922}.review{color:#a371f7}.done{color:#3fb950}
.bar{height:8px;background:#21262d;border-radius:4px;overflow:hidden}
.fill{height:100%;background:linear-gradient(90deg,#1f6feb,#58a6ff)}
.goal{background:#0a0e14;border-left:3px solid #3fb950;padding:8px 12px;margin:6px 0;border-radius:0 4px 4px 0;font-size:13px}
.goal.done{border-left-color:#8b949e;text-decoration:line-through;color:#8b949e}
ul{margin:0;padding-left:18px}
/* cubicle cards — agents as people */
.cubicles{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px}
.cubicle{background:#0d1117;border:1px solid #30363d;border-radius:8px;padding:14px;transition:transform .15s,border-color .15s}
.cubicle:hover{transform:translateY(-2px);border-color:#58a6ff}
.cubicle .avatar{width:36px;height:36px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:700;color:#fff;margin-bottom:8px;font-size:14px}
.cubicle h3{margin:0 0 2px;font-size:14px}
.cubicle .role-line{font-size:11px;color:#8b949e;margin-bottom:8px}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px;vertical-align:middle}
.dot.on{background:#3fb950;box-shadow:0 0 6px #3fb950}.dot.off{background:#484f58}
.kanban{display:flex;gap:10px}
.kanban-col{flex:1;min-width:0;background:#0a0e14;border:1px solid #21262d;border-radius:6px;padding:10px}
.kanban-col h3{margin:0 0 8px;font-size:12px;text-transform:uppercase;letter-spacing:.5px}
.card{background:#161b22;border:1px solid #30363d;border-radius:4px;padding:8px;margin-bottom:8px;font-size:12px}
.tag{display:inline-block;background:#21262d;color:#c9d1d9;padding:1px 7px;border-radius:8px;font-size:10px;margin:2px 3px 0 0}
.tree-node{padding:3px 0}
.tree-node.tribe{font-weight:600;color:#f0883e;margin-top:8px}
.tree-node.squad{color:#a371f7;margin-left:16px}
.tree-node.agent{color:#c9d1d9;margin-left:32px;font-size:12px}
.breadcrumb{font-size:12px;color:#8b949e;margin-bottom:14px}
.back{font-size:12px}
.muted{color:#8b949e;font-size:12px}
"""
