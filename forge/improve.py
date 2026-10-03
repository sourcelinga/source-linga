"""The optimizer: generate variants with different strategies, judge them, keep the best.

  target ──► context (your files + past-session lessons + house rules)
         ──► N variants, each made with a different STRATEGY
         ──► static checks (code compiles?) ──► rubric score for every candidate
         ──► best variant vs original, judged twice with the order swapped
         ──► ranked result + diff, saved to history; strategy win-rates updated

Strategy choice is adaptive: strategies that won before are tried first, and
one slot is always reserved for exploring a less-used strategy.
"""
import difflib
import json
import os
import random
import re
import subprocess
import tempfile

from .common import ROOT, db, now
from . import knowledge, skills

RUBRIC = ["goal_fit", "correctness", "clarity", "completeness", "efficiency"]
RUBRIC_SCHEMA = {  # defects come first so the model inspects before it scores
    "type": "object",
    "properties": dict([("defects", {"type": "array", "items": {"type": "string"}})] +
                       [(k, {"type": "integer", "minimum": 1, "maximum": 10}) for k in RUBRIC] +
                       [("reason", {"type": "string"})]),
    "required": ["defects"] + RUBRIC + ["reason"],
}
DEFECT_PENALTY = 0.04
SAME_RATIO = 0.9  # a variant this similar to its parent did not really try the strategy
PAIR_SCHEMA = {"type": "object", "properties": {"winner": {"type": "string", "enum": ["A", "B", "tie"]},
                                                "reason": {"type": "string"}}, "required": ["winner", "reason"]}
KINDS = {
    "skill": "a Claude Code skill / agent instruction file",
    "prompt": "an instruction prompt for an AI model",
    "workflow": "business copy or a business workflow (emails, product text, posts, plans)",
    "code": "source code or a script",
    "answer": "an answer or deliverable for a task",
}
MAX_TARGET = 24000  # chars: input + full rewritten output must fit in num_ctx 16384
CODE_EXT = {".py": ["python3", "-m", "py_compile"], ".js": ["node", "--check"], ".php": ["php", "-l"],
            ".sh": ["bash", "-n"], ".json": ["python3", "-m", "json.tool"]}


def load_strategies():
    with open(os.path.join(ROOT, "strategies.json")) as f:
        return json.load(f)


def house_rules():
    """Your facts and forbidden claims. An untouched template (headings and comments only) counts as none."""
    try:
        with open(os.path.join(ROOT, "house-rules.md")) as f:
            text = re.sub(r"<!--.*?-->", "", f.read(), flags=re.S).strip()
    except OSError:
        return ""
    return text if any(l.lstrip().startswith(("-", "*")) for l in text.splitlines()) else ""


def strategy_stats():
    """win counts per strategy from past runs: {name: [wins, tries]}"""
    stats = {}
    for r in db().execute("SELECT result FROM runs WHERE kind != 'chat'"):
        try:
            res = json.loads(r["result"])
        except ValueError:
            continue
        for v in res.get("variants", []):
            s = stats.setdefault(v["strategy"], [0, 0])
            s[1] += 1
            if v.get("rank") == 1 and v.get("beats_original"):
                s[0] += 1
    return stats


def pick_strategies(n, requested=None):
    all_s = load_strategies()
    if requested:
        return [s for s in requested if s in all_s][:n] or list(all_s)[:n]
    stats = strategy_stats()
    # Laplace-smoothed win rate; untried strategies get an optimistic prior
    score = {s: (stats.get(s, [0, 0])[0] + 1.0) / (stats.get(s, [0, 0])[1] + 2.0) for s in all_s}
    ranked = sorted(all_s, key=lambda s: score[s], reverse=True)
    chosen = ranked[: max(1, n - 1)]
    rest = [s for s in all_s if s not in chosen]
    if rest and len(chosen) < n:
        chosen.append(random.choice(rest))  # exploration slot
    return chosen[:n]


def _strip_fences(text):
    m = re.match(r"^```[\w-]*\n(.*)\n```\s*$", text.strip(), re.S)
    return m.group(1) if m else text.strip()


def static_check(text, ext):
    cmd = CODE_EXT.get(ext)
    if not cmd:
        return None
    with tempfile.NamedTemporaryFile("w", suffix=ext, delete=False) as f:
        f.write(text)
        tmp = f.name
    try:
        r = subprocess.run(cmd + [tmp], capture_output=True, text=True, timeout=30)
        return {"ok": r.returncode == 0, "output": (r.stdout + r.stderr)[-400:].replace(tmp, "<file>")}
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"ok": None, "output": "checker unavailable: %s" % e}
    finally:
        os.unlink(tmp)


