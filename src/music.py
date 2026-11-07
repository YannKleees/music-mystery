"""Where the songs come from.

Two sources produce the same track dicts (id, title, artist, year, preview_url,
popularity, source):

* Deezer's public API: no account or key needed, 30-second MP3 previews. This is the
  default so anyone can play.
* Spotify: the player's own playlists after logging in with Spotify (routes/auth.py).
  Spotify stopped returning previews for new apps in 2024, so these play through
  Spotify's embedded player instead.

The song list is kept per player (TrackList below). It used to be one module-level
list, so two people playing at once overwrote each other's playlist.
"""
import json
import re
import threading
import time
from collections.abc import MutableSequence
from concurrent.futures import ThreadPoolExecutor

import requests
from flask import has_request_context, session

DEEZER = "https://api.deezer.com"
TIMEOUT = 10

# Ready-made choices on the playlist page; each is resolved to a Deezer playlist by search.
PRESETS = {
    "charts": "Today's top hits (Deezer charts)",
    "80s hits": "80s hits",
    "90s hits": "90s hits",
    "2000s hits": "2000s hits",
    "rock classics": "Rock classics",
}

_lists = {}          # user id -> list of track dicts
_years = {}          # Deezer album id -> release year, shared cache


class TrackList(MutableSequence):
    """List of the logged-in player's tracks; behaves like the old global list."""

    def _items(self):
        key = session.get("user_id") if has_request_context() else None
        return _lists.setdefault(key, [])

    def __getitem__(self, i):
        return self._items()[i]

    def __setitem__(self, i, value):
        self._items()[i] = value

    def __delitem__(self, i):
        del self._items()[i]

    def __len__(self):
        return len(self._items())

    def insert(self, i, value):
        self._items().insert(i, value)


def _get(path, **params):
    r = requests.get(f"{DEEZER}{path}", params=params, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict) and "error" in data:
        raise RuntimeError(data["error"].get("message", "Deezer error"))
    return data


def _track(t):
    return {
        "id": f"dz{t['id']}",
        "deezer_id": t["id"],
        "title": t.get("title_short") or t.get("title", "Unknown title"),
        "artist": t.get("artist", {}).get("name", "Unknown artist"),
        "year": _years.get(t.get("album", {}).get("id")),     # filled in by refresh()
        "album_id": t.get("album", {}).get("id"),
        "preview_url": t.get("preview") or None,
        "popularity": round((t.get("rank") or 0) / 10000),   # Deezer rank is 0..1,000,000
        "source": "deezer",
    }


def parse_deezer_playlist(text):
    """Playlist id from a Deezer link (deezer.com/.../playlist/123) or a bare number."""
    m = re.search(r"playlist/(\d+)", text or "")
    if m:
        return m.group(1)
    text = (text or "").strip()
    return text if text.isdigit() else None


def find_playlist(query):
    """First Deezer playlist matching a search; returns (id, title) or None."""
    hits = _get("/search/playlist", q=query, limit=1).get("data", [])
    return (str(hits[0]["id"]), hits[0]["title"]) if hits else None


def _album_year(album_id):
    if album_id in _years:
        return _years[album_id]
    for attempt in range(3):
        try:
            date = _get(f"/album/{album_id}").get("release_date") or ""
            _years[album_id] = int(date[:4]) if date[:4].isdigit() else None
            return _years[album_id]
        except RuntimeError:              # "Quota limit exceeded": back off and retry
            time.sleep(1 + attempt)
        except requests.RequestException:
            return None
    return None


def _fill_years(tracks):
    """Release year per track via its album (several tracks often share one)."""
    albums = {t["album_id"] for t in tracks if t["album_id"] not in _years}
    with ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(_album_year, albums))
    for t in tracks:
        t["year"] = _years.get(t["album_id"])
    return [t for t in tracks if t["year"]]          # year questions need a year


