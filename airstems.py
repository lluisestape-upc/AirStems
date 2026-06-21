"""AirStems — conduct/remix a real song's stems with your hands.

Reuses the Aetheric Geometry pipeline (gestures.py / renderer.py / config.py) and
swaps the oscillator synth for stem_engine.StemEngine.

    Right hand : raise / fold each finger  -> stem 1-4 in/out
                 (fist = full drop, open hand = full mix)
    Left  hand : height (wrist Y)          -> low-pass filter (down=dark, up=open)
                 open / close the hand      -> reverb (open = full, fist = 0)
    Keys       : space = play/pause   b = beat-sync   n = next song   i = info   q = quit

Drop each song under   stems/<name>/*.wav   with matching   lyrics/<name>.lrc
(or .richsync.json)   and   analysis/<name>.json.  Cycle songs live with  n.

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


def _open_camera(i):
    cam = cv2.VideoCapture(i)
    if cam.isOpened():
        # Capture at 720p: the HUD is rendered at the frame's resolution, so a
        # bigger frame = crisp text (no upscaling blur) + a nicer demo video.
        cam.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cam.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    return cam


def _init_camera(index):
    cam = _open_camera(index)
    if cam.isOpened():
        return cam
    for fb in range(3):
        cam = _open_camera(fb)
        if cam.isOpened():
            log.warning("Camera %d unavailable — using %d", index, fb)
            return cam
    log.error("No camera found.")
    sys.exit(1)


def _find_songs():
    """All prepared songs under stems/: sorted list of (name, folder_path)."""
    base = os.path.join(_HERE, "stems")
    out = []
    if os.path.isdir(base):
        for name in sorted(os.listdir(base)):
            d = os.path.join(base, name)
            if os.path.isdir(d) and glob.glob(os.path.join(d, "*.wav")):
                out.append((name, d))
    return out


def _pick_asset(folder, name, ext):
    """Per-song asset matched by name: <folder>/<name><ext>, or None.
    (Strict, so each song only ever shows its own lyrics / analysis.)"""
    if name:
        p = os.path.join(folder, name + ext)
        if os.path.exists(p):
            return p
    return None


def _load_lyrics(name=None):
    """Lyrics matched to the song: prefer word-level rich sync (<name>.richsync.json),
    else line-level (<name>.lrc). Returns (mode, data)."""
    folder = os.path.join(_HERE, "lyrics")
    rj = _pick_asset(folder, name, ".richsync.json")
    if rj:
        try:
            return "rich", parse_richsync(rj)
        except Exception as exc:
            log.warning("Rich-sync load failed: %s", exc)
    lr = _pick_asset(folder, name, ".lrc")
    if lr:
        try:
            return "lrc", parse_lrc(lr)
        except Exception as exc:
            log.warning("Lyrics load failed: %s", exc)
    return None, None


def _load_cyanite(name=None):
    """Compact Cyanite tag string from analysis/<name>.json (matched to the song)."""
    path = _pick_asset(os.path.join(_HERE, "analysis"), name, ".json")
    if not path:
        return ""
    try:
        return format_cyanite(load_analysis(path))
    except Exception as exc:
        log.warning("Cyanite analysis load failed: %s", exc)
        return ""


def main():
    hands_model = _mp_hands.Hands(min_detection_confidence=MP_MIN_DETECTION,
                                  min_tracking_confidence=MP_MIN_TRACKING,
                                  max_num_hands=MP_MAX_HANDS)
    cam    = _init_camera(CAMERA_INDEX)
    engine = StemEngine()

    songs = _find_songs()
    idx = 0
    if len(sys.argv) > 1:                       # optional: start on a named song
        want = sys.argv[1].strip().lower()
        idx = next((i for i, (n, _) in enumerate(songs) if n.lower() == want), 0)

    if songs:
        song_name, folder = songs[idx]
        engine.load_stems(folder)
        log.info("Song '%s' -> %s  (%d song(s) available)", song_name, engine.names, len(songs))
    else:
        song_name = ""
        log.warning("No stems found. Drop WAVs in stems/<song>/ "
                    "(vocals.wav drums.wav bass.wav other.wav).")

    audio_ok = engine.start()
    if audio_ok and engine.names:
        engine.play()
    lyric_mode, lyric_data = _load_lyrics(song_name)
    cyanite_str = _load_cyanite(song_name)

    stem_on = [True, True, True, True]   # persists across frames (hysteresis)
    show_info = False
    filt, rev = 1.0, 0.0
    fps_t, fps_c, fps = time.time(), 0, 0

    cv2.namedWindow("AirStems", cv2.WINDOW_NORMAL)
    cw, ch = int(cam.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cam.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if cw > 0 and ch > 0:
        cv2.resizeWindow("AirStems", cw, ch)        # 1:1 so the HUD isn't upscaled/blurred
        log.info("Capture %dx%d", cw, ch)
    log.info("space = play/pause   b = beat-sync   n = next song   i = info   q = quit")
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

            # Composite skeleton + HUD at the WINDOW's pixel size so the rasterised
            # HUD text stays sharp at any window size (only the webcam behind it is
            # upscaled). MediaPipe still runs on the smaller capture frame above.
            disp = frame
            try:
                _, _, win_w, win_h = cv2.getWindowImageRect("AirStems")
            except Exception:
                win_w = win_h = 0
            if win_w > 0 and win_h > 0:
                win_w, win_h = min(win_w, 1920), min(win_h, 1080)
                if (win_w, win_h) != (frame.shape[1], frame.shape[0]):
                    disp = cv2.resize(frame, (win_w, win_h), interpolation=cv2.INTER_LINEAR)
            draw_skeleton(disp, results)
            disp = draw_hud(disp, engine, stem_on, filt, rev,
                            lyric_mode, lyric_data, cyanite_str, fps, audio_ok, show_info, song_name)
            cv2.imshow("AirStems", disp)

            k = cv2.waitKey(1) & 0xFF
            if   k == ord("q"): break
            elif k == ord(" "): engine.toggle()
            elif k == ord("b"): engine.toggle_quantize()
            elif k == ord("i"): show_info = not show_info
            elif k == ord("n") and len(songs) > 1:
                idx = (idx + 1) % len(songs)
                song_name, folder = songs[idx]
                engine.reload(folder)
                lyric_mode, lyric_data = _load_lyrics(song_name)
                cyanite_str = _load_cyanite(song_name)
                stem_on = [True, True, True, True]
                log.info("Switched to '%s' -> %s", song_name, engine.names)
    finally:
        engine.stop()
        cam.release()
        hands_model.close()
        cv2.destroyAllWindows()
        log.info("Shutdown complete")


if __name__ == "__main__":
    main()
