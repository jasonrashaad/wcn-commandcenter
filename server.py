#!/usr/bin/env python3
"""
wcn-commandcenter — the office TV channel. Runs on wcn-raspberrypi, stdlib only.

Serves the kiosk page (web/) and one JSON endpoint, /api/state, that the page
polls. Everything the page shows is aggregated here, in a background thread,
so a slow or dead upstream can never stall the screen: the page always gets
the last good snapshot plus a per-source ok/error flag.

Sources (all LAN or WCN-owned — no third-party requests, per canon):
  - MediaCMS studio on wcn-workbench: the curated ILBTYD Gallery playlist,
    resolved to 720p h264 encodings. Falls back to the public manifest on
    ilookbetterthanyourdad.com if the studio is unreachable.
  - Fleet pulse: TCP/HTTP reachability + latency for the boxes and sites.
  - Jellyfin on wcn-workbench: public info always; now-playing + recently
    added once JELLYFIN_TOKEN is set in wcn-commandcenter.env.
  - This Pi: temp, uptime, load.

Config is env (see wcn-commandcenter.env). Nothing here needs root.
"""
import json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, "web")

PORT = int(os.environ.get("WCN_CC_PORT", "8787"))
BIND = os.environ.get("WCN_CC_BIND", "0.0.0.0")
MEDIACMS_BASE = os.environ.get("MEDIACMS_BASE", "http://192.168.1.118").rstrip("/")
MEDIACMS_PLAYLIST = os.environ.get("MEDIACMS_PLAYLIST", "4cUEWvXJk")
PUBLIC_BASE = os.environ.get("PUBLIC_GALLERY_BASE", "https://ilookbetterthanyourdad.com/media").rstrip("/")
JELLYFIN_URL = os.environ.get("JELLYFIN_URL", "http://192.168.1.118:8096").rstrip("/")
JELLYFIN_TOKEN = os.environ.get("JELLYFIN_TOKEN", "").strip()
PREFERRED_HEIGHT = int(os.environ.get("WCN_CC_VIDEO_HEIGHT", "720"))
PHOTOPRISM_URL = os.environ.get("PHOTOPRISM_URL", "http://192.168.1.118:2342").rstrip("/")
PHOTOPRISM_TOKEN = os.environ.get("PHOTOPRISM_TOKEN", "").strip()      # app password / access token (bearer)
PHOTOPRISM_USER = os.environ.get("PHOTOPRISM_USER", "").strip()        # set both to log in with an app password instead
PHOTOPRISM_PASS = os.environ.get("PHOTOPRISM_PASS", "").strip()
PHOTOPRISM_QUERY = os.environ.get("PHOTOPRISM_QUERY", "quality:3 type:image public:true geo:true")
PHOTOPRISM_BATCH = int(os.environ.get("PHOTOPRISM_BATCH", "30"))

UA = "wcn-commandcenter/1.0 (wcn-raspberrypi)"

# name, kind, target, role. kind: tcp host:port | http url (2xx/3xx = ok)
FLEET = [
    ("wcn-workbench",  "tcp",  "192.168.1.118:22",                                "media · inference"),
    ("wcn-laundryroom","tcp",  "192.168.1.99:22",                                 "Catalyst · ztank"),
    ("MediaCMS studio","http", f"{MEDIACMS_BASE}/api/v1/playlists/{MEDIACMS_PLAYLIST}", "the studio"),
    ("Jellyfin",       "http", f"{JELLYFIN_URL}/System/Info/Public",              "the library"),
    ("whatcomesnextllc.ai",      "http", "https://whatcomesnextllc.ai/",            "the company"),
    ("ilookbetterthanyourdad.com","http", "https://ilookbetterthanyourdad.com/",     "the person"),
]


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def http_get(url, timeout=6, headers=None, json_out=True):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
        return json.loads(data) if json_out else data


def absurl(base, u):
    if not u:
        return None
    return u if u.startswith("http") else base + (u if u.startswith("/") else "/" + u)


