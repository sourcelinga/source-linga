"""Share with someone far away: a private internet address for this Mac, and one invite link per person.

The address comes from a Cloudflare quick tunnel (free, no account): `cloudflared` keeps an outgoing
connection to Cloudflare, which forwards https://<random>.trycloudflare.com to this server. Nothing is
opened on the router, and the address is unguessable.

Only invited people get in. Each invite is a one-time link; opening it gives that person their own key
(a cookie), so they can be removed one by one. Guests can only chat, with their own chat list. They never
see your files, notes, house rules, chats, tools pages or the pairing code. Requests that come through the
tunnel can never pair with the 6-digit code, so it can't be guessed from the internet.
"""
import hashlib
import hmac
import json
import os
import platform
import re
import secrets
import shutil
import signal
import subprocess
import tarfile
import threading
import time
import urllib.parse

from .common import DATA

BIN = os.path.join(DATA, "bin", "cloudflared")
STATE = os.path.join(DATA, "share.json")
INVITES = os.path.join(DATA, "invites.json")
LOG = os.path.join(DATA, "cloudflared.log")
URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
INVITE_DAYS = 7  # an unused invite link stops working after this
_lock = threading.RLock()
_job = {"state": "off", "error": ""}  # off | downloading | starting | on | error


# ---------------------------------------------------------------- small JSON files

def _load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=1)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


# ---------------------------------------------------------------- the tunnel

def _alive(pid):
    try:
        os.kill(int(pid), 0)
    except (OSError, TypeError, ValueError):
        return False
    try:  # the pid must still be our cloudflared, not a recycled number
        out = subprocess.run(["ps", "-p", str(int(pid)), "-o", "command="], capture_output=True, text=True).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return BIN in out


def _download():
    """Fetches Cloudflare's own signed cloudflared from its GitHub releases and checks the signature."""
    arch = "arm64" if platform.machine() == "arm64" else "amd64"
    url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-%s.tgz" % arch
    os.makedirs(os.path.dirname(BIN), exist_ok=True)
    tgz = BIN + ".tgz"
    # GitHub hands the file out from a CDN host. Some networks can't reach one of its addresses, so if the
    # normal download fails, try GitHub's other CDN addresses (TLS still checks it is the real host).
    loc = url
    for _ in range(5):  # follow github.com's redirects up to the CDN link
        if not (urllib.parse.urlparse(loc).hostname or "").endswith("github.com"):
            break
        loc = subprocess.run(["curl", "-sI", "-m", "30", "-o", "/dev/null", "-w", "%{redirect_url}", loc],
                             capture_output=True, text=True).stdout.strip() or url
    host = urllib.parse.urlparse(loc).hostname
    tries = [[]] + ([["--resolve", "%s:443:185.199.%d.133" % (host, n)] for n in (108, 110, 111, 109)] if host and host != "github.com" else [])
    for extra in tries:
        r = subprocess.run(["curl", "-fsSL", "--connect-timeout", "10", "-m", "300", "-o", tgz] + extra + [loc],
                           capture_output=True, text=True)
        if r.returncode == 0:
            break
    else:
        raise RuntimeError("couldn't download Cloudflare's connector. Check the internet connection and try again.")
    with tarfile.open(tgz) as t:
        member = next(m for m in t.getmembers() if os.path.basename(m.name) == "cloudflared" and m.isfile())
        with t.extractfile(member) as src, open(BIN + ".new", "wb") as dst:
            shutil.copyfileobj(src, dst)
    os.remove(tgz)
    os.chmod(BIN + ".new", 0o755)
    sig = subprocess.run(["codesign", "-dv", "--verbose=2", BIN + ".new"], capture_output=True, text=True).stderr
    ok = subprocess.run(["codesign", "--verify", "--strict", BIN + ".new"], capture_output=True).returncode == 0
    if not ok or "TeamIdentifier=68WVV388M8" not in sig:  # Cloudflare Inc.'s Apple developer ID
        os.remove(BIN + ".new")
        raise RuntimeError("the downloaded connector is not signed by Cloudflare, so it was deleted")
    os.replace(BIN + ".new", BIN)


