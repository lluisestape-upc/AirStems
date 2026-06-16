"""AirStems — real-time multi-stem player with beat-synced toggles.

Forked from Aetheric Geometry's SynthEngine: same sounddevice OutputStream and
the SAME effects chain (first-order IIR low-pass + Schroeder comb reverb +
tremolo). The only change is the *source*: instead of additive oscillators we mix
N pre-separated stem tracks (the WAVs LALAL.AI returns), with a per-stem gain the
hands drive. Audio is stereo end-to-end.

DIFFERENTIATOR — beat-synced toggles: a beat grid is detected on load (librosa);
when beat-sync is on, hand gain changes don't apply instantly, they snap to the
next beat, so every drop/return lands musically. Toggle with set_quantize().

Public API:
    eng = StemEngine()
    eng.load_stems("stems/song")     # loads *.wav + detects BPM/beats
    eng.start(); eng.play()
    eng.set_params(gains={...}, filter_bright=.8, reverb_wet=.3, tremolo=0)
    eng.set_quantize(True)
    eng.position_seconds / eng.bpm / eng.beat_pulse / eng.quantize
"""
import logging
import threading
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

try:
    import sounddevice as sd
    _AUDIO_OK = True
except ImportError:
    _AUDIO_OK = False
    log.warning("sounddevice not installed — visual-only. pip install sounddevice")

try:
    import soundfile as sf
    _SF_OK = True
except ImportError:
    _SF_OK = False
    log.warning("soundfile not installed — cannot load stems. pip install soundfile")

from config import SAMPLE_RATE, BLOCK_SIZE

# Schroeder reverb constants (same values as Aetheric Geometry's synth.py)
_COMB_DELAYS     = (1557, 1617, 1491, 1422)
_REVERB_FEEDBACK = 0.82


def _lowpass(samples: np.ndarray, cutoff: float, state) -> tuple:
    """First-order IIR low-pass. Channel-agnostic: `samples` may be (n,) or
    (n, ch) and `state` a matching scalar / (ch,) vector."""
    omega = 2.0 * np.pi * np.clip(cutoff, 20.0, SAMPLE_RATE * 0.499) / SAMPLE_RATE
    c     = np.exp(-omega)
    b0    = 1.0 - c
    out   = np.empty_like(samples)
    y     = state
    for i in range(len(samples)):
        y      = b0 * samples[i] + c * y
        out[i] = y
    return out, y


