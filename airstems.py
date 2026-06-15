"""AirStems — conduct/remix a real song's stems with your hands.

Reuses the Aetheric Geometry pipeline (gestures.py / renderer.py / config.py) and
swaps the oscillator synth for stem_engine.StemEngine.

    Right hand : raise / fold each finger  -> stem 1-4 in/out
                 (fist = full drop, open hand = full mix)
    Left  hand : height (wrist Y)          -> low-pass filter (down=dark, up=open)
                 open / close the hand      -> reverb (open = full, fist = 0)
    Keys       : space = play/pause   b = beat-sync on/off   q = quit

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
from lyrics import parse_lrc, current_line, parse_richsync, current_karaoke

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
FONT        = cv2.FONT_HERSHEY_SIMPLEX


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


def _bar(frame, x, y, w, h, frac, col):
    cv2.rectangle(frame, (x, y), (x + w, y + h), (60, 60, 60), 1)
    fw = int(w * max(0.0, min(1.0, frac)))
    cv2.rectangle(frame, (x, y), (x + fw, y + h), col, -1)


def _draw_karaoke(frame, rich, t, W, H):
    """Word-by-word lyric line: sung prefix bright, the rest dim."""
    text, sung = current_karaoke(rich, t)
    if not text:
        return
    (tw, _), _ = cv2.getTextSize(text, FONT, 0.9, 2)
    x, y = max(10, (W - tw) // 2), H - 30
    cv2.putText(frame, text, (x, y), FONT, 0.9, (130, 130, 130), 2)        # full line, dim
    if sung:
        cv2.putText(frame, text[:sung], (x, y), FONT, 0.9, (90, 220, 255), 2)  # sung, bright


def _draw_hud(frame, engine, stem_on, filt, rev, lyric_mode, lyric_data, W, H, fps, audio_ok):
    y = 30
    for i, name in enumerate(engine.names[:4]):
        on  = stem_on[i] if i < len(stem_on) else False
        col = (80, 230, 120) if on else (90, 90, 90)
        cv2.putText(frame, f"{i + 1} {name}", (20, y + 14), FONT, 0.6, col, 2)
        _bar(frame, 150, y, 120, 16, 1.0 if on else 0.0, col)
        y += 28
    y += 6
    cv2.putText(frame, "filter", (20, y + 14), FONT, 0.55, (200, 200, 200), 1)
    _bar(frame, 150, y, 120, 16, filt, (120, 180, 255)); y += 26
    cv2.putText(frame, "reverb", (20, y + 14), FONT, 0.55, (200, 200, 200), 1)
    _bar(frame, 150, y, 120, 16, rev, (200, 150, 255))

    cv2.putText(frame, f"{fps} fps{'' if audio_ok else '  (NO AUDIO)'}",
                (W - 190, 30), FONT, 0.6, (180, 180, 180), 1)

    # Beat pulse + BPM + sync state
    if engine.bpm > 0:
        p = engine.beat_pulse
        cv2.circle(frame, (W // 2, 40), int(7 + 16 * p),
                   (90, 190, 255), -1 if p > 0.5 else 2)
        cv2.putText(frame, f"{engine.bpm:.0f} BPM   beat-sync {'ON' if engine.quantize else 'OFF'}",
                    (W // 2 - 130, 80), FONT, 0.6, (210, 210, 210), 1)
    else:
        cv2.putText(frame, "beat-sync unavailable (pip install librosa)",
                    (W // 2 - 170, 40), FONT, 0.55, (120, 120, 120), 1)

    if not engine.names:
        cv2.putText(frame, "No stems loaded -> put WAVs in stems/<song>/",
                    (20, H - 30), FONT, 0.6, (60, 200, 255), 2)
    elif lyric_mode == "rich":
        _draw_karaoke(frame, lyric_data, engine.position_seconds, W, H)
    elif lyric_mode == "lrc":
        line = current_line(lyric_data, engine.position_seconds)
        if line:
            (tw, _), _ = cv2.getTextSize(line, FONT, 0.9, 2)
            cv2.putText(frame, line, (max(10, (W - tw) // 2), H - 30),
                        FONT, 0.9, (255, 255, 255), 2)


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

    stem_on = [True, True, True, True]   # persists across frames (hysteresis)
    filt, rev = 1.0, 0.0
    fps_t, fps_c, fps = time.time(), 0, 0

    cv2.namedWindow("AirStems", cv2.WINDOW_NORMAL)
    log.info("space = play/pause   b = beat-sync   q = quit")
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
            _draw_hud(frame, engine, stem_on, filt, rev, lyric_mode, lyric_data, W, H, fps, audio_ok)
            cv2.imshow("AirStems", frame)

            k = cv2.waitKey(1) & 0xFF
            if   k == ord("q"): break
            elif k == ord(" "): engine.toggle()
            elif k == ord("b"): engine.toggle_quantize()
    finally:
        engine.stop()
        cam.release()
        hands_model.close()
        cv2.destroyAllWindows()
        log.info("Shutdown complete")


if __name__ == "__main__":
    main()
