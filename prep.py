"""prep.py — prepare a whole song for AirStems in one command.

    python prep.py "C:\\path\\song.mp3" --artist "Coldplay" --title "Yellow"
    python prep.py "C:\\path\\song.mp3"                 # stems + Cyanite only
    python prep.py "song.mp3" --name myset --no-stems   # skip the slow Demucs step

Runs three steps, all under the SAME <name> so AirStems pairs them automatically
(then cycle songs in-app with the `n` key):

    1. Demucs separation         -> stems/<name>/{drums,bass,other,vocals}.wav
    2. Musixmatch synced lyrics  -> lyrics/<name>.lrc  (+ .richsync.json if available)
    3. Cyanite analysis          -> analysis/<name>.json     (MP3 — the API errors on WAV)

<name> defaults to the input file's stem. Use the GLOBAL Python (it has
torch/demucs/soundfile + requests):

    python prep.py ...        (NOT the Aetheric venv — that one has no torch)
"""
import argparse
import json
import pathlib

_HERE = pathlib.Path(__file__).parent


def _lyrics(name: str, artist: str, title: str):
    import musixmatch
    out = _HERE / "lyrics"
    out.mkdir(exist_ok=True)
    lrc = musixmatch.synced_lyrics(artist, title)
    (out / f"{name}.lrc").write_text(lrc, encoding="utf-8")
    print(f"    lyrics/{name}.lrc")
    try:                                            # word-by-word is a bonus
        rs = musixmatch.rich_sync(artist, title)
        (out / f"{name}.richsync.json").write_text(json.dumps(rs, ensure_ascii=False),
                                                   encoding="utf-8")
        print(f"    lyrics/{name}.richsync.json")
    except Exception as exc:
        print(f"    (no rich sync: {exc})")


def _analysis(name: str, path: str):
    import cyanite
    if not cyanite.available():
        print("    Cyanite token not set in .env — skipped.")
        return
    out = _HERE / "analysis"
    out.mkdir(exist_ok=True)
    res = cyanite.analyze(path)
    (out / f"{name}.json").write_text(json.dumps(res, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    print(f"    analysis/{name}.json  ({cyanite.format_cyanite(res)})")


def main():
    ap = argparse.ArgumentParser(description="Prepare a song (stems + lyrics + analysis) for AirStems.")
    ap.add_argument("file", help="audio file (MP3 recommended)")
    ap.add_argument("--name", help="folder/key name (default: the file's stem)")
    ap.add_argument("--artist")
    ap.add_argument("--title")
    ap.add_argument("--model", default="htdemucs", help="Demucs model (default htdemucs)")
    ap.add_argument("--no-stems", action="store_true", help="skip the slow Demucs separation")
    a = ap.parse_args()

    name = a.name or pathlib.Path(a.file).stem
    print(f"Preparing '{name}' from {a.file}\n")

    print(f"[1/3] Stems  -> stems/{name}/")
    if a.no_stems:
        print("    skipped (--no-stems)")
    else:
        try:
            from separate_local import separate
            separate(a.file, model_name=a.model, out_name=name)
        except Exception as exc:
            print(f"    separation FAILED: {exc}")

    print(f"\n[2/3] Lyrics -> lyrics/{name}.*")
    if a.artist and a.title:
        try:
            _lyrics(name, a.artist, a.title)
        except Exception as exc:
            print(f"    skipped: {exc}")
    else:
        print("    skipped — pass --artist and --title to fetch synced lyrics.")

    print(f"\n[3/3] Analysis -> analysis/{name}.json")
    try:
        _analysis(name, a.file)
    except Exception as exc:
        print(f"    skipped: {exc}  (Cyanite needs an MP3)")

    print(f"\nDone. Launch AirStems and press 'n' to reach '{name}'.")


if __name__ == "__main__":
    main()