# ─────────────────────────── sources ───────────────────────────

def fetch_gallery():
    """Curated playlist from the studio; public manifest as fallback."""
    try:
        pl = http_get(f"{MEDIACMS_BASE}/api/v1/playlists/{MEDIACMS_PLAYLIST}")
        items = pl.get("playlist_media") or pl.get("media") or pl.get("results") or []
        clips = []
        for m in items:
            tok = m.get("friendly_token")
            if not tok:
                continue
            d = http_get(f"{MEDIACMS_BASE}/api/v1/media/{tok}")
            src = pick_encoding(d.get("encodings_info") or {}) or d.get("original_media_url")
            if not src:
                continue
            clips.append({
                "token": tok,
                "title": d.get("title") or m.get("title") or tok,
                "blurb": (d.get("description") or m.get("description") or "").strip(),
                "poster": absurl(MEDIACMS_BASE, d.get("poster_url") or d.get("thumbnail_url")),
                "src": absurl(MEDIACMS_BASE, src),
                "duration": d.get("duration") or m.get("duration") or 0,
            })
        if not clips:
            raise RuntimeError("playlist resolved to zero playable clips")
        return {
            "ok": True, "source": "studio",
            "title": pl.get("title") or "ILBTYD Gallery",
            "description": (pl.get("description") or "").strip(),
            "clips": clips,
        }
    except Exception as e:
        log("gallery: studio failed:", repr(e), "— trying public manifest")
    man = http_get(f"{PUBLIC_BASE}/manifest.json", timeout=10)
    clips = [{
        "token": c["token"], "title": c.get("title") or c["token"],
        "blurb": c.get("blurb", ""), "duration": c.get("duration", 0),
        "poster": f"{PUBLIC_BASE}/{c['poster']}", "src": f"{PUBLIC_BASE}/{c['src']}",
    } for c in man.get("clips", []) if c.get("src")]
    if not clips:
        raise RuntimeError("public manifest has no clips")
    return {"ok": True, "source": "public", "title": "ILBTYD Gallery",
            "description": "", "clips": clips, "generated": man.get("generated")}


def pick_encoding(encodings_info):
    """encodings_info: {"720": {"h264": {"status": "success", "url": ...}}, ...}
    Prefer PREFERRED_HEIGHT; else the largest finished one at or below 1080."""
    done = {}
    for res, codecs in encodings_info.items():
        try:
            h = int(res)
        except ValueError:
            continue
        info = (codecs or {}).get("h264") or {}
        if info.get("status") == "success" and info.get("url"):
            done[h] = info["url"]
    if not done:
        return None
    if PREFERRED_HEIGHT in done:
        return done[PREFERRED_HEIGHT]
    ok = [h for h in done if h <= 1080] or list(done)
    return done[max(ok)]


def fetch_studio_count():
    d = http_get(f"{MEDIACMS_BASE}/api/v1/media?page=1")
    return {"ok": True, "count": d.get("count")}


def check_one(entry):
    name, kind, target, role = entry
    t0 = time.monotonic()
    ok, detail = False, ""
    try:
        if kind == "tcp":
            host, port = target.rsplit(":", 1)
            with socket.create_connection((host, int(port)), timeout=3):
                ok = True
        else:
            req = urllib.request.Request(target, headers={"User-Agent": UA}, method="GET")
            with urllib.request.urlopen(req, timeout=4) as r:
                ok = 200 <= r.status < 400
                detail = str(r.status)
    except urllib.error.HTTPError as e:
        detail = str(e.code)
    except Exception as e:
        detail = type(e).__name__
    ms = int((time.monotonic() - t0) * 1000)
    return {"name": name, "role": role, "ok": ok, "ms": ms, "detail": detail}


