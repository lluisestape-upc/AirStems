"""Headless smoke test for the AirStems engine — no camera, no audio device.

Loads stems/test/, prints what was detected (stems, length, BPM, beat count),
then runs ~8 s through the REAL audio callback offline and writes the result to
stems/test/_smoke_8s.wav so you can listen and confirm the mix + effects work.

    python smoke_test.py [stem_folder]
"""
import os
import sys

import numpy as np
import soundfile as sf

from config import SAMPLE_RATE, BLOCK_SIZE
from stem_engine import StemEngine

folder = sys.argv[1] if len(sys.argv) > 1 else "stems/test"

eng = StemEngine()
eng.load_stems(folder)

if not eng.names:
    sys.exit(f"No stems loaded from {folder!r} — run demucs first.")

print(f"stems     : {eng.names}")
print(f"length    : {eng.length / SAMPLE_RATE:.1f} s")
print(f"BPM       : {eng.bpm:.1f}")
print(f"beats     : {len(eng.beat_times)}")

# Render ~8 s through the actual callback (all stems on, filter slightly closed,
# a touch of reverb) — exercises mixing + IIR low-pass + Schroeder reverb + beat commit.
eng.playing = True
eng.set_params(gains={n: 1.0 for n in eng.names}, filter_bright=0.8, reverb_wet=0.2)

secs    = 8
nblocks = int(secs * SAMPLE_RATE / BLOCK_SIZE)
out     = np.zeros((nblocks * BLOCK_SIZE, 2), dtype="float32")
buf     = np.zeros((BLOCK_SIZE, 2), dtype="float32")
for i in range(nblocks):
    eng._callback(buf, BLOCK_SIZE, None, None)
    out[i * BLOCK_SIZE:(i + 1) * BLOCK_SIZE] = buf

peak = float(np.max(np.abs(out)))
pkL  = float(np.max(np.abs(out[:, 0])))
pkR  = float(np.max(np.abs(out[:, 1])))
lr   = float(np.mean(np.abs(out[:, 0] - out[:, 1])))
print(f"channels  : {out.shape[1]} | peak L {pkL:.3f} R {pkR:.3f} | mean|L-R| {lr:.4f}")
path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_smoke_8s.wav")
sf.write(path, out, SAMPLE_RATE)
print(f"wrote     : {path}  (peak {peak:.3f})")
print("OK — engine loads, detects beats, and renders audio." if peak > 1e-4
      else "WARNING — output is silent; check the stem files.")
