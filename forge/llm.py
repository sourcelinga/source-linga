"""Minimal Ollama client (stdlib only) plus Ollama-registry lookups for update checks."""
import json
import re
import subprocess
import time
import urllib.error
import urllib.request

REGISTRY = "https://registry.ollama.ai/v2/library/%s/manifests/%s"
THINK_RE = re.compile(r"<think>.*?</think>\s*", re.S)


class OllamaError(RuntimeError):
    pass


class Ollama:
    def __init__(self, url="http://127.0.0.1:11434", num_ctx=16384, keep_alive="20m"):
        self.url = url.rstrip("/")
        self.keep_alive = keep_alive  # how long Ollama keeps the model in memory after the last request
        # One context size for every call: a different num_ctx forces Ollama to reload the model.
        self.num_ctx = num_ctx

    # -- transport
    def _post(self, path, body, timeout=900):
        req = urllib.request.Request(self.url + path, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise OllamaError("%s %s: %s" % (path, e.code, e.read().decode(errors="replace")[:300]))
        except urllib.error.URLError as e:
            raise OllamaError("Ollama is not reachable at %s (%s)" % (self.url, e.reason))

    def _get(self, path, timeout=10):
        with urllib.request.urlopen(self.url + path, timeout=timeout) as r:
            return json.loads(r.read())

    # -- health
    def up(self):
        try:
            self._get("/api/version", timeout=3)
            return True
        except Exception:
            return False

    def ensure_running(self, wait=40):
        if self.up():
            return True
        if subprocess.run(["open", "-g", "-a", "Ollama"], capture_output=True).returncode != 0:
            subprocess.run(["open", "-g", "/Applications/Ollama.app"], capture_output=True)
        for _ in range(wait):
            time.sleep(1)
            if self.up():
                return True
        return False

    def version(self):
        try:
            return self._get("/api/version").get("version")
        except Exception:
            return None

    # -- models
    def tags(self):
        try:
            return self._get("/api/tags").get("models", [])
        except Exception:
            return []

    def local_digest(self, model):
        name = normalize(model)
        for m in self.tags():
            if normalize(m["name"]) == name:
                return m.get("digest")
        return None

    def pull(self, model, say=None):
        """Streamed pull so progress can be reported."""
        req = urllib.request.Request(self.url + "/api/pull", data=json.dumps({"model": model, "stream": True}).encode(),
                                     headers={"Content-Type": "application/json"})
        last = 0
        with urllib.request.urlopen(req, timeout=7200) as r:
            for line in r:
                if not line.strip():
                    continue
                ev = json.loads(line)
                if ev.get("error"):
                    raise OllamaError("pull %s: %s" % (model, ev["error"]))
                if say and ev.get("total") and ev.get("completed"):
                    pct = int(100 * ev["completed"] / ev["total"])
                    if pct >= last + 10:
                        last = pct
                        say("pull %s: %d%% of %.1f GB" % (model, pct, ev["total"] / 1e9))
                elif say and ev.get("status") and "pulling" not in ev["status"]:
                    say("pull %s: %s" % (model, ev["status"]))

    def delete(self, model):
        req = urllib.request.Request(self.url + "/api/delete", data=json.dumps({"model": model}).encode(),
                                     headers={"Content-Type": "application/json"}, method="DELETE")
        urllib.request.urlopen(req, timeout=60).read()

    # -- inference
    def chat(self, model, messages, tools=None, temperature=0.4, fmt=None, timeout=900):
        body = {"model": model, "messages": messages, "stream": False, "think": False, "keep_alive": self.keep_alive,
                "options": {"temperature": temperature, "num_ctx": self.num_ctx}}
        if tools:
            body["tools"] = tools
        if fmt is not None:
            body["format"] = fmt
        try:
            r = self._post("/api/chat", body, timeout=timeout)
        except OllamaError as e:
            if "think" in str(e):  # model without a thinking switch
                body.pop("think")
                r = self._post("/api/chat", body, timeout=timeout)
            else:
                raise
        msg = r.get("message", {})
        msg["content"] = THINK_RE.sub("", msg.get("content") or "").strip()
        dur = (r.get("eval_duration") or 0) / 1e9
        msg["_tps"] = round(r.get("eval_count", 0) / dur, 1) if dur else None
        return msg

    def chat_stream(self, model, messages, tools=None, temperature=0.4, timeout=900, options=None, on_open=None):
        """Yields ("token", text) while the answer is written, then ("done", message) with tool_calls and stats.
        on_open(response) receives the live HTTP response, so another thread can cancel it."""
        body = {"model": model, "messages": messages, "stream": True, "think": False, "keep_alive": self.keep_alive,
                "options": dict({"temperature": temperature, "num_ctx": self.num_ctx}, **(options or {}))}
        if tools:
            body["tools"] = tools
        req = urllib.request.Request(self.url + "/api/chat", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            r = urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as e:
            err = e.read().decode(errors="replace")[:300]
            if "think" not in err:
                raise OllamaError("/api/chat %s: %s" % (e.code, err))
            body.pop("think")  # model without a thinking switch
            req.data = json.dumps(body).encode()
            r = urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.URLError as e:
            raise OllamaError("Ollama is not reachable at %s (%s)" % (self.url, e.reason))
        content, calls, thinking = [], [], False
        with r:
            for line in r:
                if not line.strip():
                    continue
                ev = json.loads(line)
                if ev.get("error"):
                    raise OllamaError(ev["error"])
                m = ev.get("message") or {}
                calls += m.get("tool_calls") or []
                piece = m.get("content") or ""
                # models that ignore think:false wrap reasoning in <think>…</think>; never show it
                if "<think>" in piece:
                    thinking = True
                if thinking:
                    if "</think>" in piece:
                        thinking, piece = False, piece.split("</think>", 1)[1].lstrip()
                    else:
                        piece = ""
                if piece:
                    content.append(piece)
                    yield "token", piece
                if ev.get("done"):
                    dur = (ev.get("eval_duration") or 0) / 1e9
                    yield "done", {"role": "assistant", "content": THINK_RE.sub("", "".join(content)).strip(),
                                   "tool_calls": calls,
                                   "_tps": round(ev.get("eval_count", 0) / dur, 1) if dur else None,
                                   "_prompt_tokens": ev.get("prompt_eval_count", 0),
                                   "_prompt_secs": round((ev.get("prompt_eval_duration") or 0) / 1e9, 2)}

    def warm(self, model):
        """Load the model into memory now so the first question doesn't pay the load time."""
        self._post("/api/generate", {"model": model, "keep_alive": self.keep_alive}, timeout=120)

    def complete(self, model, system, user, **kw):
        msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": user}]
        return self.chat(model, msgs, **kw)["content"]

    def json(self, model, system, user, schema, **kw):
        out = self.complete(model, system, user, fmt=schema, temperature=0.1, **kw)
        try:
            return json.loads(out)
        except ValueError:
            m = re.search(r"\{.*\}", out, re.S)
            return json.loads(m.group(0)) if m else {}

    def embed(self, model, texts):
        out = []
        for i in range(0, len(texts), 32):
            r = self._post("/api/embed", {"model": model, "input": texts[i:i + 32], "truncate": True})
            out.extend(r["embeddings"])
        return out


def normalize(model):
    return model if ":" in model else model + ":latest"


def remote_manifest(model):
    """Returns (digest-ish fingerprint, size_bytes) from the public registry, or (None, None)."""
    name, tag = normalize(model).split(":", 1)
    req = urllib.request.Request(REGISTRY % (name, tag),
                                 headers={"Accept": "application/vnd.docker.distribution.manifest.v2+json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
            d = json.loads(raw)
    except Exception:
        return None, None
    layers = d.get("layers") or []
    if not layers:
        return None, None
    import hashlib
    return hashlib.sha256(raw).hexdigest(), sum(l.get("size", 0) for l in layers)
