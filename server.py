import json
import copy
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from game import advance, new_game, view
from players import PlayerError

ROOT = Path(__file__).parent
games = {}
guard = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, data, mime="application/json"):
        if mime == "application/json":
            data = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", mime + "; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/":
            return self.reply(200, (ROOT/"index.html").read_bytes(), "text/html")
        if self.path == "/api/game":
            return self.game_request(None)
        self.reply(404, {})

    def do_POST(self):
        if self.headers.get_content_type() != "application/json":
            return self.reply(415, {})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 16384:
                return self.reply(400, {})
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError()
        except ValueError:
            return self.reply(400, {})
        if self.path == "/api/new":
            key = secrets.token_urlsafe(32)
            g = new_game()
            with guard:
                games[key] = (threading.Lock(), g)
            return self.reply(201, dict(token=key, revision=0, **view(g)))
        if self.path == "/api/action":
            return self.game_request(data)
        self.reply(404, {})

    def game_request(self, data):
        entry = games.get(self.headers.get("Authorization","").removeprefix("Bearer "))
        if entry is None:
            return self.reply(404, dict(error="对局已过期，请重新开局"))
        lock, g = entry
        with lock:
            rev = g.get("revision", 0)
            if data is not None:
                if data.get("revision") != rev:
                    return self.reply(409, dict(error="局面已更新，请刷新"))
                try:
                    updated = copy.deepcopy(g)
                    advance(updated, data)
                except PlayerError as e:
                    return self.reply(502, dict(error=str(e)))
                except ValueError as e:
                    return self.reply(400, dict(error=str(e)))
                g.clear()
                g.update(updated)
                g["revision"] = rev + 1
            self.reply(200, dict(revision=g.get("revision",0), **view(g)))


if __name__ == "__main__":
    port = int(os.getenv("PORT","8765"))
    print(f"http://127.0.0.1:{port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1",port), Handler).serve_forever()
