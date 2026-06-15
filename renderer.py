"""OpenCV rendering helpers for Gestural-Harmonic-Mapping."""
import time

import cv2
import numpy as np

from config import (
    PANEL_BG, PANEL_BORDER, NEON_GREEN, NEON_CYAN, NEON_PINK,
    TEXT_DIM, NEAR_WHITE, WARM_RED, COOLDOWN_FRAMES, RASENGAN_HOLD,
    RASENGAN_BLUE, RASENGAN_CYAN, RASENGAN_WHITE, PINCH_THRESH,
)
from gestures import lm_px, dist, INDEX, THUMB, PINKY

STATE_COLOR = {"IDLE": TEXT_DIM, "HILO": NEON_GREEN, "POLIGONO": NEON_CYAN}

EFFECT_DEFS = [
    ("filter",  4, "FILTER",  NEON_CYAN),
    ("reverb",  6, "REVERB",  NEON_PINK),
    ("tremolo", 8, "TREMOLO", NEON_GREEN),
]

_HINTS = {
    "IDLE":     "Double pinch -> HILO   |   Secret jutsu: CROSS -> PRAY -> OPEN PALM",
    "HILO":     "Kiss / Pyramid -> POLYGON   |   Double pinch -> IDLE",
    "POLIGONO": "X=pitch  Y=filter  [6pts:+reverb]  [8pts:+tremolo]   |   Kiss -> HILO",
}

_SHORTCUTS      = "q=quit  f=fullscreen  m=mirror  r=record"
_SHORTCUTS_REC  = "[REC]  r=stop"


# ── Blend helpers ─────────────────────────────────────────────────────────────
def blend_fill(img, x: int, y: int, w: int, h: int, color: tuple, alpha: float):
    ov = img.copy()
    cv2.rectangle(ov, (x, y), (x + w, y + h), color, -1)
    cv2.addWeighted(ov, alpha, img, 1 - alpha, 0, img)


def draw_panel(img, x: int, y: int, w: int, h: int, alpha: float = 0.68):
    blend_fill(img, x, y, w, h, PANEL_BG, alpha)
    cv2.rectangle(img, (x, y), (x + w, y + h), PANEL_BORDER, 1)