def build_context(target, goal, kind, llm, cfg, job):
    q = goal + "\n" + target[:600]
    hits = knowledge.search(q, llm, cfg, k=cfg.get("context_chunks", 6), exclude_transcripts=True)
    lessons = [h for h in knowledge.search("lessons: " + goal, llm, cfg, k=8) if h["path"].startswith("lesson:")][:3]
    job.say("context: %d file chunks, %d lessons" % (len(hits), len(lessons)))
    parts = []
    rules = house_rules()
    trigger = cfg.get("house_rules_trigger") or ""  # e.g. "acme|widget": also apply the rules outside workflows
    if rules and (kind == "workflow" or (trigger and re.search(trigger, q, re.I))):
        parts.append("HOUSE RULES (must be respected):\n" + rules)
    skill = skills.match(q, llm, cfg)
    if skill:
        job.say("skill: %s" % skill["name"])
        parts.append("EXPERT %s" % skills.block(skill))
    if hits:
        parts.append("CONTEXT FROM THE USER'S FILES:\n" + knowledge.context_block(hits, 7000))
    if lessons:
        parts.append("LESSONS FROM PAST SESSIONS:\n" + knowledge.context_block(lessons, 3000))
    return "\n\n".join(parts), [h["path"] for h in hits + lessons]


def score_candidate(llm, cfg, prompts, goal, kind, original, candidate, context):
    if candidate == original:  # baseline: judge it on its own, not as a copy of itself
        user = "GOAL: %s\nTYPE: %s\n\n%s\n\nThere is no separate original; judge this CANDIDATE on its own.\n\n" \
               "CANDIDATE:\n%s" % (goal, KINDS.get(kind, kind), context[:3000], candidate[:10000])
    else:
        user = "GOAL: %s\nTYPE: %s\n\n%s\n\nORIGINAL:\n%s\n\nCANDIDATE:\n%s" % (
            goal, KINDS.get(kind, kind), context[:3000], original[:10000], candidate[:10000])
    data = llm.json(cfg["model"], prompts.get("judge"), user, RUBRIC_SCHEMA)
    vals = [max(1, min(10, int(data.get(k, 5)))) for k in RUBRIC]
    defects = [d for d in (data.get("defects") or []) if isinstance(d, str) and d.strip()][:8]
    # correctness counts double: a confident wrong answer is worse than a plain one
    total = (sum(vals) + vals[1]) / (len(vals) + 1) / 10.0 - DEFECT_PENALTY * len(defects)
    reason = data.get("reason", "")
    if defects:
        reason += " Defects: " + "; ".join(defects)
    return round(max(0.0, total), 3), {k: v for k, v in zip(RUBRIC, vals)}, reason


def pairwise(llm, cfg, prompts, goal, a, b, context):
    """Returns +1 if b beats a, -1 if a beats b, 0 tie — judged twice with order swapped."""
    tally = 0
    for first, second, sign in ((a, b, 1), (b, a, -1)):
        user = "GOAL: %s\n\n%s\n\nVERSION A:\n%s\n\nVERSION B:\n%s" % (goal, context[:2500], first[:9000], second[:9000])
        w = llm.json(cfg["model"], prompts.get("judge_pair"), user, PAIR_SCHEMA).get("winner")
        tally += sign if w == "B" else (-sign if w == "A" else 0)
    return (tally > 0) - (tally < 0)


