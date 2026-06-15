"""Minimal LRC parser for AirStems lyric overlay."""
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
