"""Auto-updates, run by launchd every few hours (python3 -m forge.updater).
Each task runs only when it is due (config.schedule_hours) or when forced.

  knowledge            re-index files that changed (cheap; skips unchanged files)
  lessons              distil new Claude Code sessions into lessons
  model_updates        re-pull the active model / embedder if the registry has a newer build
  candidate_eval       discover newer models, download ONE, test it, switch only if it scores better
  prompt_self_improve  rewrite its own chat/draft prompts; keep a rewrite only if the eval suite improves
"""
import argparse
import json
import os
import re
import shutil
import time
import urllib.request

from .common import NullJob, db, load_config, load_state, log_event, now, save_config, update_state, ROOT
from .llm import Ollama, normalize, remote_manifest
from .prompts import Prompts
from . import evals, knowledge
from .improve import improve

TASKS = ["knowledge", "lessons", "model_updates", "candidate_eval", "prompt_self_improve"]
SELF_IMPROVE = ["chat_system", "draft"]


MODELS = os.path.expanduser("~/.ollama/models")


def models_location(cfg):
    return MODELS if os.path.exists(MODELS) else os.path.expanduser("~")


def _manifest_path(base, model):
    name, tag = normalize(model).split(":", 1)
    return os.path.join(base, "manifests", "registry.ollama.ai", "library", name, tag)


def archive_model(job, cfg, model):
    """Copy a model (manifest + blobs) to the external drive so it can be restored without re-downloading."""
    arc = cfg.get("archive_dir")
    if not arc or not os.path.isdir(os.path.dirname(arc.rstrip("/"))):
        job.say("archive drive not connected; %s stays on the internal disk" % model)
        return False
    src = _manifest_path(MODELS, model)
    with open(src) as f:
        man = json.load(f)
    digests = [man["config"]["digest"]] + [l["digest"] for l in man["layers"]]
    os.makedirs(os.path.join(arc, "blobs"), exist_ok=True)
    for d in digests:
        b = d.replace(":", "-")
        dst = os.path.join(arc, "blobs", b)
        if not os.path.exists(dst):
            shutil.copyfile(os.path.join(MODELS, "blobs", b), dst + ".tmp")
            os.replace(dst + ".tmp", dst)
    os.makedirs(os.path.dirname(_manifest_path(arc, model)), exist_ok=True)
    shutil.copyfile(src, _manifest_path(arc, model))
    job.say("archived %s to %s" % (model, arc))
    return True


def restore_model(job, cfg, model):
    """Copy an archived model back from the external drive (no download)."""
    arc = cfg["archive_dir"]
    with open(_manifest_path(arc, model)) as f:
        man = json.load(f)
    for d in [man["config"]["digest"]] + [l["digest"] for l in man["layers"]]:
        b = d.replace(":", "-")
        dst = os.path.join(MODELS, "blobs", b)
        if not os.path.exists(dst):
            shutil.copyfile(os.path.join(arc, "blobs", b), dst + ".tmp")
            os.replace(dst + ".tmp", dst)
    os.makedirs(os.path.dirname(_manifest_path(MODELS, model)), exist_ok=True)
    shutil.copyfile(_manifest_path(arc, model), _manifest_path(MODELS, model))
    log_event("models", "restored %s from the archive drive" % model)


def due(task, cfg, force):
    if force:
        return True
    last = load_state().get("last_" + task, 0)
    return time.time() - last >= cfg["schedule_hours"].get(task, 24) * 3600


def mark(task):
    update_state(**{"last_" + task: time.time(), "last_" + task + "_at": now()})


# ---------------------------------------------------------------- model updates

def update_models(job, llm, cfg):
    changed = []
    for m in (cfg["model"], cfg["embed_model"]):
        local = llm.local_digest(m)
        remote, size = remote_manifest(m)
        if local is None:
            job.say("%s not installed — pulling" % m)
            llm.pull(m, job.say)
            changed.append(m)
        elif remote and remote != local:
            job.say("%s has a newer build in the registry — updating" % m)
            llm.pull(m, job.say)
            changed.append(m)
        else:
            job.say("%s is up to date" % m)
    if changed:
        log_event("models", "updated " + ", ".join(changed))
    return changed


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "forge-local-ai"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode(errors="replace")


