"""Local stem separation with Demucs — loads audio via soundfile (no ffmpeg /
torchcodec needed) and calls the model directly. Writes
stems/<song>/{drums,bass,other,vocals}.wav.

    python separate_local.py "C:\\path\\song.wav" [model_name]

This is the offline, no-API path: works before kickoff / without any keys.
"""
import pathlib
import sys

import numpy as np
import soundfile as sf
import torch
from demucs.apply import apply_model
from demucs.pretrained import get_model


def separate(path: str, model_name: str = "htdemucs", out_name: str = None) -> pathlib.Path:
    """Separate `path` into stems/<out_name or file-stem>/{drums,bass,other,vocals}.wav.
    Returns the output folder. Reusable from prep.py."""
    model = get_model(model_name)
    model.eval()
    sr_model = model.samplerate

    wav, sr = sf.read(path, dtype="float32", always_2d=True)   # (n, ch)
    x = torch.from_numpy(wav.T)                                # (ch, n)
    if x.shape[0] == 1:
        x = x.repeat(2, 1)
    elif x.shape[0] > 2:
        x = x[:2]

    if sr != sr_model:
        import librosa
        x = torch.from_numpy(np.stack(
            [librosa.resample(ch.numpy(), orig_sr=sr, target_sr=sr_model) for ch in x]))

    # demucs normalization
    ref = x.mean(0)
    x = (x - ref.mean()) / (ref.std() + 1e-8)

    print(f"separating '{path}' with {model_name}  ({x.shape[1] / sr_model:.1f}s @ {sr_model} Hz) ...")
    with torch.no_grad():
        sources = apply_model(model, x[None], device="cpu", split=True,
                              overlap=0.25, progress=True)[0]
    sources = sources * ref.std() + ref.mean()

    out = pathlib.Path(__file__).with_name("stems") / (out_name or pathlib.Path(path).stem)
    out.mkdir(parents=True, exist_ok=True)
    for name, src in zip(model.sources, sources):
        f = out / f"{name}.wav"
        sf.write(str(f), src.T.numpy(), sr_model)
        print("  wrote", f)
    print("Done ->", out)
    return out


def main():
    if len(sys.argv) < 2:
        sys.exit('Usage: python separate_local.py "song.wav" [model_name]')
    separate(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "htdemucs")


if __name__ == "__main__":
    main()
