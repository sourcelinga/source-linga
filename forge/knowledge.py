"""Knowledge index: your skills, memory, project files and Claude Code transcripts.

Hybrid search = SQLite FTS5 (exact words, lot codes, file names) fused with
embedding similarity (meaning). Incremental: only changed files are re-embedded.
"""
import fnmatch
import glob
import json
import math
import os
from array import array

from .common import db, expand, log_event, now

CHUNK = 1400
OVERLAP = 200
TRANSCRIPT_PREFIX = "transcript:"

_vec_cache = {"rows": None}


# ---------------------------------------------------------------- source discovery

def _matches(name, patterns):
    return any(fnmatch.fnmatch(name, p) for p in patterns)


def iter_source_files(cfg):
    max_bytes = cfg.get("max_file_kb", 160) * 1024
    seen = set()
    for src in cfg["sources"]:
        base = expand(src["path"])
        include = src.get("include", ["*"])
        exclude = src.get("exclude", [])
        if os.path.isfile(base):
            candidates = [base]
        elif os.path.isdir(base):
            candidates = []
            for dirpath, dirnames, filenames in os.walk(base):
                dirnames[:] = [d for d in dirnames if not d.startswith(".") and not _matches(d, exclude)]
                for fn in filenames:
                    if _matches(fn, include) and not _matches(fn, exclude):
                        candidates.append(os.path.join(dirpath, fn))
        else:
            continue
        for p in candidates:
            if p in seen:
                continue
            try:
                st = os.stat(p)
            except OSError:
                continue
            if 0 < st.st_size <= max_bytes:
                seen.add(p)
                yield p, src["path"], st.st_mtime, st.st_size


def iter_transcripts(cfg):
    t = cfg.get("transcripts")
    if not t:
        return []
    files = glob.glob(os.path.join(expand(t["path"]), "*", "*.jsonl"))
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return files[: t.get("max_files", 80)]


