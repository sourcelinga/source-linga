"""Local web app: http://127.0.0.1:8777

Localhost always works. With "lan_access": true, your iPhone, iPad and other Macs on the same
Wi-Fi can use it too, but only after pairing (a 6-digit code shown on this Mac sets a device key).
Apps that speak the OpenAI or Ollama API (Enchanted, Shortcuts, scripts) use the same key as a
Bearer token.
"""
import hmac
import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .common import (DATA, JOBS, ROOT, allowed_path, backup_and_write, db, expand, load_config, load_state,
                     save_config, start_job)
from .llm import Ollama
from .prompts import Prompts
from . import chat as chat_mod, convos, improve as imp, knowledge, skills, updater

prompts = Prompts()
_update_lock = threading.Lock()
ACTIVE = {"last_chat": 0.0}  # the scheduler waits while you are chatting
APP_NAME = "Source Linga"
APP_VERSION = "2.0.0"
MODEL_ID = "source-linga"
SERVICE_TYPE = "_sourcelinga._tcp"  # Bonjour name the iPhone/Android/Mac apps look for
DIST = os.path.join(ROOT, "dist")  # built apps (the Android APK, the Mac app zip), served to phones at /get
STATIC = {"/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json"),
          "/icon-180.png": ("icon-180.png", "image/png"), "/apple-touch-icon.png": ("icon-180.png", "image/png"),
          "/icon-192.png": ("icon-192.png", "image/png"), "/icon-512.png": ("icon-512.png", "image/png"),
          "/logo-64.png": ("logo-64.png", "image/png"), "/favicon.ico": ("logo-64.png", "image/png"),
          "/qr.js": ("qr.js", "text/javascript"), "/get": ("get.html", "text/html; charset=utf-8")}
DOWNLOADS = {"/download/android": ("SourceLinga.apk", "application/vnd.android.package-archive"),
             "/download/mac": ("SourceLinga-mac.zip", "application/zip")}


def ctx():
    cfg = load_config()
    return cfg, Ollama(cfg["ollama_url"], cfg.get("num_ctx", 16384), cfg.get("keep_alive", "60m"))


# ---------------------------------------------------------------- device pairing

def _secret(name, make):
    path = os.path.join(DATA, name)
    try:
        with open(path) as f:
            v = f.read().strip()
            if v:
                return v
    except OSError:
        pass
    v = make()
    with open(path, "w") as f:
        f.write(v)
    os.chmod(path, 0o600)
    return v


def device_key():
    return _secret("device_key", lambda: secrets.token_urlsafe(32))


def pair_code():
    return _secret("pair_code", lambda: "%06d" % secrets.randbelow(10 ** 6))


def new_device_key():
    """Revokes every paired device and app, and makes a new pairing code."""
    for name in ("device_key", "pair_code"):
        try:
            os.remove(os.path.join(DATA, name))
        except OSError:
            pass
    return device_key()


_failed = []  # times of wrong pairing codes (brute-force brake)


def lan_urls(port):
    urls = []
    try:
        name = subprocess.run(["scutil", "--get", "LocalHostName"], capture_output=True, text=True).stdout.strip()
        if name:
            urls.append("http://%s.local:%d" % (name.lower(), port))
    except OSError:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.0.2.1", 9))  # no packet is sent; this only picks the Wi-Fi interface address
        urls.append("http://%s:%d" % (s.getsockname()[0], port))
        s.close()
    except OSError:
        pass
    return urls


def _computer_name():
    try:
        return subprocess.run(["scutil", "--get", "ComputerName"], capture_output=True, text=True,
                              timeout=3).stdout.strip() or "Mac"
    except (OSError, subprocess.SubprocessError):
        return "Mac"


