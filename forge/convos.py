"""Saved conversations, shared by every app (Mac app, iPhone, Android, web), kept in data/convos/ on this Mac."""
import json
import os
import re
import threading
import time

from .common import DATA

DIR = os.path.join(DATA, "convos")
ID = re.compile(r"^[A-Za-z0-9_-]{6,64}$")
MAX_BYTES = 2_000_000
_lock = threading.Lock()


def _dir(guest=None):
    """Your chats live in data/convos; each invited guest gets a separate folder they alone can see."""
    return os.path.join(DIR, "guests", guest) if guest else DIR


def _path(cid, guest=None):
    if not ID.match(cid or ""):
        raise ValueError("bad conversation id")
    return os.path.join(_dir(guest), cid + ".json")


def _title(messages):
    first = next((m.get("content", "") for m in messages if m.get("role") == "user"), "")
    first = re.sub(r"\s+", " ", first).strip()
    return (first[:57] + "…") if len(first) > 60 else (first or "New chat")


def listing(limit=300, guest=None):
    out = []
    d0 = _dir(guest)
    if os.path.isdir(d0):
        for name in os.listdir(d0):
            if not name.endswith(".json"):
                continue
            try:
                with open(os.path.join(d0, name)) as f:
                    d = json.load(f)
                last = next((m.get("content", "") for m in reversed(d.get("messages", []))
                             if m.get("role") == "assistant"), "")
                out.append({"id": d["id"], "title": d.get("title") or "New chat", "updated": d.get("updated", 0),
                            "count": len(d.get("messages", [])), "preview": re.sub(r"\s+", " ", last)[:120]})
            except (OSError, ValueError, KeyError):
                continue
    out.sort(key=lambda d: d["updated"], reverse=True)
    return out[:limit]


def get(cid, guest=None):
    try:
        with open(_path(cid, guest)) as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def save(cid, body, guest=None):
    messages = [{k: m[k] for k in ("role", "content", "meta") if k in m}
                for m in body.get("messages", []) if m.get("role") in ("user", "assistant")
                and isinstance(m.get("content"), str)]
    d = {"id": cid, "title": (body.get("title") or "").strip()[:80] or _title(messages),
         "updated": time.time(), "messages": messages}
    data = json.dumps(d, ensure_ascii=False)
    if len(data) > MAX_BYTES:
        raise ValueError("conversation is too long to save (2 MB limit)")
    with _lock:
        os.makedirs(_dir(guest), exist_ok=True)
        tmp = _path(cid, guest) + ".tmp"
        with open(tmp, "w") as f:
            f.write(data)
        os.replace(tmp, _path(cid, guest))
    return {k: d[k] for k in ("id", "title", "updated")}


def delete(cid, guest=None):
    try:
        os.remove(_path(cid, guest))
    except FileNotFoundError:
        pass
