"""AirStems — conduct/remix a real song's stems with your hands.

Reuses the Aetheric Geometry pipeline (gestures.py / renderer.py / config.py) and
swaps the oscillator synth for stem_engine.StemEngine.

    Right hand : raise / fold each finger  -> stem 1-4 in/out
                 (fist = full drop, open hand = full mix)
    Left  hand : height (wrist Y)          -> low-pass filter (down=dark, up=open)
                 open / close the hand      -> reverb (open = full, fist = 0)
    Keys       : space = play/pause   b = beat-sync   i = info   q = quit

Put stems in   stems/<song>/*.wav   and an optional   lyrics/*.lrc.
"""
import glob
import logging
import os
import sys
import time

import cv2
import mediapipe as mp

try:
    _mp_hands = mp.solutions.hands
    _mp_draw  = mp.solutions.drawing_utils
except AttributeError:
    print("ERROR: mediapipe.solutions unavailable — activate the venv and reinstall mediapipe.")
    raise SystemExit(1)

from config import CAMERA_INDEX, MP_MIN_DETECTION, MP_MIN_TRACKING, MP_MAX_HANDS
from gestures import lm_px, dist, assign_hands
from renderer import draw_skeleton
from stem_engine import StemEngine
from lyrics import parse_lrc, parse_richsync
from hud import draw_hud
try:
    from cyanite import load_analysis, format_cyanite
except Exception:                       # keep the app running without the cyanite deps
    def load_analysis(_p): return None
    def format_cyanite(_a): return ""

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("airstems")

_HERE = os.path.dirname(os.path.abspath(__file__))
_TIPS = (8, 12, 16, 20)    # MediaPipe fingertips (index..pinky)
_PIPS = (6, 10, 14, 18)    # matching PIP joints

# ── Tunables (tweak live while testing) ──────────────────────────────────────
UP_MARGIN   = 12     # px: tip must clear PIP by this much to count as "up"
DOWN_MARGIN = 12     # px: tip must drop below PIP by this much to count as "down"
SMOOTH      = 0.35   # EMA factor for filter/reverb (higher = snappier, noisier)
REV_CLOSED  = 0.45   # left-hand openness for a fist      -> reverb 0
REV_OPEN    = 0.95   # left-hand openness for an open hand -> reverb 1


def update_fingers(hand, W, H, state):
    """Margin-based hysteresis: only flip a finger when it clearly crosses,
    otherwise hold — kills the on/off flicker near the threshold."""
    for i, (tip, pip) in enumerate(zip(_TIPS, _PIPS)):
        ty = lm_px(hand, tip, W, H)[1]
        py = lm_px(hand, pip, W, H)[1]
        if   ty < py - UP_MARGIN:   state[i] = True
        elif ty > py + DOWN_MARGIN: state[i] = False
    return state


_MCPS = (5, 9, 13, 17)   # finger knuckles (index..pinky), for hand openness


def hand_openness(hand, W, H):
    """Scale-invariant open/closed measure: mean fingertip-to-knuckle distance
    over palm length. Roughly ~0.3 for a fist, ~0.9 for an open hand."""
    ref = dist(lm_px(hand, 0, W, H), lm_px(hand, 9, W, H)) + 1e-6   # palm length
    return sum(dist(lm_px(hand, t, W, H), lm_px(hand, m, W, H))
               for t, m in zip(_TIPS, _MCPS)) / (4.0 * ref)


def _init_camera(index):
    cam = cv2.VideoCapture(index)
    if cam.isOpened():
        return cam
    for fb in range(3):
        cam = cv2.VideoCapture(fb)
        if cam.isOpened():
            log.warning("Camera %d unavailable — using %d", index, fb)
            return cam
    log.error("No camera found.")
    sys.exit(1)


def _find_stem_folder():
    base = os.path.join(_HERE, "stems")
    if not os.path.isdir(base):
        return None
    for name in sorted(os.listdir(base)):
        d = os.path.join(base, name)
        if os.path.isdir(d) and glob.glob(os.path.join(d, "*.wav")):
            return d
    return None


