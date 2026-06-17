"""Polished HUD overlay for AirStems.

Rendered with Pillow — anti-aliased TrueType text, translucent rounded panels and
soft gradient scrims — composited onto the OpenCV webcam frame. Falls back to a
plain OpenCV HUD if Pillow is unavailable.

    frame = draw_hud(frame, engine, stem_on, filt, rev,
                     lyric_mode, lyric_data, cyanite_str, fps, audio_ok)
"""
import cv2
import numpy as np

from lyrics import current_line, current_karaoke

try:
    from PIL import Image, ImageDraw, ImageFont
    _PIL = True
except Exception:
    _PIL = False

# ── palette (RGBA) ───────────────────────────────────────────────────────────
_PANEL  = (16, 18, 24, 205)
_BORDER = (255, 255, 255, 28)
_WHITE  = (236, 239, 246, 255)
_DIM    = (152, 157, 170, 255)
_MUTE   = (96, 100, 112, 255)
_TRACK  = (58, 62, 72, 235)
_GREEN  = (84, 222, 140, 255)
_BLUE   = (118, 182, 255, 255)
_PURPLE = (190, 150, 255, 255)
_CYANC  = (122, 202, 255, 255)
_LAV    = (210, 178, 255, 255)
_ACCENT = (242, 112, 70, 255)
_WARN   = (255, 120, 90, 255)
_GOLD   = (255, 214, 130, 255)
_SHADOW = (0, 0, 0, 150)

_FONTS = {}