def advertise(port, on):
    """Announce this Mac on the Wi-Fi with Bonjour, so the phone apps find it without typing an address."""
    subprocess.run(["pkill", "-f", SERVICE_TYPE], capture_output=True)  # an old announcer from the last run
    if on:
        try:
            subprocess.Popen(["dns-sd", "-R", "%s on %s" % (APP_NAME, _computer_name()), SERVICE_TYPE, "local",
                              str(port), "path=/app", "version=" + APP_VERSION],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass


_archive = {"at": 0, "list": [], "ok": False}


def archived_models(cfg):
    """Models kept on the archive drive. A sleeping or flaky USB drive must never break the status page,
    so errors count as 'not connected' and the answer is cached for 10 minutes."""
    if time.time() - _archive["at"] < 600:
        return _archive["list"], _archive["ok"]
    out, ok = [], False
    try:
        arc = cfg.get("archive_dir")
        ok = bool(arc) and os.path.isdir(arc)
        root = os.path.join(arc or "/nonexistent", "manifests", "registry.ollama.ai", "library")
        if os.path.isdir(root):
            for name in sorted(os.listdir(root)):
                d = os.path.join(root, name)
                if os.path.isdir(d) and not name.startswith("._"):
                    out += ["%s:%s" % (name, t) for t in sorted(os.listdir(d)) if not t.startswith("._")]
    except OSError:
        out, ok = [], False
    _archive.update(at=time.time(), list=out, ok=ok)
    return out, ok


def status():
    cfg, llm = ctx()
    up = llm.up()
    st = load_state()
    events = [dict(r) for r in db().execute("SELECT created, kind, message FROM events ORDER BY id DESC LIMIT 30")]
    scores = [dict(model=r["model"], score=r["score"], tps=r["tps"], created=r["created"])
              for r in db().execute("SELECT * FROM model_scores ORDER BY created DESC LIMIT 20")]
    return {
        "ollama": up, "ollama_version": llm.version() if up else None,
        "model": cfg["model"], "embed_model": cfg["embed_model"],
        "models_dir": "~/.ollama/models (internal SSD)",
        "archive_dir": cfg.get("archive_dir"),
        "archive_ok": archived_models(cfg)[1],
        "archived": archived_models(cfg)[0],
        "installed": [{"name": m["name"], "gb": round(m.get("size", 0) / 1e9, 1)} for m in llm.tags()] if up else [],
        "index": knowledge.stats(),
        "last": {k[5:-3]: v for k, v in st.items() if k.startswith("last_") and k.endswith("_at")},
        "events": events, "scores": scores,
        "strategies": imp.strategy_stats(),
        "running": [j.to_dict() for j in JOBS.values() if j.status == "running"],
    }


def run_update(job, only, force):
    if not _update_lock.acquire(blocking=False):
        raise RuntimeError("an update is already running")
    try:
        return updater.run(job=job, only=only, force=force)
    finally:
        _update_lock.release()


class Handler(BaseHTTPRequestHandler):
    server_version = "SourceLinga/1.0"

    def log_message(self, fmt, *args):  # quiet
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body, default=str).encode()
        try:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass  # the browser/curl went away; nothing to do

    def _host(self):
        h = (self.headers.get("Host") or "").lower()
        return h[1:h.index("]")] if h.startswith("[") and "]" in h else h.split(":")[0]

    def _local_client(self):
        ip = self.client_address[0]
        return (ip[7:] if ip.startswith("::ffff:") else ip) in ("127.0.0.1", "::1")

    def _token(self):
        auth = self.headers.get("Authorization") or ""
        if auth.lower().startswith("bearer "):
            return auth[7:].strip()
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == "sl_key":
                return v
        return ""

    def _access(self):
        """'local' (this Mac), 'device' (paired iPhone/iPad/app) or None.
        Blocks other websites from driving the server (Origin must match Host; localhost names only
        count for connections that really come from this Mac, which stops DNS rebinding)."""
        origin = self.headers.get("Origin")
        if origin and origin != "null" and urlparse(origin).hostname != self._host():
            return None
        if self._local_client() and self._host() in ("127.0.0.1", "localhost", "::1"):
            return "local"
        tok = self._token()
        if tok and hmac.compare_digest(tok.encode(), device_key().encode()):
            return "device"
        return None

    def _static(self, path):
        name, ctype = STATIC[path]
        with open(os.path.join(ROOT, "web", name), "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "max-age=86400")
        self.end_headers()
        self.wfile.write(data)

    def _download(self, path):
        name, ctype = DOWNLOADS[path]
        try:
            with open(os.path.join(DIST, name), "rb") as f:
                data = f.read()
        except OSError:
            return self._send(404, {"error": "this app has not been built on this Mac yet"})
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition", 'attachment; filename="%s"' % name)
        self.end_headers()
        self.wfile.write(data)

    def _stream_start(self, ctype):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()  # HTTP/1.0: the body ends when the connection closes, so no length is needed

    def _pipe(self, events, write):
        """Run a chat event stream into the response; stop the model if the client goes away."""
        ACTIVE["last_chat"] = time.time()
        try:
            for ev in events:
                write(ev)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:  # headers are already sent: report the error inside the stream
            try:
                write({"type": "token", "text": "\n\n⚠ %s: %s" % (type(e).__name__, e)})
                write({"type": "done", "content": "", "tools": [], "error": str(e)})
            except OSError:
                pass
        finally:
            events.close()  # closes the Ollama request too, so generation stops
            ACTIVE["last_chat"] = time.time()

    def do_HEAD(self):
        if self._access() is None and urlparse(self.path).path not in STATIC:
            self.send_response(401)
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
        self.end_headers()

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in STATIC:
            return self._static(u.path)
        if u.path == "/pair":
            with open(os.path.join(ROOT, "web", "pair.html"), "rb") as f:
                return self._send(200, f.read(), "text/html; charset=utf-8")
        if u.path in DOWNLOADS:
            return self._download(u.path)
        access = self._access()
        if u.path == "/api/info":  # lets an app check that an address really is Source Linga, before pairing
            return self._send(200, {"name": APP_NAME, "version": APP_VERSION, "paired": access is not None,
                                    "computer": _computer_name(), "apps": [k for k, (n, _) in DOWNLOADS.items()
                                                                           if os.path.isfile(os.path.join(DIST, n))]})
        if access is None:
            if u.path in ("/", "/index.html", "/app") and not self._local_client():
                self.send_response(302)
                self.send_header("Location", "/pair")
                self.end_headers()
                return
            return self._send(401, {"error": "not paired: open /pair on this device, or send the device key "
                                              "as 'Authorization: Bearer <key>'"})
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path in ("/", "/index.html", "/app"):
                page = "app.html" if u.path == "/app" else "index.html"
                with open(os.path.join(ROOT, "web", page), "rb") as f:
                    return self._send(200, f.read(), "text/html; charset=utf-8")
            if u.path == "/api/convos":
                return self._send(200, convos.listing())
            if u.path.startswith("/api/convos/"):
                d = convos.get(u.path.rsplit("/", 1)[1])
                return self._send(200, d) if d else self._send(404, {"error": "no such conversation"})
            if u.path == "/api/warm":
                cfg, llm = ctx()
                threading.Thread(target=lambda: _quiet(llm.warm, cfg["model"]), daemon=True).start()
                return self._send(200, {"ok": True})
            if u.path == "/api/devices":
                if access != "local":
                    return self._send(403, {"error": "only on the Mac itself"})
                cfg = load_config()
                port = int(os.environ.get("FORGE_PORT", cfg.get("port", 8777)))
                return self._send(200, {"lan_access": bool(cfg.get("lan_access")), "urls": lan_urls(port),
                                        "apps": [k for k, (n, _) in DOWNLOADS.items()
                                                 if os.path.isfile(os.path.join(DIST, n))],
                                        "pair_code": pair_code(), "device_key": device_key(),
                                        "listening_on_lan": SERVER.get("lan", False)})
            if u.path == "/api/skills":
                return self._send(200, skills.listing())
            if u.path in ("/v1/models", "/ollama/api/tags", "/ollama", "/ollama/", "/ollama/api/version"):
                return self._compat_get(u.path)
            if u.path == "/api/status":
                return self._send(200, status())
            if u.path.startswith("/api/job/"):
                j = JOBS.get(u.path.rsplit("/", 1)[1])
                return self._send(200, j.to_dict()) if j else self._send(404, {"error": "no such job"})
            if u.path == "/api/targets":
                return self._send(200, knowledge.list_targets(q.get("q", "")))
            if u.path == "/api/file":
                cfg, _ = ctx()
                p = expand(q.get("path", ""))
                if not allowed_path(p, cfg):
                    return self._send(403, {"error": "outside allowed_roots"})
                with open(p, errors="replace") as f:
                    return self._send(200, {"path": p, "text": f.read()})
            if u.path == "/api/workflows":
                return self._send(200, imp.load_workflows())
            if u.path == "/api/strategies":
                return self._send(200, imp.load_strategies())
            if u.path == "/api/runs":
                rows = db().execute("SELECT id, created, kind, target, goal FROM runs ORDER BY id DESC LIMIT 60")
                return self._send(200, [dict(r) for r in rows])
            if u.path.startswith("/api/run/"):
                r = db().execute("SELECT * FROM runs WHERE id=?", (int(u.path.rsplit("/", 1)[1]),)).fetchone()
                if not r:
                    return self._send(404, {"error": "no such run"})
                d = dict(r)
                d["result"] = json.loads(d["result"])
                return self._send(200, d)
            if u.path == "/api/prompts":
                return self._send(200, [{"name": n, "text": prompts.get(n), "history": prompts.history(n)}
                                        for n in prompts.names()])
            if u.path == "/api/search":
                cfg, llm = ctx()
                return self._send(200, knowledge.search(q.get("q", ""), llm, cfg, k=10))
            if u.path == "/api/config":
                return self._send(200, load_config())
            return self._send(404, {"error": "not found"})
        except Exception as e:
            return self._send(500, {"error": "%s: %s" % (type(e).__name__, e)})

    def do_POST(self):
        p = urlparse(self.path).path
        # JSON only: a plain HTML form on another website cannot send this content type
        if "application/json" not in (self.headers.get("Content-Type") or ""):
            return self._send(403, {"error": "forbidden"})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        except ValueError:
            return self._send(400, {"error": "bad JSON"})
        if p == "/pair":
            return self._pair(body)
        access = self._access()
        if access is None:
            return self._send(401, {"error": "not paired"})
        try:
            cfg, llm = ctx()
            if p == "/api/chat/stream":
                def sse(ev):
                    self.wfile.write(("data: " + json.dumps(ev) + "\n\n").encode())
                self._stream_start("text/event-stream")
                return self._pipe(chat_mod.stream_chat(llm, cfg, prompts, body["messages"]), sse)
            if p.startswith("/api/convos/"):
                parts = p.split("/")  # /api/convos/<id> saves, /api/convos/<id>/delete deletes
                if len(parts) == 5 and parts[4] == "delete":
                    convos.delete(parts[3])
                    return self._send(200, {"ok": True})
                return self._send(200, convos.save(parts[3], body))
            if p == "/api/read_ahead":
                if cfg.get("read_ahead", True) and body.get("messages"):
                    threading.Thread(target=lambda: _quiet(chat_mod.read_ahead, llm, cfg, prompts, body["messages"]),
                                     daemon=True).start()
                return self._send(200, {"ok": True})
            if p in ("/v1/chat/completions", "/ollama/api/chat", "/ollama/api/generate"):
                return self._compat_post(p, body, cfg, llm)
            if p == "/api/devices":
                if access != "local":
                    return self._send(403, {"error": "only on the Mac itself"})
                if body.get("new_key"):
                    new_device_key()
                if "lan_access" in body:
                    new = load_config()
                    new["lan_access"] = bool(body["lan_access"])
                    save_config(new)
                    # the listening address only changes on restart; Forge.app starts it again in ~5 s
                    threading.Timer(0.5, lambda: os._exit(0)).start()
                return self._send(200, {"ok": True})
            if p == "/api/chat":
                j = start_job("chat", chat_mod.chat, llm, cfg, prompts, body["messages"])
                return self._send(200, {"job": j.id})
            if p == "/api/improve":
                text, path = body.get("text"), body.get("path") or None
                if path and not text:
                    if not allowed_path(path, cfg):
                        return self._send(403, {"error": "outside allowed_roots"})
                    with open(expand(path), errors="replace") as f:
                        text = f.read()
                j = start_job("improve", imp.improve, llm, cfg, prompts, text, body.get("goal", ""),
                              kind=body.get("kind", "skill"), n=body.get("n"), strategies=body.get("strategies"),
                              rounds=body.get("rounds"), path=path)
                return self._send(200, {"job": j.id})
            if p == "/api/workflow":
                j = start_job("workflow", imp.run_workflow, llm, cfg, prompts, body["id"], body.get("inputs", {}),
                              n=body.get("n"))
                return self._send(200, {"job": j.id})
            if p == "/api/apply":
                r = db().execute("SELECT result FROM runs WHERE id=?", (int(body["run_id"]),)).fetchone()
                res = json.loads(r["result"])
                text = res["variants"][int(body["variant"])]["text"]
                target = body.get("path") or res.get("path")
                if not target or ":" in target.split("/")[0]:
                    return self._send(400, {"error": "this run has no file path; copy the text instead"})
                if not allowed_path(target, cfg):
                    return self._send(403, {"error": "outside allowed_roots"})
                backup = backup_and_write(target, text if text.endswith("\n") else text + "\n")
                return self._send(200, {"written": expand(target), "backup": backup})
            if p == "/api/update":
                j = start_job("update", run_update, body.get("only"), bool(body.get("force", True)))
                return self._send(200, {"job": j.id})
            if p == "/api/restore":
                def restore(job, model):
                    if not llm.local_digest(model):
                        job.say("copying %s from the archive drive…" % model)
                        updater.restore_model(job, cfg, model)
                    new = load_config()
                    new["model"] = model
                    save_config(new)
                    job.say("active model is now %s" % model)
                    return {"model": model}
                j = start_job("restore", restore, body["model"])
                return self._send(200, {"job": j.id})
            if p == "/api/prompts/rollback":
                prompts.rollback(body["name"], body["version"])
                return self._send(200, {"ok": True})
            if p == "/api/config":
                allowed = {"model", "variants", "rounds", "max_model_gb", "switch_margin", "context_chunks"}
                new = load_config()
                for k, v in body.items():
                    if k in allowed:
                        new[k] = v
                save_config(new)
                return self._send(200, new)
            return self._send(404, {"error": "not found"})
        except Exception as e:
            return self._send(500, {"error": "%s: %s" % (type(e).__name__, e)})


def _quiet(fn, *a):
    try:
        fn(*a)
    except Exception:
        pass


def _now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _pair(self, body):
    now = time.time()
    _failed[:] = [t for t in _failed if now - t < 600]
    if len(_failed) >= 5:
        return self._send(429, {"error": "too many wrong codes; try again in 10 minutes"})
    if not hmac.compare_digest(str(body.get("code", "")).strip().encode(), pair_code().encode()):
        _failed.append(now)
        return self._send(403, {"error": "wrong code"})
    out = {"ok": True, "name": APP_NAME, "computer": _computer_name()}
    if body.get("app"):  # native apps keep the key themselves instead of using a browser cookie
        out["key"] = device_key()
    data = json.dumps(out).encode()
    self.send_response(200)
    self.send_header("Content-Type", "application/json")
    self.send_header("Content-Length", str(len(data)))
    self.send_header("Set-Cookie", "sl_key=%s; Path=/; Max-Age=31536000; HttpOnly; SameSite=Strict" % device_key())
    self.end_headers()
    self.wfile.write(data)


def _compat_get(self, path):
    """Just enough of the OpenAI and Ollama APIs for apps like Enchanted (iPhone/iPad/Mac) and Shortcuts."""
    cfg, llm = ctx()
    if path == "/v1/models":
        return self._send(200, {"object": "list", "data": [{"id": MODEL_ID, "object": "model", "created": 0,
                                                            "owned_by": "local"}]})
    if path in ("/ollama", "/ollama/"):
        return self._send(200, b"Ollama is running", "text/plain")
    if path == "/ollama/api/version":
        return self._send(200, {"version": llm.version() or "0"})
    base = next((m for m in llm.tags() if m["name"] == cfg["model"]), None) or {}
    details = base.get("details") or {"parent_model": "", "format": "gguf", "family": "", "families": [],
                                      "parameter_size": "", "quantization_level": ""}
    return self._send(200, {"models": [{"name": MODEL_ID + ":latest", "model": MODEL_ID + ":latest",
                                        "modified_at": base.get("modified_at") or _now_iso(),
                                        "size": base.get("size", 0), "digest": base.get("digest", "0"),
                                        "details": details}]})


def _compat_post(self, path, body, cfg, llm):
    messages = body.get("messages")
    if path == "/ollama/api/generate":
        messages = ([{"role": "system", "content": body["system"]}] if body.get("system") else []) + \
                   [{"role": "user", "content": body.get("prompt", "")}]
    # some apps send OpenAI "content parts" lists; keep the text parts
    for m in messages:
        if isinstance(m.get("content"), list):
            m["content"] = "\n".join(part.get("text", "") for part in m["content"] if isinstance(part, dict))
    events = chat_mod.stream_chat(llm, cfg, prompts, messages)
    model_name = body.get("model") or MODEL_ID
    stream = body.get("stream", path != "/v1/chat/completions")  # Ollama streams by default, OpenAI doesn't
    if not stream:
        done = {}
        self._pipe(events, lambda ev: done.update(ev) if ev["type"] == "done" else None)
        text = done.get("content", "")
        if path == "/v1/chat/completions":
            return self._send(200, {"id": "chatcmpl-%d" % int(time.time() * 1000), "object": "chat.completion",
                                    "created": int(time.time()), "model": model_name,
                                    "choices": [{"index": 0, "finish_reason": "stop",
                                                 "message": {"role": "assistant", "content": text}}]})
        key = "response" if path.endswith("generate") else "message"
        return self._send(200, {"model": model_name, "created_at": _now_iso(), "done": True, "done_reason": "stop",
                                key: text if key == "response" else {"role": "assistant", "content": text}})
    if path == "/v1/chat/completions":
        cid, created = "chatcmpl-%d" % int(time.time() * 1000), int(time.time())

        def write(ev):
            if ev["type"] not in ("token", "done"):
                return
            delta = {"content": ev["text"]} if ev["type"] == "token" else {}
            chunk = {"id": cid, "object": "chat.completion.chunk", "created": created, "model": model_name,
                     "choices": [{"index": 0, "delta": delta,
                                  "finish_reason": "stop" if ev["type"] == "done" else None}]}
            self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
            if ev["type"] == "done":
                self.wfile.write(b"data: [DONE]\n\n")
        self._stream_start("text/event-stream")
        return self._pipe(events, write)
    gen = path.endswith("generate")

    def write(ev):
        if ev["type"] not in ("token", "done"):
            return
        out = {"model": model_name, "created_at": _now_iso(), "done": ev["type"] == "done"}
        piece = ev.get("text", "") if ev["type"] == "token" else ""
        if gen:
            out["response"] = piece
        else:
            out["message"] = {"role": "assistant", "content": piece}
        if ev["type"] == "done":
            out["done_reason"] = "stop"
            out["total_duration"] = int(ev.get("secs", 0) * 1e9)
        self.wfile.write((json.dumps(out) + "\n").encode())
    self._stream_start("application/x-ndjson")
    return self._pipe(events, write)


Handler._pair = _pair
Handler._compat_get = _compat_get
Handler._compat_post = _compat_post
SERVER = {}


def scheduler():
    """Every 30 min: run whatever update task is due, unless the user is busy (a job, or chatted <15 min ago)."""
    from .common import NullJob, log_event
    time.sleep(120)  # let the machine settle after login
    while True:
        busy = any(j.status == "running" for j in JOBS.values()) or time.time() - ACTIVE["last_chat"] < 900
        if not busy and _update_lock.acquire(blocking=False):
            try:
                updater.run(job=NullJob())
            except Exception as e:
                log_event("error", "scheduled update failed: %s" % e)
            finally:
                _update_lock.release()
        time.sleep(1800)


class DualStackServer(ThreadingHTTPServer):
    """Listens on IPv4 and IPv6 (iPhones often reach Mac.local over IPv6)."""
    address_family = socket.AF_INET6
    daemon_threads = True
    request_queue_size = 64  # a phone opening the app fires ~8 requests at once; the default queue is 5

    def server_bind(self):
        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        super().server_bind()


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 64


def warm_up():
    """Load the model and the skill index right away, so the first question is not the slow one."""
    cfg, llm = ctx()
    _quiet(llm.warm, cfg["model"])
    _quiet(skills.load, llm, cfg)


def main():
    cfg = load_config()
    llm = Ollama(cfg["ollama_url"])
    llm.ensure_running(wait=20)
    if "--no-scheduler" not in sys.argv:
        threading.Thread(target=scheduler, daemon=True).start()
    threading.Thread(target=warm_up, daemon=True).start()
    port = int(os.environ.get("FORGE_PORT", cfg.get("port", 8777)))
    advertise(port, bool(cfg.get("lan_access")))
    if cfg.get("lan_access"):
        srv = DualStackServer(("::", port), Handler)
        SERVER["lan"] = True
        device_key()
        print("%s running at http://127.0.0.1:%d and on your Wi-Fi: %s" % (APP_NAME, port, ", ".join(lan_urls(port))),
              flush=True)
    else:
        srv = LocalServer(("127.0.0.1", port), Handler)
        print("%s running at http://127.0.0.1:%d" % (APP_NAME, port), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