def _load_lyrics():
    """Prefer word-level rich sync (.richsync.json); fall back to line-level .lrc.
    Returns (mode, data): ("rich", parsed) | ("lrc", lines) | (None, None)."""
    rich = sorted(glob.glob(os.path.join(_HERE, "lyrics", "*.richsync.json")))
    if rich:
        try:
            return "rich", parse_richsync(rich[0])
        except Exception as exc:
            log.warning("Rich-sync load failed: %s", exc)
    lrc = sorted(glob.glob(os.path.join(_HERE, "lyrics", "*.lrc")))
    if lrc:
        try:
            return "lrc", parse_lrc(lrc[0])
        except Exception as exc:
            log.warning("Lyrics load failed: %s", exc)
    return None, None


def _load_cyanite():
    """Compact Cyanite tag string from a cached analysis/*.json (or '')."""
    files = sorted(glob.glob(os.path.join(_HERE, "analysis", "*.json")))
    if not files:
        return ""
    try:
        return format_cyanite(load_analysis(files[0]))
    except Exception as exc:
        log.warning("Cyanite analysis load failed: %s", exc)
        return ""


def main():
    hands_model = _mp_hands.Hands(min_detection_confidence=MP_MIN_DETECTION,
                                  min_tracking_confidence=MP_MIN_TRACKING,
                                  max_num_hands=MP_MAX_HANDS)
    cam    = _init_camera(CAMERA_INDEX)
    engine = StemEngine()

    folder = _find_stem_folder()
    if folder:
        engine.load_stems(folder)
        log.info("Stems from %s -> %s", folder, engine.names)
    else:
        log.warning("No stems found. Drop WAVs in stems/<song>/ "
                    "(vocals.wav drums.wav bass.wav other.wav).")

    audio_ok = engine.start()
    if audio_ok and engine.names:
        engine.play()
    lyric_mode, lyric_data = _load_lyrics()
    cyanite_str = _load_cyanite()

    stem_on = [True, True, True, True]   # persists across frames (hysteresis)
    show_info = False
    filt, rev = 1.0, 0.0
    fps_t, fps_c, fps = time.time(), 0, 0

    cv2.namedWindow("AirStems", cv2.WINDOW_NORMAL)
    log.info("space = play/pause   b = beat-sync   i = info   q = quit")
    try:
        while True:
            ok, frame = cam.read()
            if not ok:
                break
            frame   = cv2.flip(frame, 1)
            H, W    = frame.shape[:2]
            results = hands_model.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            lh, rh  = assign_hands(results)

            fps_c += 1
            now = time.time()
            if now - fps_t >= 1.0:
                fps, fps_c, fps_t = fps_c, 0, now

            if rh:
                update_fingers(rh, W, H, stem_on)
                gains = {engine.names[i]: (1.0 if stem_on[i] else 0.0)
                         for i in range(min(4, len(engine.names)))}
                engine.set_params(gains=gains)
            if lh:
                wy        = lm_px(lh, 0, W, H)[1]
                openness  = hand_openness(lh, W, H)
                filt_new  = max(0.0, min(1.0, 1.0 - wy / H))
                rev_new   = max(0.0, min(1.0, (openness - REV_CLOSED) / (REV_OPEN - REV_CLOSED)))
                filt += SMOOTH * (filt_new - filt)        # EMA smoothing
                rev  += SMOOTH * (rev_new - rev)
                engine.set_params(filter_bright=filt, reverb_wet=rev)

            draw_skeleton(frame, results)
            frame = draw_hud(frame, engine, stem_on, filt, rev,
                             lyric_mode, lyric_data, cyanite_str, fps, audio_ok, show_info)
            cv2.imshow("AirStems", frame)

            k = cv2.waitKey(1) & 0xFF
            if   k == ord("q"): break
            elif k == ord(" "): engine.toggle()
            elif k == ord("b"): engine.toggle_quantize()
            elif k == ord("i"): show_info = not show_info
    finally:
        engine.stop()
        cam.release()
        hands_model.close()
        cv2.destroyAllWindows()
        log.info("Shutdown complete")


if __name__ == "__main__":
    main()
