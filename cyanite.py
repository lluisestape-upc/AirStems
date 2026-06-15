"""Cyanite client — AI music analysis (BPM, key, mood, genre) for AirStems.

Cyanite is a GraphQL API.
    Endpoint: https://api.cyanite.ai/graphql
    Auth:     header  Authorization: Bearer <CYANITE_API_TOKEN>
Generate the token in the Cyanite dashboard (Integrations / API access).

    python cyanite.py            # verify the token works (auth probe)

In AirStems, librosa stays the engine for the *beat grid* (it gives per-beat
times needed to quantize). Cyanite adds the "official" BPM / key / mood and
counts as a 3rd partner API used meaningfully.

NOTE: analysing your own audio is a multi-step async flow (file upload ->
library track -> enqueue analysis -> poll -> read the analysis result). The
exact mutation/field names should be confirmed against the live GraphQL schema
(https://api.cyanite.ai/graphql) — this file ships the transport + auth probe;
`analyze_library_track()` is a template to finalise from the docs.
"""
import json
import os
import pathlib
import sys

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


# Minimal authenticated query — confirm the field exists in your account's schema.
_AUTH_PROBE = "query { libraryTracks(first: 1) { edges { node { id } } } }"


def analyze_library_track(track_id: str) -> dict:
    """Template — finalise field names from the GraphQL schema/docs."""
    q = """
    query ($id: ID!) {
      libraryTrack(id: $id) {
        __typename
        ... on LibraryTrack {
          id
          audioAnalysisV6 {
            __typename
            ... on AudioAnalysisV6Finished {
              result { bpm key mood genre }
            }
          }
        }
      }
    }"""
    return gql(q, {"id": track_id})


if __name__ == "__main__":
    try:
        data = gql(_AUTH_PROBE)
        print("Cyanite OK — token valid.")
        print(json.dumps(data)[:200])
    except Exception as exc:
        print("Cyanite check failed:", exc)
        print("Confirm the Bearer token and that the query matches your schema at "
              "https://api.cyanite.ai/graphql")