# ── Waveform graph ────────────────────────────────────────────────────────────
def draw_waveform_graph(img, shape: str, x: int, y: int, w: int, h: int, color: tuple):
    if w < 4:
        return
    t = np.linspace(0, 2 * np.pi, w, endpoint=False)
    if   shape == "SIN":    wave = np.sin(t)
    elif shape == "SAW":    wave = (t / np.pi) % 2 - 1.0
    elif shape == "SQUARE": wave = np.sign(np.sin(t)).astype(float)
    else:                   wave = 2 * np.abs((t / np.pi) % 2 - 1) - 1
    margin = 5
    xs  = (x + np.arange(w)).astype(np.int32)
    ys  = np.clip(y + h // 2 - wave * (h // 2 - margin), y, y + h - 1).astype(np.int32)
    pts = np.stack([xs, ys], axis=1).reshape(-1, 1, 2)
    cv2.polylines(img, [pts], False, color, 2, cv2.LINE_AA)


# ── Note label ────────────────────────────────────────────────────────────────
def draw_note_label(img, note: str, cx: int, cy: int, color: tuple):
    scale = 0.80
    (tw, th), _ = cv2.getTextSize(note, cv2.FONT_HERSHEY_SIMPLEX, scale, 2)
    pad = 6
    x0  = cx - tw // 2 - pad
    y0  = cy - th - pad
    blend_fill(img, x0, y0, tw + pad * 2, th + pad * 2, PANEL_BG, 0.72)
    cv2.rectangle(img, (x0, y0), (x0 + tw + pad * 2, y0 + th + pad * 2), color, 1)
    cv2.putText(img, note, (x0 + pad, cy),
                cv2.FONT_HERSHEY_SIMPLEX, scale, color, 2, cv2.LINE_AA)


# ── Effect bars ───────────────────────────────────────────────────────────────
def draw_effect_bars(img, n_verts: int, effects: dict, x: int, cy: int):
    BAR_W = 32
    for key, min_v, label, col in EFFECT_DEFS:
        active = n_verts >= min_v
        lc     = col if active else TEXT_DIM
        cv2.putText(img, label[0], (x, cy + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, lc, 1, cv2.LINE_AA)
        bx, by, bh = x + 12, cy - 5, 10
        cv2.rectangle(img, (bx, by), (bx + BAR_W, by + bh), PANEL_BORDER, 1)
        if active:
            fill = int(BAR_W * float(effects.get(key, 0.0)))
            if fill > 0:
                cv2.rectangle(img, (bx, by), (bx + fill, by + bh), col, -1)
        x += BAR_W + 20


# ── Status bar ────────────────────────────────────────────────────────────────
def draw_status_bar(img, state: str, waveform: str, n_verts: int,
                    note: str, effects: dict, W: int, H: int):
    bar_h = 72
    blend_fill(img, 0, H - bar_h, W, bar_h, PANEL_BG, 0.75)
    cv2.line(img, (0, H - bar_h), (W, H - bar_h), PANEL_BORDER, 1)

    cy  = H - bar_h // 2
    col = STATE_COLOR.get(state, NEAR_WHITE)

    cv2.circle(img, (22, cy), 7, col, -1, cv2.LINE_AA)
    cv2.putText(img, state, (38, cy + 6),
                cv2.FONT_HERSHEY_SIMPLEX, 0.80, col, 2, cv2.LINE_AA)

    if state == "HILO" and note:
        cv2.putText(img, note, (W // 2 - 18, cy + 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.70, NEAR_WHITE, 2, cv2.LINE_AA)
    elif state == "POLIGONO":
        cv2.putText(img, f"{n_verts} pts", (175, cy + 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, NEON_CYAN, 1, cv2.LINE_AA)
        draw_effect_bars(img, n_verts, effects, x=240, cy=cy)

    ww, wh = 100, 44
    wx     = W - ww - 14
    wy     = H - bar_h + (bar_h - wh) // 2
    draw_panel(img, wx, wy, ww, wh, alpha=0.55)
    draw_waveform_graph(img, waveform, wx + 5, wy + 2, ww - 10, wh - 4, NEON_PINK)
    (tw, _), _ = cv2.getTextSize(waveform, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
    cv2.putText(img, waveform, (wx - tw - 8, cy + 6),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, NEON_PINK, 1, cv2.LINE_AA)


# ── Hints + shortcuts ─────────────────────────────────────────────────────────
def draw_hints(img, state: str, recording: bool = False):
    cv2.putText(img, _HINTS.get(state, ""), (14, 26),
                cv2.FONT_HERSHEY_SIMPLEX, 0.48, TEXT_DIM, 1, cv2.LINE_AA)
    shortcuts = _SHORTCUTS_REC if recording else _SHORTCUTS
    sc_color  = (60, 20, 20) if recording else TEXT_DIM
    cv2.putText(img, shortcuts, (14, 46),
                cv2.FONT_HERSHEY_SIMPLEX, 0.40, sc_color, 1, cv2.LINE_AA)


# ── FPS / cooldown / recording overlays ──────────────────────────────────────
def draw_fps(img, fps: int, W: int):
    cv2.putText(img, f"{fps} fps", (W - 72, 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, TEXT_DIM, 1, cv2.LINE_AA)


def draw_cooldown_border(img, n: int, W: int, H: int):
    ratio = n / COOLDOWN_FRAMES
    ov    = img.copy()
    cv2.rectangle(ov, (0, 0), (W, H), WARM_RED, max(2, int(12 * ratio)))
    alpha = 0.15 + 0.35 * ratio
    cv2.addWeighted(ov, alpha, img, 1 - alpha, 0, img)


def draw_recording_indicator(img, W: int):
    """Blinking red REC dot in the top-right corner."""
    if int(time.time() * 2) % 2 == 0:
        cv2.circle(img, (W - 20, 20), 8, (0, 0, 220), -1, cv2.LINE_AA)
        cv2.putText(img, "REC", (W - 55, 26),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.50, (0, 0, 220), 1, cv2.LINE_AA)


# ── Skeleton ──────────────────────────────────────────────────────────────────
def draw_skeleton(img, results):
    if not results.multi_hand_landmarks:
        return
    import mediapipe as mp
    mp_draw  = mp.solutions.drawing_utils
    mp_hands = mp.solutions.hands
    lm_s  = mp_draw.DrawingSpec(color=(70, 60, 85),  thickness=1, circle_radius=2)
    con_s = mp_draw.DrawingSpec(color=(55, 48, 70), thickness=1)
    for hand in results.multi_hand_landmarks:
        mp_draw.draw_landmarks(img, hand, mp_hands.HAND_CONNECTIONS, lm_s, con_s)


# ── Pinch calibration guides ──────────────────────────────────────────────────
def draw_pinch_guides(img, hand, W: int, H: int):
    """In IDLE: draw a threshold ring around each fingertip.

    The ring colour transitions from the finger's neon colour (far = no pinch)
    toward white (close = near pinch threshold) so the user can see how close
    they are to triggering a gesture.
    """
    thumb_pt = lm_px(hand, THUMB, W, H)
    for lid, col in ((INDEX, NEON_CYAN), (12, NEON_GREEN), (16, NEON_PINK), (PINKY, TEXT_DIM)):
        tip   = lm_px(hand, lid, W, H)
        ratio = min(1.0, dist(thumb_pt, tip) / PINCH_THRESH)
        ring_col = tuple(
            int(col[c] * (1.0 - ratio) + NEAR_WHITE[c] * ratio) for c in range(3)
        )
        cv2.circle(img, tip, int(PINCH_THRESH / 2), ring_col, 1, cv2.LINE_AA)


# ── HILO line ─────────────────────────────────────────────────────────────────
def draw_hilo(img, lh, rh, W: int, H: int, color: tuple):
    a = lm_px(lh, INDEX, W, H)
    b = lm_px(rh, INDEX, W, H)
    cv2.line(img, a, b, color, 3, cv2.LINE_AA)
    for pt in (a, b):
        cv2.circle(img, pt, 10, color, -1, cv2.LINE_AA)
        ov = img.copy()
        cv2.circle(ov, pt, 20, color, 2, cv2.LINE_AA)
        cv2.addWeighted(ov, 0.30, img, 0.70, 0, img)


# ── Polygon ───────────────────────────────────────────────────────────────────
def draw_polygon(img, pts: list, color: tuple):
    if len(pts) < 3:
        return
    arr = np.array(pts, np.int32)
    ov  = img.copy()
    cv2.fillPoly(ov, [arr], color)
    cv2.addWeighted(ov, 0.18, img, 0.82, 0, img)
    cv2.polylines(img, [arr], True, color, 3, cv2.LINE_AA)
    for pt in pts:
        cv2.circle(img, pt, 6, NEAR_WHITE, -1, cv2.LINE_AA)
        cv2.circle(img, pt, 6, color, 2, cv2.LINE_AA)


# ── Rasengan ──────────────────────────────────────────────────────────────────
def draw_rasengan(img, cx: int, cy: int, t: float, radius: int = 85):
    """Spinning 3-D-looking chakra sphere."""
    spin = t * 180.0

    for r, a in [(int(radius * 2.4), 0.04), (int(radius * 1.9), 0.08),
                 (int(radius * 1.55), 0.13), (int(radius * 1.25), 0.18)]:
        ov = img.copy()
        cv2.circle(ov, (cx, cy), r, RASENGAN_BLUE, -1)
        cv2.addWeighted(ov, a, img, 1 - a, 0, img)

    for i, tilt in enumerate([0, 60, 120]):
        ring_rot = (spin * 0.75 + i * 55) % 360
        b = max(7, int(radius * abs(np.sin(np.radians(tilt + spin * 0.35)))))
        cv2.ellipse(img, (cx, cy), (radius, b),
                    ring_rot, 0, 360, RASENGAN_CYAN, 2, cv2.LINE_AA)

    for i in range(7):
        a0 = (spin * 1.5 + i * (360 / 7)) % 360
        cv2.ellipse(img, (cx, cy),
                    (int(radius * 1.08), int(radius * 0.40)),
                    a0, 8, 155, RASENGAN_CYAN, 2, cv2.LINE_AA)

    for i in range(16):
        theta = np.radians(spin * 2.4 + i * (360 / 16))
        px = int(cx + radius * 1.18 * np.cos(theta))
        py = int(cy + radius * 0.44 * np.sin(theta))
        size = 3 if i % 3 else 5
        cv2.circle(img, (px, py), size, RASENGAN_WHITE, -1, cv2.LINE_AA)

    cv2.circle(img, (cx, cy), int(radius * 0.58), (255, 215, 140), -1, cv2.LINE_AA)
    cv2.circle(img, (cx, cy), int(radius * 0.38), (255, 240, 210), -1, cv2.LINE_AA)
    cv2.circle(img, (cx, cy), int(radius * 0.18), RASENGAN_WHITE,  -1, cv2.LINE_AA)


def draw_rasengan_progress(img, step: int, hold: int, W: int, H: int):
    """Centred step indicator with panel background."""
    labels = ["CROSS", "PRAY", "OPEN"]
    bar_w, bar_h = 260, 72
    bx = (W - bar_w) // 2
    by = H // 2 - bar_h // 2 - 60
    blend_fill(img, bx, by, bar_w, bar_h, PANEL_BG, 0.78)
    cv2.rectangle(img, (bx, by), (bx + bar_w, by + bar_h), NEON_CYAN, 1)
    cv2.putText(img, "RASENGAN", (bx + 70, by + 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, NEON_CYAN, 1, cv2.LINE_AA)
    for i, lbl in enumerate(labels):
        done    = i < step
        current = (i == step) and step < 3
        col     = NEON_CYAN if done else (NEON_GREEN if current else TEXT_DIM)
        mark    = "v" if done else (">" if current else " ")
        pct     = f"{int(hold / RASENGAN_HOLD * 100)}%" if current else ""
        x = bx + 10 + i * 85
        cv2.putText(img, f"{mark}{lbl}", (x, by + 42),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.50, col, 1, cv2.LINE_AA)
        if current and pct:
            cv2.putText(img, pct, (x + 4, by + 62),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, NEON_GREEN, 1, cv2.LINE_AA)
