"""Objective test suite. Used to (1) compare models before switching, and
(2) accept a self-rewritten prompt only if it measurably scores higher.
Checks are deterministic (string/regex/JSON/code tests), so the AI can't talk its way to a better score."""
import json
import os
import re
import subprocess
import time

from .common import ROOT, load_config
from .improve import house_rules
from .chat import augment, run_calc_loop
from . import skills

HARNESS = "calc-skills-v2"  # bump when the way cases are run changes, so cached scores are redone
CASE_FILES = [os.path.join(ROOT, "evals", "cases.json"),         # shipped, fact-free tests
              os.path.join(ROOT, "evals", "local-cases.json")]   # private tests of your own facts (not published)


def suite_hash(prompts):
    """Scores are only comparable for the same tests + same prompts + same skills."""
    import hashlib
    h = hashlib.sha1(HARNESS.encode())
    for p in CASE_FILES + skills.skill_files():
        if os.path.exists(p):
            with open(p, "rb") as f:
                h.update(f.read())
    for name in ("chat_system", "draft"):
        h.update(prompts.get(name).encode())
    h.update(house_rules().encode())
    return h.hexdigest()[:10]


def load_cases():
    out = []
    for p in CASE_FILES:
        if os.path.exists(p):
            with open(p) as f:
                out += json.load(f)
    return out


def _code(text):
    m = re.search(r"```(?:python)?\n(.*?)```", text, re.S)
    return m.group(1) if m else text


def check(out, c):
    low = out.lower()
    t = c["type"]
    if t == "contains_any":
        return any(v.lower() in low for v in c["values"])
    if t == "not_contains_any":
        return not any(v.lower() in low for v in c["values"])
    if t == "regex":
        return re.search(c["pattern"], low) is not None
    if t == "not_regex":
        return re.search(c["pattern"], low) is None
    if t == "max_words":
        return len(out.split()) <= c["value"]
    if t == "min_words":
        return len(out.split()) >= c["value"]
    if t == "bullet_count":
        return len([l for l in out.splitlines() if re.match(r"^\s*[-*•]\s+", l)]) == c["equals"]
    if t == "json_keys":
        m = re.search(r"\{.*\}", out, re.S)
        try:
            d = json.loads(m.group(0)) if m else {}
        except ValueError:
            return False
        return all(k in d for k in c["keys"])
    if t == "word_count_equals":
        return len(re.findall(r"[\w'’-]+", out)) == c["value"]
    if t == "regex_count":
        return len(re.findall(c["pattern"], out)) == c["equals"]
    if t == "no_emoji":
        return re.search("[\U0001F300-\U0001FAFF\u2600-\u27BF]", out) is None
    if t == "json_equals":
        m = re.search(r"[\[{].*[\]}]", out, re.S)
        try:
            return m is not None and json.loads(m.group(0)) == c["value"]
        except ValueError:
            return False
    if t == "python_asserts":
        prog = _code(out) + "\n" + "\n".join("assert " + a for a in c["asserts"]) + "\nprint('OK')\n"
        try:
            r = subprocess.run(["python3", "-I", "-c", prog], capture_output=True, text=True, timeout=10,
                               cwd=os.path.join(ROOT, "data"))
            return r.returncode == 0 and "OK" in r.stdout
        except subprocess.TimeoutExpired:
            return False
    return False


def run_suite(job, llm, model, prompts, overrides=None, only_prompt=None, use_skills=True):
    """overrides: {prompt_name: text} to test a candidate prompt. Returns (score 0..1, tokens/sec, detail)."""
    overrides = overrides or {}
    rules = house_rules()
    cfg = load_config()
    cases = [c for c in load_cases() if not only_prompt or c["prompt"] == only_prompt]
    total, detail, tps = 0.0, [], []
    for c in cases:
        system = overrides.get(c["prompt"]) or prompts.get(c["prompt"])
        system += "\n\n" + rules
        t0 = time.time()
        # same calculator the chat has, so the suite measures the model the way Forge actually uses it
        # same skill routing as the chat, so a skill only "counts" if it really helps
        skill = skills.match(c["task"], llm, cfg) if use_skills else None
        msg = run_calc_loop(llm, model, [{"role": "system", "content": system},
                                         {"role": "user", "content": augment(c["task"], [], skill, cfg)}],
                            temperature=0.2)
        out = msg["content"]
        if msg.get("_tps"):
            tps.append(msg["_tps"])
        passed = [check(out, k) for k in c["checks"]]
        s = sum(passed) / float(len(passed))
        total += s
        detail.append({"id": c["id"], "score": round(s, 2), "secs": round(time.time() - t0, 1),
                       "skill": skill["name"] if skill else None,
                       "failed": [k["type"] for k, ok in zip(c["checks"], passed) if not ok], "output": out[:600]})
        job.say("eval %-18s %s %.0f%%" % (c["id"], model, s * 100))
    score = round(total / max(1, len(cases)), 3)
    speed = round(sum(tps) / len(tps), 1) if tps else 0.0
    return score, speed, detail
