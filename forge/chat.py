"""General assistant: tool-using chat over your knowledge base. Read-only on your files;
it can only write into local-ai/outputs/."""
import ast
import hashlib
import json
import operator
import os
import re
import socket
import threading
import time
from collections import OrderedDict

from .common import OUTPUTS, allowed_path, expand
from . import knowledge, skills
from .improve import house_rules

# Small models get arithmetic wrong when they do it "in their head" (qwen3.5:9b said 2.74 for 285*2.5/96).
CALC_TOOL = {"type": "function", "function": {
    "name": "calculate",
    "description": "Evaluate an arithmetic expression exactly, e.g. '285*2.5/96' or 'round(3*285+99, 2)'. "
                   "Use it for every calculation instead of computing mentally.",
    "parameters": {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]}}}

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow,
        ast.USub: operator.neg, ast.UAdd: operator.pos}
_FUNCS = {"round": round, "abs": abs, "min": min, "max": max}


def calculate(expr):
    """Safe arithmetic only: numbers, + - * / // % **, parentheses, round/abs/min/max."""
    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            a, b = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.Pow) and abs(b) > 100:
                raise ValueError("exponent too large")
            return _OPS[type(n.op)](a, b)
        if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.operand))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FUNCS and not n.keywords:
            return _FUNCS[n.func.id](*[ev(a) for a in n.args])
        raise ValueError("unsupported expression")
    expr = str(expr).replace("×", "*").replace("÷", "/").replace("₹", "")
    expr = re.sub(r"(?<=\d),(?=(?:\d{2},)*\d{3}(?!\d))", "", expr)  # 1,000 / 12,50,000 -> plain; keep round(x, 2)
    v = ev(ast.parse(expr, mode="eval"))
    return str(round(v, 10) if isinstance(v, float) else v)


def run_calc_loop(llm, model, msgs, max_steps=3, **kw):
    """Chat with only the calculator available; resolves tool calls and returns the final message."""
    for _ in range(max_steps):
        reply = llm.chat(model, msgs, tools=[CALC_TOOL], **kw)
        calls = reply.get("tool_calls") or []
        if not calls:
            return reply
        msgs = msgs + [{"role": "assistant", "content": reply.get("content", ""), "tool_calls": calls}]
        for call in calls:
            name = call.get("function", {}).get("name")
            out = (run_tool(name, _args(call), None, None) if name == "calculate"
                   else "Only calculate is available here. Put the full answer in your reply.")
            msgs.append({"role": "tool", "tool_name": name, "content": out})
    return llm.chat(model, msgs, **kw)


def _args(call):
    args = call.get("function", {}).get("arguments") or {}
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            args = {}
    return args


# Every tool schema is re-read with every new question (~110 tokens each), so keep the list short.
TOOLS = [CALC_TOOL,
    {"type": "function", "function": {
        "name": "search_knowledge",
        "description": "Search the user's skills, notes, project files, past sessions and lessons.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read a text file (first 12 KB), or list a folder (absolute path or ~/...).",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "write_output",
        "description": "Save a long deliverable as a file in the outputs folder.",
        "parameters": {"type": "object", "properties": {"filename": {"type": "string"}, "content": {"type": "string"}},
                       "required": ["filename", "content"]}}},
]


def run_tool(name, args, llm, cfg):
    try:
        if name == "calculate":
            return calculate(args.get("expression", ""))
        if name == "search_knowledge":
            hits = knowledge.search(args.get("query", ""), llm, cfg, k=4)
            return knowledge.context_block(hits, 4000) or "No results."
        if name == "read_file" and os.path.isfile(expand(args.get("path", ""))):
            p = expand(args.get("path", ""))
            if not allowed_path(p, cfg):
                return "Not allowed: outside allowed_roots in config.json."
            with open(p, errors="replace") as f:
                return f.read()[:12000]  # ~3k tokens; a 9B model reads ~150 tokens/s
        if name in ("read_file", "list_dir"):
            p = expand(args.get("path", ""))
            if not allowed_path(p, cfg):
                return "Not allowed: outside allowed_roots in config.json."
            return "\n".join(sorted(os.listdir(p))[:300])
        if name == "write_output":
            fn = os.path.basename(args.get("filename", "output.md")) or "output.md"
            dest = os.path.join(OUTPUTS, fn)
            with open(dest, "w") as f:
                f.write(args.get("content", ""))
            return "Saved to " + dest
        return "Unknown tool " + name
    except Exception as e:
        return "Tool error: %s" % e


# ---------------------------------------------------------------- fast, streamed chat
#
# Speed comes from two things (measured on a 9B model on an M4: it reads ~150 prompt tokens/s):
#  1. The system prompt never changes between turns. Notes and the skill card go into the newest
#     user message instead, so a follow-up only has to read the new part, and Ollama reuses the
#     rest (2–3 s instead of 20+ s).
#  2. The exact messages the model already read are remembered (CONVOS), because a client only
#     sends back the plain conversation, without the notes that were added to each turn.

CONVOS = OrderedDict()
MAX_CONVOS = 50


def _key(system, plain):
    return hashlib.sha1(json.dumps([system, plain], ensure_ascii=False).encode()).hexdigest()


def system_prompt(prompts, client_system=""):
    system = prompts.get("chat_system")
    rules = house_rules()
    if rules:
        system += "\n\n" + rules
    if client_system:
        system += "\n\nINSTRUCTIONS FROM THE APP:\n" + client_system
    return system


def augment(text, hits, skill, cfg):
    """The newest user turn: optional skill card + notes, then the user's own words."""
    parts = []
    if skill:
        parts.append(skills.block(skill))
    if hits:
        parts.append("NOTES FROM THE USER'S FILES (use only if relevant):\n" +
                     knowledge.context_block(hits, cfg.get("chat_context_chars", 3500)))
    return text if not parts else "\n\n".join(parts) + "\n\nUSER MESSAGE:\n" + text