def load_deezer(choice, limit=40):
    """Tracks for a preset key, a Deezer playlist link/id, or a search term. Returns (title, tracks)."""
    if choice == "charts":
        items, title = _get("/chart/0/tracks", limit=limit)["data"], PRESETS["charts"]
    else:
        pid = parse_deezer_playlist(choice)
        title = None
        if not pid:
            found = find_playlist(choice)
            if not found:
                raise RuntimeError(f"No Deezer playlist found for '{choice}'")
            pid, title = found
        data = _get(f"/playlist/{pid}")
        title = title or data.get("title", "Deezer playlist")
        items = data.get("tracks", {}).get("data", [])[:limit]
    tracks = [_track(t) for t in items if t.get("readable", True) and t.get("preview")]
    return title, _fill_years(tracks)


# ---------------------------------------------------------------- original release year
# Album dates on Deezer (and Spotify) are often those of a remaster or compilation, so a
# 1983 hit can show up as 2014. MusicBrainz stores when a recording was first released.
# Rule: the song's own single/album release group if there is one, otherwise the earliest
# recording with this title and artist, otherwise the Deezer album year.
MUSICBRAINZ = "https://musicbrainz.org/ws/2"
MB_HEADERS = {"User-Agent": "music-mystery/1.0 (https://github.com/YannKleees/music-mystery)"}
_mb_lock = threading.Lock()
_mb_last = [0.0]
_original = {}       # "artist|title" -> year or None


def _norm(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _credit(item):
    return "".join(c.get("name", "") + c.get("joinphrase", "")
                   for c in item.get("artist-credit", []) if isinstance(c, dict))


def _mb(kind, query):
    with _mb_lock:                                   # MusicBrainz allows one request per second
        wait = 1.05 - (time.time() - _mb_last[0])
        if wait > 0:
            time.sleep(wait)
        _mb_last[0] = time.time()
    r = requests.get(f"{MUSICBRAINZ}/{kind}", headers=MB_HEADERS, timeout=TIMEOUT,
                     params={"query": query, "fmt": "json", "limit": 50})
    r.raise_for_status()
    return r.json()


def _base_title(title):
    """'Song (2014 Remaster)' or 'Song - Live' -> 'Song'."""
    return re.split(r"\s[(\[-]", title, maxsplit=1)[0].strip()


def original_year(artist, title):
    key = f"{_norm(artist)}|{_norm(_base_title(title))}"
    if key in _original:
        return _original[key]
    a, t, base = _norm(artist), _norm(_base_title(title)), _base_title(title)
    year = None
    try:
        groups = _mb("release-group", f'releasegroup:"{base}" AND artist:"{artist}"').get("release-groups", [])
        years = [g["first-release-date"][:4] for g in groups
                 if g.get("first-release-date", "")[:4].isdigit() and _norm(g.get("title", "")) == t
                 and _norm(_credit(g)) == a and g.get("primary-type") in ("Single", "Album", "EP")]
        if not years:
            recs = _mb("recording", f'recording:"{base}" AND artist:"{artist}"').get("recordings", [])
            years = [r["first-release-date"][:4] for r in recs
                     if r.get("first-release-date", "")[:4].isdigit() and _norm(r.get("title", "")) == t
                     and _norm(_credit(r)) == a]
        year = int(min(years)) if years else None
    except (requests.RequestException, ValueError):
        return None                                  # not cached: try again next round
    _original[key] = year
    _save_cache()
    return year


CACHE = None         # set by the app to instance/years.json


def load_cache(path):
    global CACHE
    CACHE = path
    try:
        _original.update(json.loads(open(path, encoding="utf-8").read()))
    except (OSError, ValueError):
        pass


def _save_cache():
    if CACHE:
        try:
            with open(CACHE, "w", encoding="utf-8") as f:
                json.dump(_original, f)
        except OSError:
            pass


def refresh(track):
    """Before a round: a fresh preview link (Deezer's links expire) and the original release year."""
    if track.get("source") != "deezer":
        return track
    try:
        t = _get(f"/track/{track['deezer_id']}")
        if t.get("preview"):
            track["preview_url"] = t["preview"]
    except (requests.RequestException, RuntimeError):
        pass                              # keep the old link; the round still works
    year = original_year(track["artist"], track["title"])
    if year:
        track["year"] = year
    return track
