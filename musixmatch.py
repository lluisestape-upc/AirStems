"""Musixmatch client — fetch time-synced (LRC) lyrics for AirStems.

    python musixmatch.py "Artist" "Song title"

Reads MUSIXMATCH_API_KEY from the environment (or a local .env file).

NOTE: synced subtitles (matcher.subtitle.get / track.richsync.get) require a
Musixmatch plan with subtitle access. The free Developer plan only returns a
30% lyric snippet. For the Musicathon, ask the Musixmatch Pro organizers for an
elevated hackathon key. If you get status 401/403 or an empty body, that's why.
"""
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


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit('Usage: python musixmatch.py "Artist" "Song title"')
    try:
        p = save_lrc(sys.argv[1], sys.argv[2])
        print("Saved:", p)
        print("----")
        print(p.read_text(encoding="utf-8")[:400])
    except Exception as exc:
        print("ERROR:", exc)
        print("If this is a plan/access error, request a Musixmatch Pro key from "
              "the Musicathon organizers (synced lyrics are gated on the public API).")
