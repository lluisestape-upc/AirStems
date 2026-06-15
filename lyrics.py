"""Minimal LRC + Musixmatch rich-sync parser for AirStems lyric overlay."""
import json
import re

_TS = re.compile(r"\[(\d+):(\d+)(?:[.:](\d+))?\]")


def parse_lrc(path: str):
    """Return a sorted list of (time_seconds, text)."""
    lines = []
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            stamps = list(_TS.finditer(raw))
            if not stamps:
                continue
            text = _TS.sub("", raw).strip()
            for m in stamps:
                mm   = int(m.group(1))
                ss   = int(m.group(2))
                frac = m.group(3) or "0"
                t    = mm * 60 + ss + int(frac) / (10 ** len(frac))
                lines.append((t, text))
    lines.sort(key=lambda x: x[0])
    return lines


def current_line(lines, t: float) -> str:
    """The last lyric line whose timestamp has passed."""
    cur = ""
    for ts, text in lines:
        if ts <= t:
            cur = text
        else:
            break
    return cur


def parse_richsync(path: str):
    """Load a saved Musixmatch rich-sync JSON.

    Returns a sorted list of (ts, te, text, words), where words is a list of
    (segment_text, absolute_time) and absolute_time = line start + word offset.
    """
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    out = []
    for ln in data:
        ts = float(ln.get("ts", 0.0))
        te = float(ln.get("te", ts))
        words = [(w.get("c", ""), ts + float(w.get("o", 0.0))) for w in ln.get("l", [])]
        out.append((ts, te, ln.get("x", ""), words))
    out.sort(key=lambda e: e[0])
    return out


def current_karaoke(rich, t: float):
    """For time t, return (line_text, sung_chars) for the active rich-sync line.

    sung_chars = number of leading characters of line_text already reached, so a
    HUD can draw text[:sung_chars] highlighted and text[sung_chars:] dim.
    Returns ("", 0) before the first line.
    """
    active = None
    for entry in rich:
        if entry[0] <= t:
            active = entry
        else:
            break
    if active is None:
        return "", 0
    _ts, _te, text, words = active
    sung = 0
    for seg, at in words:
        if at <= t:
            sung += len(seg)
        else:
            break
    return text, sung
