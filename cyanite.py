"""Cyanite client — AI music analysis (BPM, key, mood, genre) for AirStems.

Cyanite is a GraphQL API.
    Endpoint: https://api.cyanite.ai/graphql
    Auth:     header  Authorization: Bearer <CYANITE_API_TOKEN>
Create an Integration in the Cyanite dashboard (app.cyanite.ai) to get the token.

    python cyanite.py                 # verify the token works (auth probe)
    python cyanite.py "song.mp3"      # upload + analyse a local file

In AirStems, librosa stays the engine for the *beat grid* (it gives per-beat
times needed to quantize). Cyanite adds the "official" BPM / key / mood / genre
and counts as a 3rd partner API used meaningfully.

Analysis flow (Cyanite docs, Audio Analysis V7):
    1) mutation fileUploadRequest        -> { id, uploadUrl }
    2) HTTP PUT the audio to uploadUrl   (raw bytes, <= 15 min)
    3) mutation libraryTrackCreate(uploadId)  -> created track id (auto-enqueues analysis)
    4) query libraryTrack(id).audioAnalysisV7 -> poll until ...Finished, read result

Verified end-to-end 2026-06-15 (bpm/key/genre/mood/energy/valence/arousal all
returned). GOTCHA: the API analysis fails on PCM-16 WAV input with a generic
"Unexpected error occurred" (AudioAnalysisV7Failed) — feed it an MP3 (or convert
WAV -> MP3 first). MP3 works reliably.
"""
import json
import os
import pathlib
import sys
import time

import requests

ENDPOINT = "https://api.cyanite.ai/graphql"


def _load_dotenv():
    env = pathlib.Path(__file__).with_name(".env")
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def _token(required: bool = True) -> str | None:
    _load_dotenv()
    t = os.environ.get("CYANITE_API_TOKEN")
    if t and t.startswith("your_"):
        t = None
    if not t and required:
        sys.exit('Set CYANITE_API_TOKEN  (PowerShell:  $env:CYANITE_API_TOKEN="...")')
    return t or None


def available() -> bool:
    """True if a real Cyanite token is configured."""
    return _token(required=False) is not None


