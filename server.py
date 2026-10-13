"""
server.py - serves the Nashmi web interface (the web folder) and connects it to rag.py.
Only uses Python's standard library, so there is nothing new to install.

Run:   py server.py            -> opens http://localhost:8000
       py server.py --port 9000 --no-browser

API (used by the page):
  GET  /api/status                         model + index info
  POST /api/chat   {conversation_id, message}  -> streams JSON lines: meta, token..., done
  POST /api/reset  {conversation_id}       forget a conversation
"""
import argparse
import json
import mimetypes
import os
import threading
import time
import traceback
import webbrowser
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import rag

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "web")

STATE = {"retriever": None, "index_mtime": None, "model": "loading", "model_error": None}
CONVERSATIONS = {}  # conversation_id -> {"history": [...], "memory": {...}}
LOCK = threading.Lock()


def retriever():
    """Load the index once; reload automatically if index.pkl was rebuilt."""
    path = rag.INDEX_PATH
    if not os.path.exists(path):
        return None
    mtime = os.path.getmtime(path)
    with LOCK:
        if STATE["retriever"] is None or STATE["index_mtime"] != mtime:
            STATE["retriever"], STATE["index_mtime"] = rag.Retriever(path), mtime
    return STATE["retriever"]


def warm_up_loop():
    """Load the chat model in the background; retry every 10 s while Ollama is not reachable."""
    while True:
        try:
            STATE["model"] = "loading"
            rag.warmup()
            STATE["model"], STATE["model_error"] = "ready", None
            return
        except Exception as e:
            STATE["model"], STATE["model_error"] = "offline", str(e)
            time.sleep(10)


def conversation(cid):
    with LOCK:
        if cid not in CONVERSATIONS:
            CONVERSATIONS[cid] = {"history": [], "memory": rag.new_memory()}
        return CONVERSATIONS[cid]


class Handler(BaseHTTPRequestHandler):
    server_version = "Nashmi/1.0"

    def log_message(self, fmt, *args):  # quieter console: only API calls
        if "/api/" in (args[0] if args else ""):
            print(time.strftime("%H:%M:%S"), fmt % args)

    # ---------- helpers
    def send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def stream_line(self, obj):
        self.wfile.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
        self.wfile.flush()

    # ---------- routes
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/status":
            return self.status()
        return self.static(path)

    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/api/chat":
            return self.chat()
        if path == "/api/reset":
            cid = str(self.read_json().get("conversation_id", ""))
            with LOCK:
                CONVERSATIONS.pop(cid, None)
            return self.send_json({"ok": True})
        self.send_json({"error": "not found"}, 404)

    def status(self):
        r = retriever()
        files = Counter(c["source"].split(" › ")[0] for c in r.chunks) if r else {}
        self.send_json({
            "model": STATE["model"] if not rag.FAKE else "ready",
            "model_name": rag.LLM_MODEL,
            "model_error": STATE["model_error"],
            "fake": rag.FAKE,
            "index": bool(r),
            "files": [{"name": f, "chunks": n} for f, n in files.items()],
            "records": len(r.records) if r else 0,
            "search": ("fast" if r.vecs is None else "hybrid") if r else None,
        })

    def chat(self):
        req = self.read_json()
        question = str(req.get("message", "")).strip()
        conv = conversation(str(req.get("conversation_id") or "default"))
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        t0 = time.time()
        r = retriever()
        if not r:
            self.stream_line({"type": "error", "message": "ما في فهرس بعد. شغّل: py rag.py ingest data_excel"})
            return
        if not question:
            self.stream_line({"type": "error", "message": "الرسالة فاضية"})
            return
        try:
            mem = conv["memory"]
            gen, sources, _ = rag.answer(r, question, history=conv["history"], stream=True, memory=mem)
            focus = set(mem["focus"])
            self.stream_line({
                "type": "meta",
                "sources": list(dict.fromkeys(sources)),  # unique, in order
                "table": mem["table"],
                "warning": mem["warning"],
                "people": [{**p, "focus": p["id"] in focus} for p in mem["people"]],
                "family": mem.get("family_label"),
            })
            text = ""
            for piece in gen:
                text += piece
                self.stream_line({"type": "token", "text": piece})
            conv["history"] += [{"role": "user", "content": question}, {"role": "assistant", "content": text}]
            conv["history"] = conv["history"][-20:]
            self.stream_line({"type": "done", "seconds": round(time.time() - t0, 1)})
        except (BrokenPipeError, ConnectionResetError):
            pass  # the browser closed the tab mid-answer
        except Exception as e:
            traceback.print_exc()
            msg = str(e)
            if "connect" in msg.lower() or "ollama" in msg.lower():
                msg = "نشمي مش قادر يوصل لـ Ollama. تأكد إنه شغّال (ollama serve) وجرب كمان مرة."
            try:
                self.stream_line({"type": "error", "message": msg})
            except Exception:
                pass

    def static(self, path):
        if not os.path.isdir(DIST):
            return self.send_json({"error": "the web folder is missing next to server.py"}, 500)
        rel = path.lstrip("/") or "index.html"
        full = os.path.normpath(os.path.join(DIST, rel))
        if not full.startswith(DIST) or not os.path.isfile(full):
            full = os.path.join(DIST, "index.html")  # single-page app: unknown paths -> index
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "image/svg+xml"):
            ctype += "; charset=utf-8"
        with open(full, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    ap.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"))
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    mimetypes.add_type("application/javascript", ".js")
    mimetypes.add_type("text/css", ".css")
    if retriever() is None:
        print("!! no index.pkl yet - run:  py rag.py ingest data_excel")
    if not rag.FAKE:
        threading.Thread(target=warm_up_loop, daemon=True).start()
    url = f"http://localhost:{a.port}"
    print(f"\n  نشمي شغّال  ->  {url}\n  (Ctrl+C to stop)\n")
    if not a.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