def discover(job, cfg, limit=25):
    """Find new tool-capable models on ollama.com that fit this Mac. Returns [(tag, size_gb)]."""
    found = []
    try:
        page = _get("https://ollama.com/search?c=tools&o=newest")
    except Exception as e:
        job.say("discovery skipped (offline?): %s" % e)
        return found
    names = []
    for n in re.findall(r'href="/library/([a-z0-9.\-]+)"', page):
        if n not in names:
            names.append(n)
    skip = re.compile(r"guard|safeguard|shield|embed|rerank|ocr|vision-only|tts|whisper", re.I)
    seen_fp = set()
    for name in names[:limit]:
        if skip.search(name):  # classifiers / embedders are not assistants
            continue
        try:
            tags_page = _get("https://ollama.com/library/%s/tags" % name)
        except Exception:
            continue
        # plain size tags only (e.g. qwen3.8:8b, gemma4:e4b) — skip quantization/format variants
        tags = sorted(set(re.findall(r"\b%s:((?:e?\d+(?:\.\d+)?b)|latest)\b" % re.escape(name), tags_page)))
        for t in tags:
            fp, size = remote_manifest("%s:%s" % (name, t))
            if fp in seen_fp:  # ":latest" is usually the same file as one of the size tags
                continue
            seen_fp.add(fp)
            if size and 1.5e9 <= size <= cfg["max_model_gb"] * 1e9:
                found.append(("%s:%s" % (name, t), round(size / 1e9, 1)))
    job.say("discovered %d models that fit: %s" % (len(found), ", ".join(t for t, _ in found[:10])))
    return found


def cached_score(model, digest):
    r = db().execute("SELECT score, tps FROM model_scores WHERE model=? AND digest=?", (model, digest)).fetchone()
    return (r["score"], r["tps"]) if r else None


def score_model(job, llm, model, prompts):
    digest = "%s|%s" % (llm.local_digest(model), evals.suite_hash(prompts))
    hit = cached_score(model, digest)
    if hit:
        return hit
    score, tps, detail = evals.run_suite(job, llm, model, prompts)
    c = db()
    c.execute("INSERT OR REPLACE INTO model_scores VALUES (?,?,?,?,?,?)",
              (model, digest, now(), score, tps, json.dumps(detail)))
    c.commit()
    return score, tps


def evaluate_candidates(job, llm, cfg, prompts, max_new=1):
    current = normalize(cfg["model"])
    cur_score, cur_tps = score_model(job, llm, current, prompts)
    job.say("current %s: score %.2f, %.1f tok/s" % (current, cur_score, cur_tps))
    pool = [(m, None) for m in cfg.get("candidate_models", [])] + discover(job, cfg)
    tested_at = load_state().get("tested_candidates", {})
    pulled_new = 0
    for model, _ in pool:
        model = normalize(model)
        if model == current:
            continue
        remote, size = remote_manifest(model)
        if not size or size > cfg["max_model_gb"] * 1e9 or tested_at.get(model) == remote:
            continue
        installed = llm.local_digest(model) is not None
        if not installed:
            if pulled_new >= max_new:
                continue
            free_gb = shutil.disk_usage(models_location(cfg)).free / 1e9
            if free_gb - size / 1e9 < cfg["min_free_disk_gb"]:
                job.say("skip %s: not enough disk (%.0f GB free)" % (model, free_gb))
                continue
            job.say("downloading candidate %s (%.1f GB)" % (model, size / 1e9))
            llm.pull(model, job.say)
            pulled_new += 1
        score, tps = score_model(job, llm, model, prompts)
        # tests may have changed during a long download: compare on the same suite (cached if unchanged)
        cur_score, cur_tps = score_model(job, llm, current, prompts)
        tested_at[model] = remote
        update_state(tested_candidates=tested_at)
        better = score >= cur_score + cfg["switch_margin"] and tps >= cfg["min_tokens_per_sec"]
        job.say("candidate %s: score %.2f, %.1f tok/s → %s" % (model, score, tps, "SWITCH" if better else "keep current"))
        if better:
            old = current
            cfg = load_config()
            cfg["model"] = model
            save_config(cfg)
            log_event("models", "switched %s → %s (score %.2f → %.2f)" % (old, model, cur_score, score))
            current, cur_score, cur_tps = model, score, tps
            # keep the old model for rollback on the external drive, free the SSD
            if archive_model(job, cfg, old):
                llm.delete(old)
        else:
            log_event("models", "tested %s (%.2f vs %.2f) — kept %s" % (model, score, cur_score, current))
            if not installed and cfg.get("remove_losing_candidates"):
                llm.delete(model)
                job.say("removed %s to free disk" % model)
    return {"model": current, "score": cur_score}


