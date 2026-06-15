"""Musixmatch client — fetch time-synced (LRC) lyrics for AirStems.

    python musixmatch.py "Artist" "Song title"

Reads MUSIXMATCH_API_KEY from the environment (or a local .env file).

NOTE: synced subtitles (matcher.subtitle.get / track.richsync.get) require a
Musixmatch plan with subtitle access. The free Developer plan only returns a
30% lyric snippet. For the Musicathon, ask the Musixmatch Pro organizers for an
elevated hackathon key. If you get status 401/403 or an empty body, that's why.
"""
import json
import os
import sys
import pathlib

import requests

BASE = "https://api.musixmatch.com/ws/1.1"


def _load_dotenv():
    env = pathlib.Path(__file__).with_name(".env")
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def _key() -> str:
    _load_dotenv()
    k = os.environ.get("MUSIXMATCH_API_KEY")
    if not k:
        sys.exit('Set MUSIXMATCH_API_KEY  (PowerShell:  $env:MUSIXMATCH_API_KEY="...")')
    return k


def _get(endpoint: str, **params):
    params["apikey"] = _key()
    r = requests.get(f"{BASE}/{endpoint}", params=params, timeout=30)
    r.raise_for_status()
    msg    = r.json()["message"]
    status = msg["header"]["status_code"]
    if status != 200:
        raise RuntimeError(f"{endpoint} -> status {status} "
                           f"(401/403 = plan lacks access; 404 = no match)")
    return msg["body"]


def synced_lyrics(artist: str, title: str, fmt: str = "lrc") -> str:
    """LRC subtitle body via matcher.subtitle.get (match + subtitle in one call)."""
    body = _get("matcher.subtitle.get", q_artist=artist, q_track=title,
                subtitle_format=fmt)
    return body["subtitle"]["subtitle_body"]


def save_lrc(artist: str, title: str, out_dir: str = "lyrics") -> pathlib.Path:
    lrc = synced_lyrics(artist, title)
    out = pathlib.Path(__file__).with_name(out_dir)
    out.mkdir(exist_ok=True)
    safe = f"{artist}-{title}".replace("/", "_").replace("\\", "_")
    path = out / f"{safe}.lrc"
    path.write_text(lrc, encoding="utf-8")
    return path


def commontrack_id(artist: str, title: str) -> int:
    """Resolve a Musixmatch commontrack_id from artist + title."""
    return _get("matcher.track.get", q_artist=artist, q_track=title)["track"]["commontrack_id"]


def rich_sync(artist: str, title: str) -> list:
    """Word-by-word synced lyrics via track.richsync.get.

    Returns the raw richsync list: each entry is a line
        {"ts": start_s, "te": end_s, "x": line_text,
         "l": [{"c": segment, "o": offset_from_ts}, ...]}
    so a word's absolute time is ts + o. Requires a plan with richsync access
    (the hackathon Pro key has it).
    """
    body = _get("track.richsync.get", commontrack_id=commontrack_id(artist, title))
    return json.loads(body["richsync"]["richsync_body"])


def save_richsync(artist: str, title: str, out_dir: str = "lyrics") -> pathlib.Path:
    data = rich_sync(artist, title)
    out  = pathlib.Path(__file__).with_name(out_dir)
    out.mkdir(exist_ok=True)
    safe = f"{artist}-{title}".replace("/", "_").replace("\\", "_")
    path = out / f"{safe}.richsync.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Fetch synced lyrics from Musixmatch.")
    ap.add_argument("artist")
    ap.add_argument("title")
    ap.add_argument("--rich", action="store_true",
                    help="also fetch word-by-word rich sync (-> .richsync.json)")
    a = ap.parse_args()
    try:
        p = save_lrc(a.artist, a.title)
        print("Saved LRC:", p)
        print(p.read_text(encoding="utf-8")[:300])
        if a.rich:
            rp = save_richsync(a.artist, a.title)
            print("Saved rich sync:", rp)
    except Exception as exc:
        print("ERROR:", exc)
        print("If this is a plan/access error, request a Musixmatch Pro key from "
              "the Musicathon organizers (synced lyrics are gated on the public API).")
