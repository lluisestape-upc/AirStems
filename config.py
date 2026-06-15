"""Loads config.yaml and exposes flat constants. Falls back to defaults if YAML is unavailable."""
import logging
from pathlib import Path

log = logging.getLogger(__name__)

_DEFAULTS: dict = {
    "thresholds": {
        "pinch": 60, "double_pinch": 90, "pyramid": 70,
        "prayer_dist": 160, "open_palm_spread": 100,
    },
    "timing": {"cooldown_frames": 45, "rasengan_hold": 20, "rasengan_duration": 60},
    "colors": {
        "panel_bg": [18, 12, 28], "panel_border": [65, 55, 95],
        "neon_green": [70, 230, 90], "neon_cyan": [240, 210, 40],
        "neon_pink": [215, 65, 230], "text_dim": [145, 135, 165],
        "near_white": [230, 225, 242], "warm_red": [40, 40, 220],
        "rasengan_blue": [220, 100, 20], "rasengan_cyan": [255, 210, 70],
        "rasengan_white": [255, 255, 255],
    },
    "audio": {
        "sample_rate": 44100, "block_size": 512,
        "amplitude_hilo": 0.28, "amplitude_polygon": 0.22,
        "attack_alpha": 0.008, "release_alpha": 0.002,
        "reverb_tail_alpha": 0.0005, "reverb_feedback": 0.82,
        "midi_port": None,
    },
    "mediapipe": {
        "min_detection_confidence": 0.65,
        "min_tracking_confidence": 0.65,
        "max_num_hands": 2,
    },
    "camera": {"index": 0},
}


def _deep_merge(defaults: dict, overrides: dict) -> dict:
    result = {}
    for key, default_val in defaults.items():
        if key in overrides:
            if isinstance(default_val, dict) and isinstance(overrides[key], dict):
                result[key] = _deep_merge(default_val, overrides[key])
            else:
                result[key] = overrides[key]
        else:
            result[key] = default_val
    return result


def _load() -> dict:
    cfg_path = Path(__file__).parent / "config.yaml"
    try:
        import yaml
        with open(cfg_path, encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
        log.debug("Loaded config from %s", cfg_path)
        return _deep_merge(_DEFAULTS, loaded)
    except ImportError:
        log.warning("pyyaml not installed — using defaults. Run: pip install pyyaml")
    except FileNotFoundError:
        log.warning("config.yaml not found — using defaults.")
    except Exception as exc:
        log.warning("Failed to load config.yaml (%s) — using defaults.", exc)
    return _DEFAULTS


_cfg = _load()


def _color(key: str) -> tuple:
    return tuple(_cfg["colors"][key])


# ── Thresholds ────────────────────────────────────────────────────────────────
PINCH_THRESH        = float(_cfg["thresholds"]["pinch"])
DOUBLE_PINCH_THRESH = float(_cfg["thresholds"]["double_pinch"])
PYRAMID_THRESH      = float(_cfg["thresholds"]["pyramid"])
PRAYER_DIST         = float(_cfg["thresholds"]["prayer_dist"])
OPEN_PALM_SPREAD    = float(_cfg["thresholds"]["open_palm_spread"])

# ── Timing ────────────────────────────────────────────────────────────────────
COOLDOWN_FRAMES   = int(_cfg["timing"]["cooldown_frames"])
RASENGAN_HOLD     = int(_cfg["timing"]["rasengan_hold"])
RASENGAN_DURATION = int(_cfg["timing"]["rasengan_duration"])

# ── Colors ────────────────────────────────────────────────────────────────────
PANEL_BG       = _color("panel_bg")
PANEL_BORDER   = _color("panel_border")
NEON_GREEN     = _color("neon_green")
NEON_CYAN      = _color("neon_cyan")
NEON_PINK      = _color("neon_pink")
TEXT_DIM       = _color("text_dim")
NEAR_WHITE     = _color("near_white")
WARM_RED       = _color("warm_red")
RASENGAN_BLUE  = _color("rasengan_blue")
RASENGAN_CYAN  = _color("rasengan_cyan")
RASENGAN_WHITE = _color("rasengan_white")

# ── Audio ─────────────────────────────────────────────────────────────────────
SAMPLE_RATE       = int(_cfg["audio"]["sample_rate"])
BLOCK_SIZE        = int(_cfg["audio"]["block_size"])
AMPLITUDE_HILO    = float(_cfg["audio"]["amplitude_hilo"])
AMPLITUDE_POLYGON = float(_cfg["audio"]["amplitude_polygon"])
ATTACK_ALPHA      = float(_cfg["audio"]["attack_alpha"])
RELEASE_ALPHA     = float(_cfg["audio"]["release_alpha"])
REVERB_TAIL_ALPHA = float(_cfg["audio"]["reverb_tail_alpha"])
REVERB_FEEDBACK   = float(_cfg["audio"]["reverb_feedback"])
MIDI_PORT         = _cfg["audio"]["midi_port"]

# ── MediaPipe ─────────────────────────────────────────────────────────────────
MP_MIN_DETECTION = float(_cfg["mediapipe"]["min_detection_confidence"])
MP_MIN_TRACKING  = float(_cfg["mediapipe"]["min_tracking_confidence"])
MP_MAX_HANDS     = int(_cfg["mediapipe"]["max_num_hands"])

# ── Camera ────────────────────────────────────────────────────────────────────
CAMERA_INDEX = int(_cfg["camera"]["index"])