def fetch_fleet():
    with ThreadPoolExecutor(max_workers=len(FLEET)) as ex:
        rows = list(ex.map(check_one, FLEET))
    return {"ok": True, "hosts": rows, "up": sum(r["ok"] for r in rows), "total": len(rows)}


def jf_headers():
    auth = (f'MediaBrowser Client="wcn-commandcenter", Device="wcn-raspberrypi", '
            f'DeviceId="wcn-commandcenter", Version="1.0", Token="{JELLYFIN_TOKEN}"')
    return {"Authorization": auth, "X-Emby-Token": JELLYFIN_TOKEN}


_jf_user_id = None


def fetch_jellyfin():
    out = {"ok": False, "configured": bool(JELLYFIN_TOKEN)}
    info = http_get(f"{JELLYFIN_URL}/System/Info/Public", timeout=4)
    out.update({"ok": True, "server": info.get("ServerName"), "version": info.get("Version")})
    if not JELLYFIN_TOKEN:
        return out
    h = jf_headers()
    # Now playing — any client on the server.
    playing = []
    for s in http_get(f"{JELLYFIN_URL}/Sessions?ActiveWithinSeconds=600", headers=h):
        item = s.get("NowPlayingItem")
        if not item:
            continue
        ps = s.get("PlayState") or {}
        playing.append({
            "title": item.get("Name"),
            "series": item.get("SeriesName"),
            "album": item.get("Album"),
            "artist": (item.get("Artists") or [None])[0],
            "type": item.get("Type"),
            "year": item.get("ProductionYear"),
            "client": s.get("Client"), "device": s.get("DeviceName"), "user": s.get("UserName"),
            "paused": bool(ps.get("IsPaused")),
            "position": (ps.get("PositionTicks") or 0) / 1e7,
            "runtime": (item.get("RunTimeTicks") or 0) / 1e7,
            "image": f"/api/jf/image/{item.get('SeriesId') or item.get('Id')}",
        })
    out["now_playing"] = playing
    # Recently added — needs a user context.
    global _jf_user_id
    if not _jf_user_id:
        users = http_get(f"{JELLYFIN_URL}/Users", headers=h)
        admins = [u for u in users if (u.get("Policy") or {}).get("IsAdministrator")]
        _jf_user_id = (admins or users or [{}])[0].get("Id")
    recent = []
    if _jf_user_id:
        q = urllib.parse.urlencode({"Limit": 8, "Fields": "ProductionYear", "GroupItems": "true"})
        for it in http_get(f"{JELLYFIN_URL}/Users/{_jf_user_id}/Items/Latest?{q}", headers=h):
            recent.append({
                "title": it.get("Name"), "type": it.get("Type"), "year": it.get("ProductionYear"),
                "series": it.get("SeriesName"),
                "image": f"/api/jf/image/{it.get('Id')}",
            })
    out["recent"] = recent
    return out


# ── PhotoPrism ──────────────────────────────────────────────────
# Auth is either a bearer token (PHOTOPRISM_TOKEN) or an app password used as
# a login (PHOTOPRISM_USER + PHOTOPRISM_PASS → session token, refreshed on 401).
_pp = {"token": None, "preview": None}