def gql(query: str, variables: dict = None) -> dict:
    r = requests.post(
        ENDPOINT,
        headers={"Authorization": f"Bearer {_token(required=True)}",
                 "Content-Type": "application/json"},
        json={"query": query, "variables": variables or {}},
        timeout=40,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("errors"):
        raise RuntimeError(json.dumps(data["errors"])[:400])
    return data["data"]


# ── Analysis flow ────────────────────────────────────────────────────────────

_CREATE = """
mutation ($input: LibraryTrackCreateInput!) {
  libraryTrackCreate(input: $input) {
    __typename
    ... on LibraryTrackCreateSuccess { createdLibraryTrack { id } }
    ... on LibraryTrackCreateError   { code message }
  }
}"""

# audioAnalysisV7 is a union; only ...Finished carries the result.
_ANALYSIS = """
query ($id: ID!) {
  libraryTrack(id: $id) {
    __typename
    ... on LibraryTrack {
      id
      audioAnalysisV7 {
        __typename
        ... on AudioAnalysisV7Finished {
          result {
            bpmPrediction { value confidence }
            keyPrediction { value confidence }
            genreTags
            moodTags
            energyLevel
            valence
            arousal
          }
        }
        ... on AudioAnalysisV7Failed { error { message } }
      }
    }
  }
}"""


def request_upload() -> dict:
    """fileUploadRequest -> {'id': ..., 'uploadUrl': ...}."""
    return gql("mutation { fileUploadRequest { id uploadUrl } }")["fileUploadRequest"]


def upload_file(upload_url: str, path: str) -> None:
    requests.put(upload_url, data=pathlib.Path(path).read_bytes(), timeout=300).raise_for_status()


def create_library_track(upload_id: str, external_id: str = None) -> str:
    inp = {"uploadId": upload_id}
    if external_id:
        inp["externalId"] = external_id
    res = gql(_CREATE, {"input": inp})["libraryTrackCreate"]
    if res.get("__typename") != "LibraryTrackCreateSuccess":
        raise RuntimeError(f"libraryTrackCreate: {res.get('code')} {res.get('message')}")
    return res["createdLibraryTrack"]["id"]


def wait_for_analysis(track_id: str, every: float = 5.0, timeout: float = 600) -> dict:
    t0 = time.time()
    while True:
        track = gql(_ANALYSIS, {"id": track_id})["libraryTrack"]
        a  = track.get("audioAnalysisV7") or {}
        tn = a.get("__typename", "")
        if tn == "AudioAnalysisV7Finished":
            return a["result"]
        if tn == "AudioAnalysisV7Failed":
            msg = (a.get("error") or {}).get("message", "")
            raise RuntimeError(f"Cyanite analysis failed: {msg or a}")
        if time.time() - t0 > timeout:
            raise TimeoutError("Cyanite analysis timed out")
        print(f"  analysis: {tn or '?'} ...")
        time.sleep(every)


def analyze(path: str) -> dict:
    """Upload a local file, enqueue analysis, and return the V7 result dict
    (bpmPrediction / keyPrediction / genreTags / moodTags / energy / valence)."""
    up = request_upload()
    print("upload id:", up["id"])
    upload_file(up["uploadUrl"], path)
    tid = create_library_track(up["id"], external_id=pathlib.Path(path).stem)
    print("library track:", tid)
    return wait_for_analysis(tid)


def save_analysis(path: str, out_dir: str = "analysis") -> pathlib.Path:
    """Analyse a file and cache the result dict to analysis/<file>.json
    (AirStems reads it to show BPM/key/mood on the HUD)."""
    result = analyze(path)
    out = pathlib.Path(__file__).with_name(out_dir)
    out.mkdir(exist_ok=True)
    p = out / f"{pathlib.Path(path).stem}.json"
    p.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def load_analysis(path: str) -> dict:
    """Read a cached analysis JSON written by save_analysis()."""
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def _pretty_key(v: str) -> str:
    if not v:
        return ""
    for mode in ("Major", "Minor"):
        if v.endswith(mode):
            note = v[:-len(mode)]
            note = (note[0].upper() + note[1:]).replace("Sharp", "#")
            return f"{note} {mode.lower()}"
    return v


def format_cyanite(a: dict) -> str:
    """Compact HUD string, e.g. 'Eb major  |  ambient  |  epic, chilled'.
    ASCII-only separator: OpenCV's Hershey fonts can't render non-ASCII glyphs."""
    if not a:
        return ""
    parts = []
    key = _pretty_key((a.get("keyPrediction") or {}).get("value", ""))
    if key:
        parts.append(key)
    if a.get("genreTags"):
        parts.append(a["genreTags"][0])
    if a.get("moodTags"):
        parts.append(", ".join(a["moodTags"][:3]))
    return "  |  ".join(parts)


# Minimal authenticated query — confirm the field exists in your account's schema.
_AUTH_PROBE = "query { libraryTracks(first: 1) { edges { node { id } } } }"


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Cyanite analysis for AirStems (use MP3).")
    ap.add_argument("file", nargs="?", help="audio file to analyse (MP3 recommended)")
    ap.add_argument("--save", action="store_true",
                    help="cache result to analysis/<file>.json (AirStems shows it on the HUD)")
    a = ap.parse_args()
    if not a.file:                              # auth probe
        try:
            gql(_AUTH_PROBE)
            print("Cyanite OK — token valid.")
        except Exception as exc:
            print("Cyanite check failed:", exc)
            print("Confirm the Bearer token / schema at https://api.cyanite.ai/graphql")
    else:
        try:
            if a.save:
                p = save_analysis(a.file)
                print("Saved analysis:", p)
                print(p.read_text(encoding="utf-8"))
            else:
                result = analyze(a.file)
                print("Cyanite analysis:")
                print(json.dumps(result, indent=2)[:900])
        except Exception as exc:
            print("Cyanite analyze failed:", exc)
            print("Note: feed an MP3 — the API errors on WAV. Docs: https://api-docs.cyanite.ai/")