# ---------------------------------------------------------------- prompt self-improvement

def self_improve(job, llm, cfg, prompts):
    adopted = []
    for name in SELF_IMPROVE:
        base, tps, _ = evals.run_suite(job, llm, cfg["model"], prompts, only_prompt=name)
        job.say("prompt %s baseline %.2f" % (name, base))
        if base >= 0.999:
            continue
        res = improve(job, llm, cfg, prompts, prompts.get(name),
                      "Improve this system prompt so a small local model following it passes more of these tests: "
                      "respects house-rule facts, follows exact format/length instructions, answers precisely.",
                      kind="prompt", n=3, save=True, path="prompt:" + name)
        best_text, best = None, base
        for v in res["variants"][:2]:
            s, _, _ = evals.run_suite(job, llm, cfg["model"], prompts, overrides={name: v["text"]}, only_prompt=name)
            job.say("  variant (%s) scores %.2f" % (v["strategy"], s))
            if s > best:
                best_text, best = v["text"], s
        if best_text and best >= base + cfg["switch_margin"]:
            prompts.replace(name, best_text, reason="eval %.2f → %.2f" % (base, best))
            log_event("prompts", "self-improved %s: eval %.2f → %.2f" % (name, base, best))
            adopted.append(name)
        else:
            job.say("prompt %s kept (no variant beat it by the margin)" % name)
    return adopted


# ---------------------------------------------------------------- entry point

def run(job=None, only=None, force=False):
    job = job or NullJob()
    cfg = load_config()
    llm = Ollama(cfg["ollama_url"], cfg.get("num_ctx", 16384))
    prompts = Prompts()
    if not llm.ensure_running():
        log_event("error", "Ollama is not running and could not be started")
        return {"error": "ollama down"}
    report = {}
    for task in TASKS:
        if only and task not in only:
            continue
        if not due(task, cfg, force):
            continue
        job.say("== %s ==" % task)
        try:
            if task == "knowledge":
                report[task] = knowledge.refresh(job, llm, cfg)
            elif task == "lessons":
                report[task] = knowledge.extract_lessons(job, llm, cfg, prompts, limit=8)
            elif task == "model_updates":
                report[task] = update_models(job, llm, cfg)
            elif task == "candidate_eval":
                report[task] = evaluate_candidates(job, llm, cfg, prompts)
                cfg = load_config()
            elif task == "prompt_self_improve":
                report[task] = self_improve(job, llm, cfg, prompts)
            mark(task)
        except Exception as e:
            log_event("error", "%s failed: %s" % (task, e))
            report[task] = {"error": str(e)}
    return report


def main():
    ap = argparse.ArgumentParser(description="Forge auto-updater")
    ap.add_argument("tasks", nargs="*", help="limit to these tasks: " + ", ".join(TASKS))
    ap.add_argument("--force", action="store_true", help="run even if not due")
    a = ap.parse_args()
    bad = [t for t in a.tasks if t not in TASKS]
    if bad:
        ap.error("unknown task(s): %s" % ", ".join(bad))
    print(json.dumps(run(only=a.tasks or None, force=a.force), indent=2, default=str))


if __name__ == "__main__":
    main()