def _font(size, bold=False):
    key = (size, bold)
    if key not in _FONTS:
        paths = ([r"C:\Windows\Fonts\seguisb.ttf"] if bold else []) + [
            r"C:\Windows\Fonts\segoeui.ttf",
            "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        ]
        f = None
        for p in paths:
            try:
                f = ImageFont.truetype(p, size)
                break
            except Exception:
                continue
        _FONTS[key] = f or ImageFont.load_default()
    return _FONTS[key]


def _tw(d, text, font):
    return d.textlength(text, font=font)


def _scrim(d, W, y0, y1, a0, a1):
    """Vertical alpha gradient strip (a0 at y0 -> a1 at y1)."""
    n = max(1, y1 - y0)
    for i in range(n):
        a = int(a0 + (a1 - a0) * i / n)
        if a > 0:
            d.line([(0, y0 + i), (W, y0 + i)], fill=(8, 9, 12, a))


def _chip(d, x, y, text, font, S):
    """Small key-cap chip with a centered glyph; returns its width."""
    pad = S(7)
    w = d.textlength(text, font=font)
    cw, ch = max(S(20), int(w + 2 * pad)), S(22)
    d.rounded_rectangle([x, y, x + cw, y + ch], radius=S(5),
                        fill=(46, 50, 60, 255), outline=(255, 255, 255, 100), width=1)
    d.text((x + (cw - w) / 2, y + S(3)), text, font=font, fill=_WHITE)
    return cw


def _draw_info(d, W, H, S):
    """Centered 'CONTROLS' help card (toggled with the i key)."""
    sections = [
        ("RIGHT HAND", False, [
            ("fingers up / down", "stem 1-4   on / off"),
            ("fist  /  open hand", "full drop  /  full mix"),
        ]),
        ("LEFT HAND", False, [
            ("raise  /  lower", "low-pass filter"),
            ("open  /  close", "reverb"),
        ]),
        ("KEYS", True, [
            ("space", "play / pause"),
            ("B", "beat-sync  on / off"),
            ("N", "load the next song"),
            ("I", "show / hide this panel"),
            ("Q", "quit"),
        ]),
    ]
    f_title = _font(S(16), bold=True)
    f_sec = _font(S(11), bold=True)
    f_row = _font(S(14))
    f_sm = _font(S(12))

    pad = S(22)
    rowh, hdrh, secgap = S(29), S(24), S(12)
    nrows = sum(len(r) for _, _, r in sections)
    pw = S(468)
    ph = pad + S(34) + len(sections) * hdrh + nrows * rowh + len(sections) * secgap + pad
    px, py = (W - pw) // 2, (H - ph) // 2

    d.rounded_rectangle([px, py, px + pw, py + ph], radius=S(16),
                        fill=(13, 14, 19, 248), outline=_BORDER, width=1)
    x, y = px + pad, py + pad
    d.text((x, y), "CONTROLS", font=f_title, fill=_ACCENT)
    close = "press  I  to close"
    d.text((px + pw - pad - d.textlength(close, f_sm), y + S(4)), close, font=f_sm, fill=_DIM)
    y += S(34)

    ctrl_x, desc_x = x, x + S(196)
    for title, is_key, rows in sections:
        d.text((x, y), title, font=f_sec, fill=_CYANC)
        y += hdrh
        for ctrl, desc in rows:
            cy = y + (rowh - S(18)) // 2
            if is_key:
                _chip(d, ctrl_x, y + (rowh - S(22)) // 2, ctrl, f_sm, S)
            else:
                d.text((ctrl_x, cy), ctrl, font=f_row, fill=_WHITE)
            d.text((desc_x, cy), desc, font=f_row, fill=_DIM)
            y += rowh
        y += secgap


def draw_hud(frame, engine, stem_on, filt, rev, lyric_mode, lyric_data, cyanite_str, fps, audio_ok, show_info=False, song_name=""):
    if not _PIL:
        return _draw_cv2(frame, engine, stem_on, filt, rev,
                         lyric_mode, lyric_data, cyanite_str, fps, audio_ok, show_info, song_name)

    H, W = frame.shape[:2]
    u = min(2.0, max(0.7, H / 720.0))
    S = lambda v: max(1, int(round(v * u)))

    img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).convert("RGBA")
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)

    f_hdr = _font(S(15), bold=True)
    f_lbl = _font(S(15))
    f_num = _font(S(13), bold=True)
    f_bpm = _font(S(18), bold=True)
    f_sub = _font(S(13))
    f_sm = _font(S(12))
    f_lyr = _font(S(27), bold=True)

    # soft scrims so text reads over any background
    _scrim(d, W, 0, S(118), 120, 0)
    _scrim(d, W, H - S(96), H, 0, 150)

    # ── left mixer panel ──────────────────────────────────────────────────────
    m, pad, pw, rh = S(16), S(14), S(244), S(30)
    names = engine.names[:4]
    rows = len(names) + 2
    hdr_h = S(28)
    ph = pad + hdr_h + rows * rh + pad
    d.rounded_rectangle([m, m, m + pw, m + ph], radius=S(13), fill=_PANEL, outline=_BORDER, width=1)

    cx0 = m + pad
    y = m + pad
    d.text((cx0, y), "AIRSTEMS", font=f_hdr, fill=_ACCENT)
    tag = song_name if song_name else "LIVE"
    if len(tag) > 16:
        tag = tag[:15] + "…"
    d.text((m + pw - pad - _tw(d, tag, f_sm), y + S(3)), tag, font=f_sm, fill=_DIM)
    y += hdr_h
    d.line([cx0, y - S(7), m + pw - pad, y - S(7)], fill=_BORDER, width=1)

    bar_x = cx0 + S(94)
    bar_w = (m + pw - pad) - bar_x
    bar_h = S(9)

    def _row(label, frac, color, idx=None, on=True):
        nonlocal y
        ty = y + (rh - S(17)) // 2
        col = color if on else _MUTE
        if idx is not None:
            d.text((cx0, ty), str(idx), font=f_num, fill=col)
            d.text((cx0 + S(16), ty), label, font=f_lbl, fill=col)
        else:
            d.text((cx0, ty), label, font=f_lbl, fill=_DIM)
        by = y + (rh - bar_h) // 2
        d.rounded_rectangle([bar_x, by, bar_x + bar_w, by + bar_h], radius=bar_h // 2, fill=_TRACK)
        fw = int(bar_w * max(0.0, min(1.0, frac)))
        if fw >= bar_h:
            d.rounded_rectangle([bar_x, by, bar_x + fw, by + bar_h], radius=bar_h // 2, fill=color)
        y += rh

    for i, name in enumerate(names):
        on = stem_on[i] if i < len(stem_on) else False
        _row(name, 1.0 if on else 0.0, _GREEN if on else _MUTE, idx=i + 1, on=on)
    _row("filter", filt, _BLUE, on=False)
    _row("reverb", rev, _PURPLE, on=False)

    # ── top-center: beat pulse + BPM + Cyanite, on a backing pill ──────────────
    ccx = W // 2
    has_bpm  = engine.bpm > 0
    bpm_txt  = f"{engine.bpm:.0f} BPM" if has_bpm else ""
    sync_txt = f"beat-sync {'ON' if engine.quantize else 'OFF'}" if has_bpm else ""
    gap = S(14)
    w1 = (_tw(d, bpm_txt, f_bpm) + gap + _tw(d, sync_txt, f_sub)) if has_bpm else 0.0
    lead = "CYANITE   "
    w2 = _tw(d, lead + cyanite_str, f_sub) if cyanite_str else 0.0
    bw = max(w1, w2)
    if bw > 0:                                          # readable backing behind the text
        bot = m + (S(76) if cyanite_str else S(54))
        d.rounded_rectangle([ccx - bw / 2 - S(18), m + S(24), ccx + bw / 2 + S(18), bot],
                            radius=S(12), fill=(0, 0, 0, 150))
    if has_bpm:
        p = max(0.0, min(1.0, engine.beat_pulse))
        cy = m + S(11)
        for rad, a in ((S(9) + S(11) + int(S(10) * p), 60),
                       (S(9) + S(4) + int(S(8) * p), 120)):
            d.ellipse([ccx - rad, cy - rad, ccx + rad, cy + rad], outline=(122, 202, 255, a), width=S(2))
        ir = S(4) + int(S(5) * p)
        d.ellipse([ccx - ir, cy - ir, ccx + ir, cy + ir], fill=(150, 212, 255, int(120 + 135 * p)))
        bx = ccx - w1 / 2
        ty = m + S(30)
        d.text((bx, ty), bpm_txt, font=f_bpm, fill=_WHITE)
        d.text((bx + _tw(d, bpm_txt, f_bpm) + gap, ty + S(4)), sync_txt, font=f_sub,
               fill=_GREEN if engine.quantize else _DIM)
    if cyanite_str:
        sx = ccx - w2 / 2
        ty = m + S(54)
        d.text((sx, ty), lead, font=f_sub, fill=_ACCENT)
        d.text((sx + _tw(d, lead, f_sub), ty), cyanite_str, font=f_sub, fill=_LAV)

    # ── top-right: fps / audio ─────────────────────────────────────────────────
    fps_txt = f"{fps} fps"
    d.text((W - m - _tw(d, fps_txt, f_sm), m), fps_txt, font=f_sm, fill=_DIM)
    if not audio_ok:
        nt = "NO AUDIO"
        d.text((W - m - _tw(d, nt, f_sm), m + S(16)), nt, font=f_sm, fill=_WARN)

    # ── bottom: lyrics / hint ──────────────────────────────────────────────────
    if not names:
        msg = "No stems loaded  —  put WAVs in stems/<song>/"
        d.text((max(S(10), (W - _tw(d, msg, f_lbl)) // 2), H - S(44)), msg, font=f_lbl, fill=_CYANC)
    else:
        text, sung = "", 0
        if lyric_mode == "rich":
            text, sung = current_karaoke(lyric_data, engine.position_seconds)
        elif lyric_mode == "lrc":
            text = current_line(lyric_data, engine.position_seconds)
        if text:
            asc, desc = f_lyr.getmetrics()
            th = asc + desc
            w = _tw(d, text, f_lyr)
            lx = max(S(12), int((W - w) / 2))
            ly = H - S(40) - th
            d.rounded_rectangle([lx - S(18), ly - S(6), lx + w + S(18), ly + th + S(6)],
                                radius=S(11), fill=(0, 0, 0, 150))
            d.text((lx + S(2), ly + S(2)), text, font=f_lyr, fill=_SHADOW)
            if lyric_mode == "rich":
                d.text((lx, ly), text, font=f_lyr, fill=_DIM)
                if sung:
                    d.text((lx, ly), text[:sung], font=f_lyr, fill=_GOLD)
            else:
                d.text((lx, ly), text, font=f_lyr, fill=_WHITE)

    # ── controls: hint chip, or full panel (with dimmed backdrop) when toggled ──
    if show_info:
        d.rectangle([0, 0, W, H], fill=(0, 0, 0, 125))      # dim the video behind the modal
        _draw_info(d, W, H, S)
    else:
        label = "  show controls"
        x0 = W - m - (S(20) + int(_tw(d, label, f_sm)))
        y0 = H - m - S(20)
        cw = _chip(d, x0, y0, "i", f_sm, S)
        d.text((x0 + cw, y0 + S(3)), label, font=f_sm, fill=_DIM)

    out = Image.alpha_composite(img, ov).convert("RGB")
    return cv2.cvtColor(np.asarray(out), cv2.COLOR_RGB2BGR)


# ── plain OpenCV fallback (only if Pillow is missing) ─────────────────────────
def _draw_cv2(frame, engine, stem_on, filt, rev, lyric_mode, lyric_data, cyanite_str, fps, audio_ok, show_info=False, song_name=""):
    F = cv2.FONT_HERSHEY_SIMPLEX
    H, W = frame.shape[:2]

    def bar(x, y, w, h, frac, col):
        cv2.rectangle(frame, (x, y), (x + w, y + h), (60, 60, 60), 1)
        cv2.rectangle(frame, (x, y), (x + int(w * max(0.0, min(1.0, frac))), y + h), col, -1)

    y = 30
    for i, name in enumerate(engine.names[:4]):
        on = stem_on[i] if i < len(stem_on) else False
        col = (80, 230, 120) if on else (90, 90, 90)
        cv2.putText(frame, f"{i + 1} {name}", (20, y + 14), F, 0.6, col, 2)
        bar(150, y, 120, 16, 1.0 if on else 0.0, col)
        y += 28
    y += 6
    cv2.putText(frame, "filter", (20, y + 14), F, 0.55, (200, 200, 200), 1); bar(150, y, 120, 16, filt, (120, 180, 255)); y += 26
    cv2.putText(frame, "reverb", (20, y + 14), F, 0.55, (200, 200, 200), 1); bar(150, y, 120, 16, rev, (200, 150, 255))
    cv2.putText(frame, f"{fps} fps{'' if audio_ok else '  (NO AUDIO)'}", (W - 190, 30), F, 0.6, (180, 180, 180), 1)
    if engine.bpm > 0:
        cv2.putText(frame, f"{engine.bpm:.0f} BPM   beat-sync {'ON' if engine.quantize else 'OFF'}",
                    (W // 2 - 130, 40), F, 0.6, (210, 210, 210), 1)
    if cyanite_str:
        cv2.putText(frame, "Cyanite:  " + cyanite_str, (W // 2 - 200, 64), F, 0.5, (205, 170, 255), 1)
    if engine.names:
        text = ""
        if lyric_mode == "rich":
            text, _ = current_karaoke(lyric_data, engine.position_seconds)
        elif lyric_mode == "lrc":
            text = current_line(lyric_data, engine.position_seconds)
        if text:
            (tw, _), _ = cv2.getTextSize(text, F, 0.9, 2)
            cv2.putText(frame, text, (max(10, (W - tw) // 2), H - 30), F, 0.9, (255, 255, 255), 2)
    if show_info:
        for j, ln in enumerate(["CONTROLS",
                                 "R-hand fingers: stems 1-4 on/off   fist=drop  open=full",
                                 "L-hand: height=filter   open/close=reverb",
                                 "space play/pause   b beat-sync   i info   q quit"]):
            cv2.putText(frame, ln, (40, 96 + j * 26), F, 0.6, (235, 235, 235), 1)
    else:
        cv2.putText(frame, "press i for controls", (W - 250, H - 18), F, 0.5, (165, 165, 165), 1)
    return frame