def condense_transcript(path, limit=60000):
    """Keep what shows *how work was done*: user requests, assistant text, tool calls, tool errors."""
    out = []
    try:
        fh = open(path, errors="replace")
    except OSError:
        return ""
    with fh:
        for line in fh:
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            msg = ev.get("message") or {}
            role = msg.get("role") or ev.get("type")
            content = msg.get("content")
            if isinstance(content, str):
                if role == "user" and not content.startswith("<"):
                    out.append("USER: " + content[:1500])
                continue
            for block in content or []:
                if not isinstance(block, dict):
                    continue
                kind = block.get("type")
                if kind == "text" and block.get("text"):
                    txt = block["text"]
                    if role == "user" and txt.lstrip().startswith("<system-reminder>"):
                        continue
                    out.append(("USER: " if role == "user" else "AI: ") + txt[:1500])
                elif kind == "tool_use":
                    inp = block.get("input") or {}
                    hint = inp.get("description") or inp.get("command") or inp.get("file_path") or inp.get("query") or ""
                    out.append("TOOL %s: %s" % (block.get("name"), str(hint)[:200]))
                elif kind == "tool_result" and block.get("is_error"):
                    c = block.get("content")
                    if isinstance(c, list):
                        c = " ".join(x.get("text", "") for x in c if isinstance(x, dict))
                    out.append("TOOL ERROR: " + str(c)[:300])
    text = "\n".join(out)
    if len(text) > limit:  # keep the beginning (the ask) and the end (how it finished)
        text = text[: limit // 2] + "\n...\n" + text[-limit // 2:]
    return text


# ---------------------------------------------------------------- chunking / vectors

def chunk_text(text, path):
    head = "FILE: %s\n" % path
    if len(text) <= CHUNK:
        return [head + text]
    chunks, i = [], 0
    while i < len(text):
        end = min(len(text), i + CHUNK)
        nl = text.rfind("\n", i + CHUNK // 2, end)  # prefer to cut at a line break
        if nl > 0 and end < len(text):
            end = nl
        chunks.append(head + text[i:end])
        if end >= len(text):
            break
        i = max(end - OVERLAP, i + 1)
    return chunks


def _norm(v):
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return array("f", (x / n for x in v))


def _store(path, source, mtime, size, text, llm, cfg):
    c = db()
    old = [r["id"] for r in c.execute("SELECT id FROM chunks WHERE path=?", (path,))]
    for cid in old:
        row = c.execute("SELECT text FROM chunks WHERE id=?", (cid,)).fetchone()
        c.execute("INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES('delete', ?, ?)", (cid, row["text"]))
    c.execute("DELETE FROM chunks WHERE path=?", (path,))
    pieces = chunk_text(text, path) if text.strip() else []
    vecs = llm.embed(cfg["embed_model"], pieces) if pieces else []
    for i, (piece, vec) in enumerate(zip(pieces, vecs)):
        cur = c.execute("INSERT INTO chunks (path, ord, text, emb) VALUES (?,?,?,?)",
                        (path, i, piece, _norm(vec).tobytes()))
        c.execute("INSERT INTO chunks_fts(rowid, text) VALUES (?,?)", (cur.lastrowid, piece))
    c.execute("INSERT OR REPLACE INTO files (path, source, mtime, size, indexed) VALUES (?,?,?,?,?)",
              (path, source, mtime, size, now()))
    c.commit()
    return len(pieces)


def _forget(path):
    c = db()
    for r in c.execute("SELECT id, text FROM chunks WHERE path=?", (path,)).fetchall():
        c.execute("INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES('delete', ?, ?)", (r["id"], r["text"]))
    c.execute("DELETE FROM chunks WHERE path=?", (path,))
    c.execute("DELETE FROM files WHERE path=?", (path,))
    c.commit()


def refresh(job, llm, cfg):
    """Index new/changed files, drop deleted ones. Returns counts."""
    c = db()
    known = {r["path"]: r["mtime"] for r in c.execute("SELECT path, mtime FROM files")}
    current, changed = {}, []
    for path, source, mtime, size in iter_source_files(cfg):
        current[path] = 1
        if known.get(path) != mtime:
            changed.append((path, source, mtime, size))
    for tpath in iter_transcripts(cfg):
        key = TRANSCRIPT_PREFIX + tpath
        current[key] = 1
        mtime = os.path.getmtime(tpath)
        if known.get(key) != mtime:
            changed.append((key, "transcripts", mtime, os.path.getsize(tpath)))
    removed = [p for p in known if p not in current and not p.startswith("lesson:")]
    for p in removed:
        _forget(p)
    job.say("index: %d changed, %d removed, %d total sources" % (len(changed), len(removed), len(current)))
    n_chunks = 0
    for i, (path, source, mtime, size) in enumerate(changed):
        if path.startswith(TRANSCRIPT_PREFIX):
            text = condense_transcript(path[len(TRANSCRIPT_PREFIX):])
        else:
            try:
                with open(path, errors="replace") as f:
                    text = f.read()
            except OSError:
                continue
        n_chunks += _store(path, source, mtime, size, text, llm, cfg)
        if i % 25 == 0:
            job.say("index: %d/%d files (%s)" % (i + 1, len(changed), os.path.basename(path)))
    _vec_cache["rows"] = None
    if changed or removed:
        log_event("knowledge", "indexed %d files (%d chunks), removed %d" % (len(changed), n_chunks, len(removed)))
    return {"changed": len(changed), "removed": len(removed), "chunks": n_chunks}


# ---------------------------------------------------------------- search

def _vectors():
    if _vec_cache["rows"] is None:
        rows = []
        for r in db().execute("SELECT id, emb FROM chunks"):
            a = array("f")
            a.frombytes(r["emb"])
            rows.append((r["id"], a))
        _vec_cache["rows"] = rows
    return _vec_cache["rows"]


def _fts_query(q):
    words = [w for w in "".join(ch if ch.isalnum() else " " for ch in q).split() if len(w) > 2]
    return " OR ".join('"%s"' % w for w in words[:12])


def search(query, llm, cfg, k=6, exclude_transcripts=False):
    c = db()
    ranks = {}
    # meaning
    try:
        qv = _norm(llm.embed(cfg["embed_model"], [query])[0])
        scored = sorted(((sum(a * b for a, b in zip(qv, v)), cid) for cid, v in _vectors()), reverse=True)[:40]
        for rank, (_, cid) in enumerate(scored):
            ranks[cid] = ranks.get(cid, 0) + 1.0 / (60 + rank)
    except Exception:
        pass
    # exact words
    fq = _fts_query(query)
    if fq:
        for rank, r in enumerate(c.execute(
                "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY rank LIMIT 40", (fq,))):
            ranks[r["rowid"]] = ranks.get(r["rowid"], 0) + 1.0 / (60 + rank)
    out = []
    for cid in sorted(ranks, key=ranks.get, reverse=True):
        r = c.execute("SELECT path, text FROM chunks WHERE id=?", (cid,)).fetchone()
        if not r or (exclude_transcripts and r["path"].startswith(TRANSCRIPT_PREFIX)):
            continue
        out.append({"path": r["path"], "text": r["text"], "score": round(ranks[cid] * 1000, 2)})
        if len(out) >= k:
            break
    return out


def context_block(hits, max_chars=9000):
    parts, used = [], 0
    for h in hits:
        t = h["text"][:2500]
        if used + len(t) > max_chars:
            break
        parts.append(t)
        used += len(t)
    return "\n\n---\n\n".join(parts)


def stats():
    c = db()
    return {
        "files": c.execute("SELECT COUNT(*) FROM files WHERE path NOT LIKE 'transcript:%' AND path NOT LIKE 'lesson:%'").fetchone()[0],
        "transcripts": c.execute("SELECT COUNT(*) FROM files WHERE path LIKE 'transcript:%'").fetchone()[0],
        "chunks": c.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
        "lessons": c.execute("SELECT COUNT(*) FROM lessons").fetchone()[0],
    }


def list_targets(q=""):
    """Files the Improve tab can load (skills, memory, workflows, code)."""
    c = db()
    rows = c.execute("SELECT path FROM files WHERE path NOT LIKE 'transcript:%' AND path NOT LIKE 'lesson:%' AND path LIKE ? ORDER BY path LIMIT 300",
                     ("%" + q + "%",)).fetchall()
    return [r["path"] for r in rows]


# ---------------------------------------------------------------- lessons from past sessions

LESSON_SCHEMA = {
    "type": "object",
    "properties": {
        "task": {"type": "string"},
        "worked": {"type": "array", "items": {"type": "string"}},
        "failed": {"type": "array", "items": {"type": "string"}},
        "user_corrections": {"type": "array", "items": {"type": "string"}},
        "better_next_time": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["task", "worked", "failed", "user_corrections", "better_next_time"],
}


def extract_lessons(job, llm, cfg, prompts, limit=5):
    """Distil new transcripts into reusable lessons (what worked / failed / what the user corrected)."""
    import time
    from datetime import datetime
    c = db()
    done = {r["path"]: r["created"] for r in c.execute("SELECT path, created FROM lessons")}

    def needs(p):
        mtime = os.path.getmtime(p)
        if time.time() - mtime < 3 * 3600:  # session still active: wait until it's finished
            return False
        if p not in done:
            return True
        # re-distil if the session continued well after its lesson was written
        return mtime - datetime.fromisoformat(done[p]).timestamp() > 6 * 3600

    todo = [p for p in iter_transcripts(cfg) if needs(p)][:limit]
    for p in todo:
        text = condense_transcript(p, limit=30000)
        if len(text) < 400:
            c.execute("INSERT OR REPLACE INTO lessons VALUES (?,?,?)", (p, now(), ""))
            c.commit()
            continue
        job.say("lessons: reading %s" % os.path.basename(p))
        data = llm.json(cfg["model"], prompts.get("lessons"), text[:30000], LESSON_SCHEMA)
        lines = ["LESSON from session %s" % os.path.basename(p), "Task: " + data.get("task", "")]
        for key, label in (("worked", "Worked"), ("failed", "Failed"), ("user_corrections", "User corrected"),
                           ("better_next_time", "Do better")):
            for item in data.get(key, []) or []:
                lines.append("- %s: %s" % (label, item))
        lesson = "\n".join(lines)
        c.execute("INSERT OR REPLACE INTO lessons VALUES (?,?,?)", (p, now(), lesson))
        c.commit()
        _store("lesson:" + p, "lessons", os.path.getmtime(p), len(lesson), lesson, llm, cfg)
    _vec_cache["rows"] = None
    if todo:
        log_event("lessons", "distilled %d transcript(s)" % len(todo))
    return len(todo)
