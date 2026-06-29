"""dwizzyOS-HQ dashboard server. Stdlib HTTP, multi-page, per-route 10s cache.

Routes: / /agent/<id> /tribe/<name> /chapter/<name>.
Renders in dashboard/handlers.py; CSS in dashboard/styles.py.
Reads PG via shared.config.pg_dsn(). Read-only. Bind 0.0.0.0:8485 (LAN).
"""
from __future__ import annotations
import time
import psycopg
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

from shared.config import pg_dsn
from dashboard import handlers
from dashboard.styles import CSS

# ponytail: per-route 10s render cache — kills the 5× docker-bridge PG
# handshake-per-refresh lag. Page is read-only; operators don't need sub-10s.
_CACHE: dict[str, tuple[float, bytes]] = {}
TTL = 10


def _render(route: str, key: str) -> bytes:
    now = time.time()
    cached = _CACHE.get(route)
    if cached and now - cached[0] < TTL:
        return cached[1]
    with psycopg.connect(pg_dsn()) as conn:
        if route == "/":
            body = handlers.render_home(conn).encode()
        elif route == "/cto":
            body = handlers.render_cto(conn).encode()
        elif route.startswith("/agent/"):
            body = handlers.render_agent(conn, key).encode()
        elif route.startswith("/squad/"):
            body = handlers.render_squad(conn, key).encode()
        elif route.startswith("/tribe/"):
            body = handlers.render_tribe(conn, key).encode()
        elif route.startswith("/chapter/"):
            body = handlers.render_chapter(conn, key).encode()
        else:
            return b""  # 404 handled by caller
    _CACHE[route] = (now, body)
    return body


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = unquote(self.path).rstrip("/") or "/"
        try:
            if path == "/":
                body = _render("/", "")
            elif path == "/cto":
                body = _render("/cto", "")
            elif path.startswith(("/agent/", "/tribe/", "/chapter/", "/squad/")):
                key = path.split("/", 2)[2]
                if not key:
                    self.send_error(400); return
                body = _render(path, key)
            else:
                self.send_error(404); return
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