def _start(port):
    if not os.path.isfile(BIN):
        _job.update(state="downloading", error="")
        _download()
    _job.update(state="starting", error="")
    log = open(LOG, "w")
    proc = subprocess.Popen([BIN, "tunnel", "--no-autoupdate", "--url", "http://127.0.0.1:%d" % port],
                            stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    # keep the Mac from idle-sleeping while sharing is on (caffeinate ends by itself with cloudflared)
    subprocess.Popen(["caffeinate", "-i", "-w", str(proc.pid)], stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    url = None
    for _ in range(90):
        time.sleep(0.5)
        if proc.poll() is not None:
            break
        try:
            with open(LOG) as f:
                m = URL_RE.search(f.read())
        except OSError:
            m = None
        if m:
            url = m.group(0)
            break
    if not url:
        _kill(proc.pid)
        raise RuntimeError("Cloudflare didn't give an address. Check the internet connection and try again.")
    old = _load(STATE, {})
    _save(STATE, {"on": True, "pid": proc.pid, "url": url, "started": time.time(),
                  "previous_url": old.get("url") if old.get("url") != url else old.get("previous_url")})
    _job.update(state="on", error="")


def _kill(pid):
    try:
        os.killpg(int(pid), signal.SIGTERM)
    except (OSError, TypeError, ValueError):
        try:
            os.kill(int(pid), signal.SIGTERM)
        except (OSError, TypeError, ValueError):
            pass


def ensure(port):
    """Called when the server starts and every few minutes: keeps the tunnel up while sharing is on."""
    with _lock:
        st = _load(STATE, {})
        if not st.get("on") or _job["state"] in ("downloading", "starting"):
            return
        if _alive(st.get("pid")):
            _job.update(state="on", error="")
            return
        try:
            _start(port)
        except Exception as e:
            _job.update(state="error", error=str(e))


def turn_on(port):
    st = _load(STATE, {})
    st["on"] = True
    _save(STATE, st)
    threading.Thread(target=ensure, args=(port,), daemon=True).start()


def turn_off():
    with _lock:
        st = _load(STATE, {})
        _kill(st.get("pid"))
        _save(STATE, {"on": False, "previous_url": st.get("url") or st.get("previous_url")})
        _job.update(state="off", error="")


def url():
    st = _load(STATE, {})
    return st.get("url") if st.get("on") and _job["state"] == "on" else None


def watchdog(port):
    while True:
        time.sleep(120)
        ensure(port)


# ---------------------------------------------------------------- invites (one per person)

def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _invites():
    return _load(INVITES, [])


def create(name):
    """Returns the one-time token; the link is <address>/join#<token>."""
    token = secrets.token_urlsafe(18)
    with _lock:
        inv = _invites()
        inv.append({"id": secrets.token_hex(6), "name": (name or "").strip()[:40] or "Guest",
                    "token": _hash(token), "key": secrets.token_urlsafe(32), "created": time.time(),
                    "joined": None, "last_seen": None})
        _save(INVITES, inv)
        return inv[-1]["id"], token


def renew(gid):
    """A new link for someone already invited (e.g. after the address changed). Keeps their chats."""
    token = secrets.token_urlsafe(18)
    with _lock:
        inv = _invites()
        for g in inv:
            if g["id"] == gid:
                g.update(token=_hash(token), created=time.time())
                _save(INVITES, inv)
                return token
    return None


def remove(gid):
    with _lock:
        _save(INVITES, [g for g in _invites() if g["id"] != gid])
    if re.fullmatch(r"[0-9a-f]{12}", gid or ""):  # their chats go too
        shutil.rmtree(os.path.join(DATA, "convos", "guests", gid), ignore_errors=True)


def accept(token):
    """Uses up an invite link and returns (guest id, key), or None."""
    if not token:
        return None
    h = _hash(token.strip())
    with _lock:
        inv = _invites()
        for g in inv:
            if g.get("token") and hmac.compare_digest(g["token"], h):
                if time.time() - g["created"] > INVITE_DAYS * 86400:
                    return None
                g.update(token=None, joined=g.get("joined") or time.time(), last_seen=time.time())
                _save(INVITES, inv)
                return g["id"], g["key"], g["name"]
    return None


def guest_for(key):
    """The guest id that owns this key, or None."""
    if not key:
        return None
    for g in _invites():
        if hmac.compare_digest(g["key"].encode(), key.encode()):
            if not g.get("last_seen") or time.time() - g["last_seen"] > 300:
                _touch(g["id"])
            return g["id"]
    return None


def _touch(gid):
    with _lock:
        inv = _invites()
        for g in inv:
            if g["id"] == gid:
                g["last_seen"] = time.time()
        _save(INVITES, inv)


def overview():
    st = _load(STATE, {})
    return {"on": bool(st.get("on")), "state": _job["state"] if st.get("on") else "off", "error": _job["error"],
            "url": url(), "installed": os.path.isfile(BIN),
            "guests": [{"id": g["id"], "name": g["name"], "created": g["created"], "joined": g.get("joined"),
                        "last_seen": g.get("last_seen"), "pending": bool(g.get("token")),
                        "expired": bool(g.get("token")) and time.time() - g["created"] > INVITE_DAYS * 86400}
                       for g in _invites()]}