def _resample(x: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    """Cheap linear resample — fine for loading stems once at startup."""
    if sr_in == sr_out:
        return x.astype(np.float32)
    n_out = int(round(len(x) * sr_out / sr_in))
    xp    = np.linspace(0.0, 1.0, len(x), endpoint=False)
    xq    = np.linspace(0.0, 1.0, n_out, endpoint=False)
    return np.interp(xq, xp, x).astype(np.float32)


class StemEngine:
    def __init__(self):
        self._lock = threading.Lock()

        self.stems: dict[str, np.ndarray] = {}   # name -> (length, 2) float32
        self.names: list[str] = []
        self.length = 0
        self._song_len = 0.0          # seconds

        # Beat grid (set once on load; read-only during playback)
        self.beat_times = np.array([], dtype=np.float64)
        self.bpm = 0.0

        # Shared params (main thread -> callback)
        self._pending_gains: dict[str, float] = {}   # what the hands want
        self._filter_bright = 1.0
        self._reverb_wet    = 0.0
        self._tremolo       = 0.0
        self._master        = 0.9
        self.playing        = False
        self._quantize      = True

        # Audio-thread-only state
        self._pos            = 0
        self._target_gains: dict[str, float] = {}     # committed (snaps on beat)
        self._curr_gains:   dict[str, float] = {}     # smoothed actual
        self._filter_st      = np.zeros(2)            # per-channel IIR state
        self._comb_bufs      = [np.zeros((d, 2)) for d in _COMB_DELAYS]
        self._comb_pos       = [0] * len(_COMB_DELAYS)
        self._trem_phase     = 0.0
        self._reverb_smooth  = 0.0
        self._beat_pulse     = 0.0    # 1.0 on a beat, decays — for the HUD

        self._stream = None

    # ── Loading + beat detection ─────────────────────────────────────────────
    def load_stems(self, folder: str):
        if not _SF_OK:
            log.error("soundfile missing — run: pip install soundfile")
            return
        wavs = sorted(f for f in Path(folder).glob("*.wav") if not f.name.startswith("_"))
        if not wavs:
            log.warning("No .wav files in %s", folder)
            return
        loaded = {}
        for f in wavs:
            data, sr = sf.read(str(f), dtype="float32", always_2d=True)   # (n, ch)
            if data.shape[1] == 1:
                data = np.repeat(data, 2, axis=1)          # mono -> stereo
            elif data.shape[1] > 2:
                data = data[:, :2]
            if sr != SAMPLE_RATE:
                data = np.stack([_resample(data[:, 0], sr, SAMPLE_RATE),
                                 _resample(data[:, 1], sr, SAMPLE_RATE)], axis=1)
            loaded[f.stem.lower()] = data
            log.info("  stem '%s'  %.1fs", f.stem.lower(), len(data) / SAMPLE_RATE)
        self.length = max(len(a) for a in loaded.values())
        for k, a in loaded.items():
            if len(a) < self.length:
                loaded[k] = np.pad(a, ((0, self.length - len(a)), (0, 0)))
        self.stems = loaded
        self.names = list(loaded.keys())
        self._song_len = self.length / SAMPLE_RATE
        self._pending_gains = {n: 1.0 for n in self.names}
        self._target_gains  = dict(self._pending_gains)
        self._curr_gains    = dict(self._pending_gains)
        self._detect_beats()

    def _detect_beats(self):
        """Detect BPM + beat times with librosa (optional dependency)."""
        try:
            import librosa
        except ImportError:
            log.warning("librosa not installed — beat-sync disabled. pip install librosa")
            return
        try:
            drums = next((v for k, v in self.stems.items() if "drum" in k), None)
            y = drums if drums is not None else np.sum(
                list(self.stems.values()), axis=0) / max(1, len(self.stems))
            y = np.asarray(y, dtype=np.float32)
            if y.ndim > 1:                                 # stereo -> mono for tracking
                y = y.mean(axis=1)
            tempo, beats = librosa.beat.beat_track(y=y, sr=SAMPLE_RATE, units="time")
            self.beat_times = np.asarray(beats, dtype=np.float64)
            self.bpm = float(np.atleast_1d(tempo)[0])
            log.info("Beat grid: %.1f BPM, %d beats", self.bpm, len(self.beat_times))
        except Exception as exc:
            log.warning("beat detection failed: %s", exc)

    # ── Transport ────────────────────────────────────────────────────────────
    def start(self) -> bool:
        if not _AUDIO_OK:
            return False
        try:
            self._stream = sd.OutputStream(
                samplerate=SAMPLE_RATE, channels=2, blocksize=BLOCK_SIZE,
                dtype="float32", callback=self._callback)
            self._stream.start()
            log.info("Audio stream started — %d Hz, block %d, stereo", SAMPLE_RATE, BLOCK_SIZE)
            return True
        except Exception as exc:
            log.error("Audio start failed: %s", exc)
            self._stream = None
            return False

    def stop(self):
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def reload(self, folder: str) -> bool:
        """Switch to another song while running. Closes the stream first so no
        callback touches the buffers mid-swap, loads the new stems, resets the
        audio-thread state, and reopens the stream."""
        self.stop()
        self._pos = 0
        self._filter_st = np.zeros(2)
        self._comb_bufs = [np.zeros((d, 2)) for d in _COMB_DELAYS]
        self._comb_pos  = [0] * len(_COMB_DELAYS)
        self._reverb_smooth = 0.0
        self._beat_pulse = 0.0
        self.load_stems(folder)
        ok = self.start()
        self.playing = True
        return ok

    def play(self):   self.playing = True
    def pause(self):  self.playing = False
    def toggle(self): self.playing = not self.playing

    def set_quantize(self, on: bool): self._quantize = bool(on)
    def toggle_quantize(self):        self._quantize = not self._quantize

    @property
    def quantize(self) -> bool:        return self._quantize
    @property
    def position_seconds(self) -> float: return self._pos / SAMPLE_RATE
    @property
    def beat_pulse(self) -> float:     return self._beat_pulse

    # ── Params ───────────────────────────────────────────────────────────────
    def set_params(self, gains: dict = None, filter_bright: float = None,
                   reverb_wet: float = None, tremolo: float = None):
        with self._lock:
            if gains is not None:
                for n, g in gains.items():
                    self._pending_gains[n] = float(g)
            if filter_bright is not None: self._filter_bright = float(filter_bright)
            if reverb_wet    is not None: self._reverb_wet    = float(reverb_wet)
            if tremolo       is not None: self._tremolo       = float(tremolo)

    # ── Audio callback ───────────────────────────────────────────────────────
    def _callback(self, outdata, frames, time_info, status):
        with self._lock:
            playing  = self.playing
            pending  = dict(self._pending_gains)
            fb       = self._filter_bright
            rw       = self._reverb_wet
            tr       = self._tremolo
            master   = self._master
            quantize = self._quantize

        if not playing or self.length == 0:
            outdata[:] = 0.0
            return

        # Beat crossing within this block?
        on_beat = False
        if self.beat_times.size:
            t0 = self._pos / SAMPLE_RATE
            t1 = (self._pos + frames) / SAMPLE_RATE
            if t1 > self._song_len:                        # loop wrap = downbeat
                on_beat = True
            else:
                on_beat = bool(np.any((self.beat_times >= t0) & (self.beat_times < t1)))

        # Commit hand-wanted gains: on the beat (quantized) or immediately
        if on_beat or not (quantize and self.beat_times.size):
            self._target_gains = pending
        self._beat_pulse = 1.0 if on_beat else self._beat_pulse * 0.85

        idx = (self._pos + np.arange(frames)) % self.length
        mix = np.zeros((frames, 2), dtype=np.float64)

        # 1. Mix stems with click-free per-block gain ramps
        for n, arr in self.stems.items():
            cg  = self._curr_gains.get(n, 0.0)
            tgt = self._target_gains.get(n, 0.0)
            mix += arr[idx] * np.linspace(cg, tgt, frames, endpoint=False)[:, None]
            self._curr_gains[n] = tgt
        mix *= master   # stems sum back to ~the original track, so no headroom division

        # 2. Low-pass (hand height) — reuses synth.py's _lowpass, per channel
        if fb < 0.999:
            cutoff = 200.0 * (8000.0 / 200.0) ** fb
            mix, self._filter_st = _lowpass(mix, cutoff, self._filter_st)

        # 3. Schroeder reverb (hand spread), smoothed
        self._reverb_smooth += 0.08 * (rw - self._reverb_smooth)
        if self._reverb_smooth > 0.001:
            mix = self._comb_reverb(mix, self._reverb_smooth)

        # 4. Tremolo (one LFO across both channels)
        if tr > 0.001:
            rate = 0.5 + tr * 9.5
            i    = np.arange(frames)
            lfo  = 0.5 + 0.5 * np.sin(2.0 * np.pi * rate * i / SAMPLE_RATE + self._trem_phase)
            mix *= (1.0 - tr * 0.7 * (1.0 - lfo))[:, None]
            self._trem_phase = (self._trem_phase + 2.0 * np.pi * rate * frames / SAMPLE_RATE) % (2.0 * np.pi)

        outdata[:] = np.clip(mix, -1.0, 1.0).astype(np.float32)
        self._pos = (self._pos + frames) % self.length

    def _comb_reverb(self, dry: np.ndarray, wet: float) -> np.ndarray:
        rev = np.zeros_like(dry)
        for j in range(len(_COMB_DELAYS)):
            D   = _COMB_DELAYS[j]
            buf = self._comb_bufs[j]
            pos = self._comb_pos[j]
            for i in range(len(dry)):
                echo     = buf[(pos + 1) % D]
                buf[pos] = dry[i] + echo * _REVERB_FEEDBACK
                rev[i]  += echo
                pos      = (pos + 1) % D
            self._comb_pos[j] = pos
        rev /= len(_COMB_DELAYS)
        return dry * (1.0 - wet * 0.4) + rev * wet