def improve(job, llm, cfg, prompts, target, goal, kind="skill", n=None, strategies=None, rounds=None,
            path=None, save=True):
    if len(target) > MAX_TARGET:
        raise ValueError("This is %d characters; the local model can rewrite up to %d at once. "
                         "Paste one section of it instead." % (len(target), MAX_TARGET))
    n = int(n or cfg.get("variants", 4))
    rounds = int(rounds or cfg.get("rounds", 1))
    ext = os.path.splitext(path or "")[1].lower()
    goal = goal or "Make this produce better results for its purpose."
    context, sources = build_context(target, goal, kind, llm, cfg, job)

    original = target
    base_score, base_rubric, base_reason = score_candidate(llm, cfg, prompts, goal, kind, original, original, context)
    job.say("original scores %.2f" % base_score)
    variants, current = [], original

    for rnd in range(rounds):
        chosen = pick_strategies(n, strategies)
        job.say("round %d strategies: %s" % (rnd + 1, ", ".join(chosen)))
        all_s = load_strategies()
        for s in chosen:
            job.say("generating: %s" % s)
            # strategy is repeated after the current version: small models follow the most recent instruction
            user = "GOAL: %s\nTYPE: %s\n\n%s\n\nCURRENT VERSION:\n%s\n\nSTRATEGY TO APPLY NOW (%s): %s\n" \
                   "Rewrite the current version substantially according to this strategy." % (
                       goal, KINDS.get(kind, kind), context[:5000], current, s, all_s[s])
            text = _strip_fences(llm.complete(cfg["model"], prompts.get("generate"), user, temperature=0.8))
            if difflib.SequenceMatcher(None, current, text).ratio() > SAME_RATIO:
                job.say("  %s barely changed anything — retrying once" % s)
                text = _strip_fences(llm.complete(
                    cfg["model"], prompts.get("generate"),
                    user + "\n\nYour previous attempt was almost identical to the current version. That is a "
                           "failure. Apply the strategy for real: change the structure, the method or the wording.",
                    temperature=1.0))
            check = static_check(text, ext) if kind == "code" else None
            sc, rub, why = score_candidate(llm, cfg, prompts, goal, kind, original, text, context)
            if check and check["ok"] is False:
                sc, why = round(sc * 0.3, 3), "FAILS CHECK: %s | %s" % (check["output"][:150], why)
            job.say("  %s → %.2f" % (s, sc))
            variants.append({"strategy": s, "round": rnd + 1, "text": text, "score": sc, "rubric": rub,
                             "reason": why, "check": check})
        best = max(variants, key=lambda v: v["score"])
        if best["score"] > base_score:
            current = best["text"]  # next round evolves from the best so far

    # Repair: give the best version so far its own defect list and ask for a fix (critique → revise).
    pool = variants + [{"strategy": "original", "text": original, "score": base_score, "reason": base_reason}]
    best = max(pool, key=lambda v: v["score"])
    if " Defects: " in best["reason"]:
        defects = best["reason"].split(" Defects: ", 1)[1]
        job.say("repair: fixing the defects the judge found in '%s'" % best["strategy"])
        user = ("GOAL: %s\nTYPE: %s\n\n%s\n\nCURRENT VERSION:\n%s\n\nA reviewer found these defects:\n%s\n\n"
                "Fix every defect. Remove invented claims and do not add new ones. Respect every limit. "
                "Change nothing else.") % (goal, KINDS.get(kind, kind), context[:5000], best["text"], defects)
        text = _strip_fences(llm.complete(cfg["model"], prompts.get("generate"), user, temperature=0.3))
        check = static_check(text, ext) if kind == "code" else None
        sc, rub, why = score_candidate(llm, cfg, prompts, goal, kind, original, text, context)
        if check and check["ok"] is False:
            sc, why = round(sc * 0.3, 3), "FAILS CHECK: %s | %s" % (check["output"][:150], why)
        job.say("  repair → %.2f" % sc)
        variants.append({"strategy": "repair:" + best["strategy"], "round": rounds, "text": text, "score": sc,
                         "rubric": rub, "reason": why, "check": check})

    variants.sort(key=lambda v: v["score"], reverse=True)
    for i, v in enumerate(variants):
        v["rank"] = i + 1
        v["diff"] = "".join(difflib.unified_diff(original.splitlines(True), v["text"].splitlines(True),
                                                 "original", "variant", n=2))[:20000]
    top = variants[0] if variants else None
    if top:
        job.say("confirming top variant against original (2 blind comparisons)…")
        verdict = pairwise(llm, cfg, prompts, goal, original, top["text"], context)
        # blind comparison wins, or it ties (position bias cancels out) while the rubric shows a clear gain
        top["beats_original"] = top["score"] > base_score and (verdict > 0 or (verdict == 0 and top["score"] >= base_score + 0.1))
        top["pairwise"] = {1: "variant preferred", 0: "tie", -1: "original preferred"}[verdict]
    result = {"goal": goal, "kind": kind, "path": path, "original": original,
              "original_score": base_score, "original_rubric": base_rubric, "original_reason": base_reason,
              "variants": variants, "sources": sources, "model": cfg["model"]}
    if save:
        c = db()
        cur = c.execute("INSERT INTO runs (created, kind, target, goal, result) VALUES (?,?,?,?,?)",
                        (now(), kind, path or original[:120], goal, json.dumps(result)))
        c.commit()
        result["run_id"] = cur.lastrowid
    verdict_txt = "better version found" if top and top.get("beats_original") else "original held up"
    job.say("done: %s" % verdict_txt)
    return result


# ---------------------------------------------------------------- workflows (business presets)

def load_workflows():
    """Shipped examples in workflows/, plus your private ones in local/workflows/ (same file name wins)."""
    found = {}
    for d in (os.path.join(ROOT, "workflows"), os.path.join(ROOT, "local", "workflows")):
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".md"):
                found[fn] = os.path.join(d, fn)
    out = []
    for fn in sorted(found):
        with open(found[fn]) as f:
            raw = f.read()
        meta, body = {}, raw
        m = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.S)
        if m:
            body = m.group(2)
            for line in m.group(1).splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip()
        fields = [x.strip() for x in meta.get("fields", "").split(",") if x.strip()]
        out.append({"id": fn[:-3], "name": meta.get("name", fn[:-3]), "goal": meta.get("goal", ""),
                    "fields": fields, "instructions": body.strip()})
    return out


def run_workflow(job, llm, cfg, prompts, wf_id, inputs, n=None):
    wf = next(w for w in load_workflows() if w["id"] == wf_id)
    filled = "\n".join("%s: %s" % (k, inputs.get(k, "")) for k in wf["fields"])
    context, _ = build_context(filled, wf["goal"], "workflow", llm, cfg, job)
    job.say("writing first draft…")
    draft = llm.complete(cfg["model"], prompts.get("draft"),
                         "WORKFLOW: %s\n\nINSTRUCTIONS:\n%s\n\nINPUTS:\n%s\n\n%s" % (
                             wf["name"], wf["instructions"], filled, context), temperature=0.6)
    goal = "%s\nWorkflow instructions: %s\nInputs:\n%s" % (wf["goal"], wf["instructions"][:1500], filled)
    return improve(job, llm, cfg, prompts, _strip_fences(draft), goal, kind="workflow", n=n,
                   path="workflow:" + wf_id)
