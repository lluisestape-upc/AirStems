"""LALAL.AI v1 client — separate a song into stems for AirStems.

Verified against the Musicathon partner cURL snippet (API v1). Auth header:
    X-License-Key: <key>
Flow:
    1) POST /api/v1/upload/                  (raw bytes)          -> source "id"
    2) POST /api/v1/split/stem_separator/    {source_id, presets} -> "task_id"
    3) POST /api/v1/check/                    {task_ids:[...]}      -> status + URLs

    python lalalai.py "C:\\path\\song.mp3"
    python lalalai.py song.mp3 --stems vocals drum bass piano

Reads LALAI_LICENSE_KEY from env or .env. Docs: https://www.lalal.ai/api/v1/docs/

Stems land in stems/<song>/<label>.wav — airstems.py loads whatever WAVs are
there (positionally), so exact filenames aren't critical.
"""
import argparse
import json
import os
import pathlib
import sys
import time

import requests

BASE = "https://www.lalal.ai/api/v1/"


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
    k = os.environ.get("LALAI_LICENSE_KEY")
    if not k:
        sys.exit('Set LALAI_LICENSE_KEY  (PowerShell:  $env:LALAI_LICENSE_KEY="...")')
    return k


def _headers(extra: dict = None) -> dict:
    h = {"X-License-Key": _key()}
    if extra:
        h.update(extra)
    return h


def upload(path: str) -> str:
    name = pathlib.Path(path).name
    data = pathlib.Path(path).read_bytes()
    r = requests.post(BASE + "upload/", data=data,
                      headers=_headers({"Content-Disposition": f"attachment; filename={name}"}),
                      timeout=180)
    r.raise_for_status()
    j = r.json()
    sid = j.get("id") or j.get("source_id")
    if not sid:
        raise RuntimeError(f"upload: no source id in response -> {j}")
    return sid


def split(source_id: str, stem: str = "vocals", splitter: str = None) -> str:
    presets = {"stem": stem}
    if splitter:
        presets["splitter"] = splitter
    r = requests.post(BASE + "split/stem_separator/",
                      json={"source_id": source_id, "presets": presets},
                      headers=_headers({"Content-Type": "application/json"}), timeout=60)
    r.raise_for_status()
    j = r.json()
    tid = j.get("task_id") or j.get("id")
    if not tid:
        raise RuntimeError(f"split: no task_id in response -> {j}")
    return tid


def check(task_ids) -> dict:
    r = requests.post(BASE + "check/",
                      json={"task_ids": list(task_ids)},
                      headers=_headers({"Content-Type": "application/json"}), timeout=60)
    r.raise_for_status()
    return r.json()


def _task_node(resp: dict, task_id: str) -> dict:
    """Pull this task's entry out of the check response (shape unconfirmed)."""
    if not isinstance(resp, dict):
        return {}
    if isinstance(resp.get(task_id), dict):
        return resp[task_id]
    for key in ("tasks", "results", "result"):
        v = resp.get(key)
        if isinstance(v, dict) and isinstance(v.get(task_id), dict):
            return v[task_id]
        if isinstance(v, list):
            for it in v:
                if isinstance(it, dict) and it.get("task_id") == task_id:
                    return it
    return resp


def wait(task_id: str, every: float = 3.0, timeout: float = 900) -> dict:
    t0 = time.time()
    while True:
        node   = _task_node(check([task_id]), task_id)
        status = str(node.get("status", "")).lower()
        print(f"  status={status or '?'} progress={node.get('progress')}")
        if status in ("success", "completed", "done", "finished"):
            return node
        if status in ("error", "failed", "cancelled", "canceled"):
            raise RuntimeError(f"split failed -> {node}")
        if time.time() - t0 > timeout:
            raise TimeoutError("split timed out")
        time.sleep(every)


def _tracks(node: dict) -> list:
    """Find download URLs in the result node (handles a couple of layouts)."""
    out = (node.get("tracks")
           or (node.get("result") or {}).get("tracks")
           or (node.get("split") or {}).get("tracks") or [])
    out = list(out) if isinstance(out, list) else []
    res = node.get("split") or node.get("result") or node
    if isinstance(res, dict):
        for k in ("stem_track", "back_track"):
            if res.get(k):
                out.append({"url": res[k], "label": k})
    return out


def download_tracks(tracks: list, out_dir: pathlib.Path) -> list:
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for tr in tracks:
        url   = tr.get("url")
        label = (tr.get("label") or tr.get("stem") or "stem").lower().replace(" ", "_")
        if not url:
            continue
        out = out_dir / f"{label}.wav"
        out.write_bytes(requests.get(url, timeout=600).content)
        saved.append(out)
        print("  saved", out)
    return saved


def separate(path: str, stems=("vocals", "drum", "bass", "piano"), splitter=None) -> pathlib.Path:
    sid = upload(path)
    print("source_id:", sid)
    out = pathlib.Path(__file__).with_name("stems") / pathlib.Path(path).stem
    for stem in stems:
        print(f"splitting '{stem}' ...")
        tid = split(sid, stem=stem, splitter=splitter)
        print("  task_id:", tid)
        node = wait(tid)
        if not download_tracks(_tracks(node), out):
            print("  (no tracks parsed — raw node:)", json.dumps(node)[:300])
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--stems", nargs="+", default=["vocals", "drum", "bass", "piano"])
    ap.add_argument("--splitter", default=None)
    a = ap.parse_args()
    try:
        out = separate(a.file, stems=a.stems, splitter=a.splitter)
        print("Done ->", out)
    except Exception as exc:
        print("ERROR:", exc)
        print("Confirm fields in the Swagger UI: https://www.lalal.ai/api/v1/docs/")
