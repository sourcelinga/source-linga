"""Skill router: picks the one skill card (skills/<name>/SKILL.md) that fits a request.

Matching is by meaning: each skill's description is embedded once, the request is
embedded per turn, and the best skill is used only if it is clearly relevant.
Only one card is injected, so the prompt stays small (a 9B model reads ~150 tokens/s).
"""
import os
import re
import threading

from .common import ROOT

SKILLS_DIR = os.path.join(ROOT, "skills")
LOCAL_SKILLS_DIR = os.path.join(ROOT, "local", "skills")
_cache = {"key": None, "skills": []}
_lock = threading.Lock()


def _parse(path):
    with open(path) as f:
        raw = f.read()
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.S)
    meta, body = {}, raw
    if m:
        body = m.group(2).strip()
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
    name = meta.get("name") or os.path.basename(os.path.dirname(path))
    triggers = [t.strip().lower() for t in meta.get("triggers", "").split(",") if t.strip()]
    boost = float(meta["trigger_boost"]) if meta.get("trigger_boost") else None
    return {"name": name, "description": meta.get("description", ""), "source": meta.get("source", ""),
            "triggers": triggers, "trigger_boost": boost, "body": body, "path": path}


def skill_files():
    out = []
    for d in (SKILLS_DIR, LOCAL_SKILLS_DIR):  # local/skills is private and overrides a shipped skill of the same name
        if os.path.isdir(d):
            for name in sorted(os.listdir(d)):
                p = os.path.join(d, name, "SKILL.md")
                if os.path.isfile(p):
                    out.append(p)
    return out


def load(llm, cfg):
    """Skills with their description vectors; re-embedded only when a file or the embedder changes."""
    files = skill_files()
    key = (cfg["embed_model"],) + tuple((p, os.path.getmtime(p)) for p in files)
    with _lock:
        if _cache["key"] != key:
            by_name = {}
            for p in files:
                s = _parse(p)
                by_name[s["name"]] = s
            skills = list(by_name.values())
            if skills:
                vecs = llm.embed(cfg["embed_model"],
                                 ["search_document: %s. %s" % (s["name"].replace("-", " "), s["description"])
                                  for s in skills])
                for s, v in zip(skills, vecs):
                    s["vec"] = _norm(v)
            _cache.update(key=key, skills=skills)
        return _cache["skills"]


def _norm(v):
    n = sum(x * x for x in v) ** 0.5 or 1.0
    return [x / n for x in v]


def rank(text, llm, cfg):
    skills = load(llm, cfg)
    if not skills or not text.strip():
        return []
    q = _norm(llm.embed(cfg["embed_model"], ["search_query: " + text[:2000]])[0])
    low = " " + re.sub(r"\s+", " ", text[:600].lower()) + " "
    boost = cfg.get("skill_trigger_boost", 0.1)

    def score(s):  # meaning + a bonus for each trigger phrase in the request (at most two count)
        hits = sum(1 for t in s["triggers"] if re.search(r"(?<![\w])" + re.escape(t) + r"(?:s|es)?(?![\w])", low))
        return round(sum(a * b for a, b in zip(q, s["vec"])) + (s["trigger_boost"] or boost) * min(hits, 2), 3)
    return sorted(((score(s), s) for s in skills), key=lambda x: x[0], reverse=True)


def match(text, llm, cfg):
    """The best skill for this request, or None when nothing fits well enough."""
    if not cfg.get("skills_enabled", True):
        return None
    try:
        ranked = rank(text, llm, cfg)
    except Exception:
        return None  # the embedder being down must never break chat
    if not ranked:
        return None
    best_score, best = ranked[0]
    margin = best_score - (ranked[1][0] if len(ranked) > 1 else 0)
    if best_score >= cfg.get("skill_threshold", 0.62) and margin >= cfg.get("skill_margin", 0.02):
        return best
    return None


def block(skill):
    return "SKILL TO APPLY (%s):\n%s" % (skill["name"], skill["body"])


def listing():
    return [{k: s[k] for k in ("name", "description", "triggers", "source", "path")} for s in map(_parse, skill_files())]