def pp_login():
    if PHOTOPRISM_TOKEN:
        _pp["token"] = PHOTOPRISM_TOKEN
    elif PHOTOPRISM_USER and PHOTOPRISM_PASS:
        body = json.dumps({"username": PHOTOPRISM_USER, "password": PHOTOPRISM_PASS}).encode()
        req = urllib.request.Request(f"{PHOTOPRISM_URL}/api/v1/session", data=body, method="POST",
                                     headers={"User-Agent": UA, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.loads(r.read())
        _pp["token"] = d.get("access_token") or d.get("id")
        _pp["preview"] = (d.get("config") or {}).get("previewToken")
    else:
        raise RuntimeError("not configured")
    if not _pp["preview"]:
        cfg = http_get(f"{PHOTOPRISM_URL}/api/v1/config", headers=pp_headers())
        _pp["preview"] = cfg.get("previewToken")
    return _pp["token"]


def pp_headers():
    t = _pp["token"] or pp_login()
    return {"Authorization": f"Bearer {t}", "X-Auth-Token": t, "X-Session-ID": t}


def pp_get(url, **kw):
    try:
        return http_get(url, headers=pp_headers(), **kw)
    except urllib.error.HTTPError as e:
        if e.code != 401:
            raise
        _pp["token"] = None            # session expired — log in once more
        return http_get(url, headers=pp_headers(), **kw)


def fetch_photos():
    configured = bool(PHOTOPRISM_TOKEN or (PHOTOPRISM_USER and PHOTOPRISM_PASS))
    if not configured:
        return {"ok": True, "configured": False, "photos": []}
    q = urllib.parse.urlencode({"count": PHOTOPRISM_BATCH, "offset": 0, "order": "random",
                                "merged": "true", "q": PHOTOPRISM_QUERY})
    # order=random over a 30k-photo SQLite library can take 10 s+; give it room.
    items = pp_get(f"{PHOTOPRISM_URL}/api/v1/photos?{q}", timeout=30)
    if isinstance(items, dict):
        raise RuntimeError(items.get("error") or "unexpected response")
    photos = []
    for p in items:
        h = p.get("Hash")
        if not h:
            continue
        place = p.get("PlaceLabel") or ", ".join(x for x in (p.get("City"), p.get("Country")) if x and x != "zz")
        photos.append({
            "hash": h,
            "title": p.get("Title") or "",
            "taken": p.get("TakenAtLocal") or p.get("TakenAt"),
            "place": place if place and not place.startswith("Unknown") else "",
            "w": p.get("Width"), "h": p.get("Height"),
            "favorite": bool(p.get("Favorite")),
            "camera": p.get("CameraModel") if p.get("CameraModel") not in (None, "", "Unknown") else "",
            "src": f"/api/pp/thumb/{h}",
        })
    return {"ok": True, "configured": True, "photos": photos, "query": PHOTOPRISM_QUERY}


def fetch_sys():
    temp = None
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            temp = round(int(f.read().strip()) / 1000, 1)
    except Exception:
        pass
    up = None
    try:
        with open("/proc/uptime") as f:
            up = float(f.read().split()[0])
    except Exception:
        pass
    return {"ok": True, "host": socket.gethostname(), "temp_c": temp,
            "uptime_s": up, "load": os.getloadavg()[0]}


# ───────────────────────── aggregator ──────────────────────────

SOURCES = {
    # name: (fetch, ttl seconds)
    "gallery":  (fetch_gallery, 300),
    "studio":   (fetch_studio_count, 300),
    "fleet":    (fetch_fleet, 30),
    "jellyfin": (fetch_jellyfin, 20),
    "photos":   (fetch_photos, 600),
    "sys":      (fetch_sys, 10),
}

STATE = {name: {"ok": False, "error": "not yet fetched"} for name in SOURCES}
STAMP = {name: 0.0 for name in SOURCES}
CMD = {"seq": 0, "scene": None}   # remote nudge: /api/cmd?scene=reel
LOCK = threading.Lock()


def refresh(name):
    fn, _ = SOURCES[name]
    try:
        data = fn()
        data["checked_at"] = time.time()
        data.pop("error", None)
        with LOCK:
            STATE[name] = data
    except Exception as e:
        with LOCK:
            prev = dict(STATE.get(name) or {})
            prev["ok"] = False
            prev["error"] = f"{type(e).__name__}: {e}"[:200]
            prev["checked_at"] = time.time()
            STATE[name] = prev
        log(f"{name}: {type(e).__name__}: {e}")
    STAMP[name] = time.monotonic()


def refresher():
    # First pass in parallel so the screen has something within a few seconds.
    with ThreadPoolExecutor(max_workers=len(SOURCES)) as ex:
        list(ex.map(refresh, SOURCES))
    log("first refresh done:", {k: v.get("ok") for k, v in STATE.items()})
    while True:
        now = time.monotonic()
        for name, (_, ttl) in SOURCES.items():
            if not STATE[name].get("ok"):
                ttl = min(ttl, 60)          # a failed source retries soon, not next TTL
            if now - STAMP[name] >= ttl:
                refresh(name)
        time.sleep(2)


def snapshot():
    with LOCK:
        s = json.loads(json.dumps(STATE))
    s["now"] = time.time()
    s["cmd"] = dict(CMD)
    s["config"] = {"jellyfin_configured": bool(JELLYFIN_TOKEN), "playlist": MEDIACMS_PLAYLIST,
                   "photoprism_configured": bool(PHOTOPRISM_TOKEN or (PHOTOPRISM_USER and PHOTOPRISM_PASS))}
    return s


# ──────────────────────────── http ─────────────────────────────

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=WEB, **kw)

    def log_message(self, fmt, *args):
        if "/api/" not in str(args[0] if args else ""):
            super().log_message(fmt, *args)

    def send_json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == "/api/state":
            return self.send_json(snapshot())
        if u.path == "/api/cmd":
            q = urllib.parse.parse_qs(u.query)
            scene = (q.get("scene") or [None])[0]
            with LOCK:
                CMD["seq"] += 1
                CMD["scene"] = scene
            return self.send_json({"ok": True, **CMD})
        if u.path == "/api/log":
            log("page:", urllib.parse.unquote(u.query)[:120])
            return self.send_json({"ok": True})
        if u.path == "/api/refresh":
            threading.Thread(target=lambda: [refresh(n) for n in SOURCES], daemon=True).start()
            return self.send_json({"ok": True})
        if u.path.startswith("/api/jf/image/"):
            return self.jf_image(u.path.rsplit("/", 1)[1])
        if u.path.startswith("/api/pp/thumb/"):
            return self.pp_thumb(u.path.rsplit("/", 1)[1])
        if u.path == "/":
            self.path = "/index.html"
        return super().do_GET()

    def jf_image(self, item_id):
        """Proxy Jellyfin artwork so the token never reaches the page."""
        if not JELLYFIN_TOKEN or not item_id.isalnum():
            return self.send_error(404)
        try:
            data = http_get(f"{JELLYFIN_URL}/Items/{item_id}/Images/Primary?maxHeight=600&quality=85",
                            headers=jf_headers(), json_out=False, timeout=8)
        except Exception:
            return self.send_error(404)
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Cache-Control", "max-age=3600")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    _thumb_cache = {}   # hash -> bytes; bounded below

    def pp_thumb(self, h):
        """Proxy a PhotoPrism preview (fit_1920) so the token never reaches the page."""
        if not (h.isalnum() and 8 <= len(h) <= 64):
            return self.send_error(404)
        data = Handler._thumb_cache.get(h)
        if data is None:
            try:
                pp_headers()
                data = pp_get(f"{PHOTOPRISM_URL}/api/v1/t/{h}/{_pp['preview']}/fit_1920", json_out=False, timeout=15)
            except Exception as e:
                log("pp thumb:", type(e).__name__, e)
                return self.send_error(404)
            if len(Handler._thumb_cache) > 80:
                Handler._thumb_cache.pop(next(iter(Handler._thumb_cache)))
            Handler._thumb_cache[h] = data
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Cache-Control", "max-age=86400")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def end_headers(self):
        if self.path.endswith((".html", ".js", ".css")):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()


def main():
    threading.Thread(target=refresher, daemon=True, name="refresher").start()
    srv = ThreadingHTTPServer((BIND, PORT), Handler)
    srv.daemon_threads = True
    log(f"wcn-commandcenter listening on {BIND}:{PORT}  playlist={MEDIACMS_PLAYLIST}  "
        f"jellyfin={'configured' if JELLYFIN_TOKEN else 'public-only'}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
