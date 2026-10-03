"""Shared plumbing: paths, config, SQLite store, event log, background jobs."""
import json
import os
import sqlite3
import threading
import time
import traceback
import uuid
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
PROMPTS = os.path.join(ROOT, "prompts")
OUTPUTS = os.path.join(ROOT, "outputs")
for _d in (DATA, OUTPUTS, os.path.join(DATA, "backups"), os.path.join(PROMPTS, "history")):
    os.makedirs(_d, exist_ok=True)


def now():
    return datetime.now().isoformat(timespec="seconds")


def expand(p):
    p = os.path.expanduser(p)
    return os.path.abspath(p if os.path.isabs(p) else os.path.join(ROOT, p))  # relative = inside this folder


# ---------------------------------------------------------------- config / state

DEFAULTS = {
    "keep_alive": "60m",          # keep the model in memory this long after the last question
    "chat_notes": 3,              # notes from your files added to each question
    "chat_context_chars": 3500,   # ...capped at this size (every token costs time on a small Mac)
    "chat_history": 12,
    "skills_enabled": True,
    "skill_threshold": 0.62,
    "lan_access": False,          # true: iPhone/iPad/other Macs on your Wi-Fi can use it after pairing
    "house_rules_trigger": "",
    "read_ahead": True,           # start reading a question while it is being typed (web app)
}


def load_config():
    path = os.path.join(ROOT, "config.json")
    if not os.path.exists(path):  # fresh clone: start from the example
        with open(os.path.join(ROOT, "config.example.json")) as f, open(path, "w") as out:
            out.write(f.read())
    with open(path) as f:
        cfg = dict(DEFAULTS)
        cfg.update(json.load(f))
        return cfg


def save_config(cfg):
    path = os.path.join(ROOT, "config.json")
    with open(path + ".tmp", "w") as f:
        json.dump(cfg, f, indent=2)
    os.replace(path + ".tmp", path)


STATE_PATH = os.path.join(DATA, "state.json")
_state_lock = threading.Lock()


def load_state():
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def update_state(**kw):
    with _state_lock:
        s = load_state()
        s.update(kw)
        with open(STATE_PATH + ".tmp", "w") as f:
            json.dump(s, f, indent=2)
        os.replace(STATE_PATH + ".tmp", STATE_PATH)
        return s


# ---------------------------------------------------------------- database

DB_PATH = os.path.join(DATA, "forge.db")
_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (path TEXT PRIMARY KEY, source TEXT, mtime REAL, size INT, indexed TEXT);
CREATE TABLE IF NOT EXISTS chunks (id INTEGER PRIMARY KEY, path TEXT, ord INT, text TEXT, emb BLOB);
CREATE INDEX IF NOT EXISTS chunks_path ON chunks(path);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(text, content='chunks', content_rowid='id');
CREATE TABLE IF NOT EXISTS lessons (path TEXT PRIMARY KEY, created TEXT, text TEXT);
CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY, created TEXT, kind TEXT, target TEXT, goal TEXT, result TEXT);
CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, created TEXT, kind TEXT, message TEXT);
CREATE TABLE IF NOT EXISTS model_scores (model TEXT, digest TEXT, created TEXT, score REAL, tps REAL, detail TEXT,
                                         PRIMARY KEY (model, digest));
"""


def db():
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        _local.conn = conn
    return conn


def log_event(kind, message):
    c = db()
    c.execute("INSERT INTO events (created, kind, message) VALUES (?,?,?)", (now(), kind, message))
    c.commit()
    print("[%s] %s: %s" % (now(), kind, message), flush=True)


# ---------------------------------------------------------------- background jobs

JOBS = {}
_jobs_lock = threading.Lock()


class Job:
    def __init__(self, kind):
        self.id = uuid.uuid4().hex[:10]
        self.kind = kind
        self.status = "running"
        self.log = []
        self.result = None
        self.error = None
        self.started = time.time()

    def say(self, msg):
        self.log.append("%5.0fs  %s" % (time.time() - self.started, msg))

    def to_dict(self):
        return {"id": self.id, "kind": self.kind, "status": self.status, "log": self.log[-80:],
                "result": self.result, "error": self.error, "elapsed": round(time.time() - self.started)}


def start_job(kind, fn, *args, **kw):
    """Run fn(job, *args) in a thread; the UI polls /api/job/<id>."""
    job = Job(kind)
    with _jobs_lock:
        JOBS[job.id] = job
        # forget finished jobs older than an hour
        for jid in [j for j, v in JOBS.items() if v.status != "running" and time.time() - v.started > 3600]:
            JOBS.pop(jid, None)

    def run():
        try:
            job.result = fn(job, *args, **kw)
            job.status = "done"
        except Exception as e:  # surface the error to the UI instead of dying silently
            job.error = "%s: %s" % (type(e).__name__, e)
            job.say(traceback.format_exc(limit=3))
            job.status = "error"
        finally:
            if getattr(_local, "conn", None) is not None:
                _local.conn.close()
                _local.conn = None

    threading.Thread(target=run, daemon=True).start()
    return job


class NullJob:
    """Used when running from the command line (updater) — prints instead of storing."""
    def say(self, msg):
        print("  " + msg, flush=True)


# ---------------------------------------------------------------- file safety

def allowed_path(path, cfg, write=False):
    """Reads are allowed under allowed_roots; writes only there too, never outside."""
    p = expand(path)
    roots = [expand(r) for r in cfg.get("allowed_roots", [])] + [ROOT]
    return any(p == r or p.startswith(r + os.sep) for r in roots)


def backup_and_write(path, content):
    path = expand(path)
    if os.path.exists(path):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        dest = os.path.join(DATA, "backups", stamp + "__" + path.strip("/").replace("/", "__"))
        with open(path, "rb") as src, open(dest, "wb") as dst:
            dst.write(src.read())
    else:
        dest = None
        os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    return dest