def prepare(llm, cfg, prompts, messages):
    """Returns (msgs for the model, plain history incl. the new user turn, hits, skill)."""
    client_system = "\n".join(m["content"] for m in messages if m.get("role") == "system" and m.get("content"))
    plain = [{"role": m["role"], "content": m.get("content") or ""} for m in messages
             if m.get("role") in ("user", "assistant")]
    if not plain or plain[-1]["role"] != "user":
        raise ValueError("the last message must come from the user")
    system = system_prompt(prompts, client_system)
    history, last = plain[:-1], plain[-1]["content"]
    prefix = CONVOS.get(_key(system, history))
    budget = cfg.get("num_ctx", 16384) * 2.5  # rough chars that fit, leaving room for the answer
    if prefix is None or sum(len(m.get("content") or "") for m in prefix) > budget:
        keep = history[-cfg.get("chat_history", 12):]
        while keep and keep[0]["role"] != "user":
            keep = keep[1:]
        prefix = [{"role": "system", "content": system}] + keep
    seen = "\n".join(m.get("content") or "" for m in prefix)
    hits = [h for h in knowledge.search(last, llm, cfg, k=cfg.get("chat_notes", 3))
            if h["text"][:300] not in seen]  # don't pay to re-read notes already in this conversation
    skill = skills.match(last, llm, cfg)
    msgs = [dict(m) for m in prefix] + [{"role": "user", "content": augment(last, hits, skill, cfg)}]
    return msgs, plain, hits, skill, system


# ---------------------------------------------------------------- read ahead while the user types
#
# A new question costs ~10–20 s of prompt reading before the first word. The web app sends the draft
# after a short typing pause; reading it now means that, if the user sends exactly that text, Ollama
# already holds the result and the answer starts at once. Any other request cancels a stale read,
# so it never delays a real question.

_ahead = {"sig": None, "resp": None}
_ahead_lock = threading.Lock()


def _sig(msgs):
    return hashlib.sha1(json.dumps(msgs, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def cancel_read_ahead(keep=None):
    with _ahead_lock:
        if _ahead["sig"] is None or _ahead["sig"] == keep:
            return
        resp = _ahead["resp"]
        _ahead.update(sig=None, resp=None)
    if resp is not None:
        try:
            resp.fp.raw._sock.shutdown(socket.SHUT_RDWR)  # unblocks the reader; Ollama sees the disconnect
        except Exception:
            pass


def read_ahead(llm, cfg, prompts, messages):
    msgs = prepare(llm, cfg, prompts, messages)[0]
    sig = _sig(msgs)
    with _ahead_lock:
        if _ahead["sig"] == sig:
            return False  # already reading exactly this
    cancel_read_ahead()
    with _ahead_lock:
        _ahead.update(sig=sig, resp=None)

    def opened(r):
        with _ahead_lock:
            if _ahead["sig"] == sig:
                _ahead["resp"] = r
    try:
        for _ in llm.chat_stream(cfg["model"], msgs, tools=TOOLS, options={"num_predict": 1}, on_open=opened):
            pass
    except Exception:
        pass  # cancelled or failed: harmless, the real request does the work
    finally:
        with _ahead_lock:
            if _ahead["sig"] == sig:
                _ahead.update(sig=None, resp=None)
    return True


def stream_chat(llm, cfg, prompts, messages, max_steps=6):
    """Yields events: status, token, tool, done. Shared by the web app, the OpenAI/Ollama-compatible APIs
    and the evals, so every surface gets the same knowledge, skills and tools."""
    t0 = time.time()
    msgs, plain, hits, skill, system = prepare(llm, cfg, prompts, messages)
    cancel_read_ahead(keep=_sig(msgs))  # a read-ahead of this very question is useful; any other is in the way
    if skill:
        yield {"type": "status", "text": "Using skill: " + skill["name"]}
    used, first, final = [], None, {"content": ""}
    for step in range(max_steps + 1):
        last_round = step == max_steps
        for kind, val in llm.chat_stream(cfg["model"], msgs, tools=None if last_round else TOOLS):
            if kind == "token":
                if first is None:
                    first = round(time.time() - t0, 2)
                yield {"type": "token", "text": val}
            else:
                final = val
        calls = final.get("tool_calls") or []
        entry = {"role": "assistant", "content": final["content"]}
        if calls:
            entry["tool_calls"] = calls
        msgs.append(entry)
        if not calls:
            break
        for call in calls:
            name = call.get("function", {}).get("name")
            args = _args(call)
            used.append(name)
            yield {"type": "tool", "name": name, "args": args}
            msgs.append({"role": "tool", "tool_name": name, "content": run_tool(name, args, llm, cfg)})
    CONVOS[_key(system, plain + [{"role": "assistant", "content": final["content"]}])] = msgs
    while len(CONVOS) > MAX_CONVOS:
        CONVOS.popitem(last=False)
    yield {"type": "done", "content": final["content"], "tools": used, "skill": skill["name"] if skill else None,
           "sources": [h["path"] for h in hits], "tps": final.get("_tps"), "first_token_secs": first,
           "secs": round(time.time() - t0, 1), "prompt_tokens": final.get("_prompt_tokens")}


def chat(job, llm, cfg, prompts, messages, max_steps=6):
    """Background-job version (older UI / scripts): same engine, result at the end."""
    for ev in stream_chat(llm, cfg, prompts, messages, max_steps):
        if ev["type"] == "tool":
            job.say("tool %s %s" % (ev["name"], json.dumps(ev["args"])[:120]))
        elif ev["type"] == "status":
            job.say(ev["text"])
        elif ev["type"] == "done":
            return ev
