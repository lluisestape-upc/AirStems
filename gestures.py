"""Geometry utilities and gesture detection functions."""
import numpy as np

from config import (
    PINCH_THRESH, PYRAMID_THRESH, PRAYER_DIST, OPEN_PALM_SPREAD,
)

# ── Landmark IDs ──────────────────────────────────────────────────────────────
THUMB    = 4
INDEX    = 8
MIDDLE   = 12
RING     = 16
PINKY    = 20
ALL_TIPS = (THUMB, INDEX, MIDDLE, RING, PINKY)


# ── Coordinate helpers ────────────────────────────────────────────────────────
def lm_px(hand, lid: int, W: int, H: int) -> tuple:
    m = hand.landmark[lid]
    return int(m.x * W), int(m.y * H)


def dist(a: tuple, b: tuple) -> float:
    return float(np.hypot(a[0] - b[0], a[1] - b[1]))


def mid(a: tuple, b: tuple) -> tuple:
    return (a[0] + b[0]) // 2, (a[1] + b[1]) // 2


def polygon_area(pts: np.ndarray) -> float:
    x = pts[:, 0].astype(float)
    y = pts[:, 1].astype(float)
    return 0.5 * abs(float(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1))))


# ── Hand geometry ─────────────────────────────────────────────────────────────
def fingers_up(hand) -> int:
    """Count extended fingers (index through pinky) by tip-vs-knuckle y position."""
    return sum(
        1 for tip, knuckle in ((INDEX, 6), (MIDDLE, 10), (RING, 14), (PINKY, 18))
        if hand.landmark[tip].y < hand.landmark[knuckle].y
    )


# ── Gesture detectors ─────────────────────────────────────────────────────────
def is_cross_pose(lh, rh, W: int, H: int) -> bool:
    """Right index tip is LEFT of left index tip — hands/arms crossed."""
    ri = lm_px(rh, INDEX, W, H)
    li = lm_px(lh, INDEX, W, H)
    return ri[0] < li[0] - 20


def is_prayer_pose(lh, rh, W: int, H: int) -> bool:
    """Wrists close together AND several fingertip pairs close."""
    lw = lm_px(lh, 0, W, H)
    rw = lm_px(rh, 0, W, H)
    if dist(lw, rw) > PRAYER_DIST:
        return False
    close = sum(
        1 for lid in ALL_TIPS
        if dist(lm_px(lh, lid, W, H), lm_px(rh, lid, W, H)) < PRAYER_DIST * 1.4
    )
    return close >= 3


def is_prayer_single(hand, W: int, H: int) -> bool:
    """Single-hand prayer: fingers up and narrow spread (hands pressed together)."""
    spread = dist(lm_px(hand, THUMB, W, H), lm_px(hand, PINKY, W, H))
    return fingers_up(hand) >= 2 and spread < 90


def is_open_palm(hand, W: int, H: int) -> bool:
    """Spread open hand — thumb tip and pinky tip are far apart."""
    return dist(lm_px(hand, THUMB, W, H), lm_px(hand, PINKY, W, H)) > OPEN_PALM_SPREAD


def rasengan_target(hand, W: int, H: int) -> tuple:
    """Palm center extended beyond fingertips in the palm→fingertip direction."""
    palm_cx, palm_cy = lm_px(hand, 9, W, H)
    tips_y = sum(lm_px(hand, lid, W, H)[1] for lid in (INDEX, MIDDLE, RING, PINKY)) // 4
    beyond_y = tips_y - (palm_cy - tips_y)
    return palm_cx, beyond_y


# ── Hand assignment ───────────────────────────────────────────────────────────
def assign_hands(results) -> tuple:
    """Assign detected hands to left/right.

    Primary: MediaPipe handedness (calibrated for front-facing/flipped images,
    so "Left" = user's left hand, "Right" = user's right hand).
    Fallback: thumb-x vs pinky-MCP-x heuristic.

    Returns (left_hand, right_hand) — either may be None.
    """
    landmarks  = results.multi_hand_landmarks or []
    handedness = results.multi_handedness or []
    lh = rh = None

    if handedness and len(handedness) == len(landmarks):
        for hand, label_list in zip(landmarks, handedness):
            label = label_list.classification[0].label
            # MediaPipe handedness is relative to a mirrored (selfie) image:
            # "Left" = user's left hand, "Right" = user's right hand.
            if label == "Left":
                lh = hand
            else:
                rh = hand
    else:
        for m in landmarks:
            if m.landmark[THUMB].x < m.landmark[17].x:
                rh = m
            else:
                lh = m
    return lh, rh


# ── Polygon helpers ───────────────────────────────────────────────────────────
def build_polygon_points(lh, rh, active_l: list, active_r: list,
                         W: int, H: int) -> list:
    """Collect polygon vertices from active finger landmarks of both hands."""
    pts = []
    for d in (THUMB, INDEX, MIDDLE, RING, PINKY):
        if d == THUMB or d in active_l:
            pts.append(lm_px(lh, d, W, H))
    for d in (PINKY, RING, MIDDLE, INDEX, THUMB):
        if d == THUMB or d in active_r:
            pts.append(lm_px(rh, d, W, H))
    return pts


# ── Waveform selection ────────────────────────────────────────────────────────
def select_waveform(hand, W: int, H: int, waves: tuple):
    """Map extended finger count to a waveform name.

    Returns None if the hand is currently pinching (to avoid accidental
    waveform changes during gesture transitions).
    """
    thumb_pt = lm_px(hand, THUMB, W, H)
    if any(dist(thumb_pt, lm_px(hand, lid, W, H)) < PINCH_THRESH
           for lid in (INDEX, MIDDLE, RING, PINKY)):
        return None
    n = fingers_up(hand)
    return waves[n - 1] if 1 <= n <= 4 else None
