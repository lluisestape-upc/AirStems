# AirStems

**Conduct and remix a real song's stems with your bare hands.**
Move your fingers to bring vocals, drums, bass and "other" in and out; raise or lower
your hand to open a filter; open your hand for reverb. Synced lyrics scroll underneath,
karaoke-style.

Entry for the **Musicathon by Musixmatch Pro** (15–21 Jun 2026).

---

## The idea in one line
I take my own **Aetheric Geometry** engine (MediaPipe hand tracking + my real-time DSP
effects) and swap its *source*: instead of oscillators, it plays back and mixes the
**stems separated by LALAL.AI / Demucs**, with **Musixmatch synced lyrics** overlaid.

## What is reused (from my Aetheric Geometry / Gestural-Harmonic-Mapping)
| File | Origin | Role in AirStems |
|---|---|---|
| `gestures.py`, `renderer.py`, `config.py`, `config.yaml` | copied as-is | hand tracking, drawing, constants |
| `stem_engine.py` | **new**, forked from `synth.py` | same `sounddevice` callback + same effects (`_lowpass`, `_comb_reverb`, tremolo); the source changes from oscillators → stem mix |
| `airstems.py` | **new**, adapted from `main.py` | camera loop + gesture→stem mapping + lyric overlay |
| `lalalai.py` / `musixmatch.py` / `cyanite.py` | **new** | the three partner-API clients |

> The hand-tracking + DSP foundation is my own pre-existing open-source instrument,
> *Aetheric Geometry*. The new work for the Musicathon is the multi-stem player, the
> beat-sync engine, and the partner-API integrations.

---

## Setup
```powershell
git clone https://github.com/lluisestape-upc/AirStems.git
cd AirStems
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

### API keys (from the hackathon onboarding / partner channels)
1. **Musixmatch** (`MUSIXMATCH_API_KEY`) — the hackathon Pro key unlocks **synced /
   rich-sync** lyrics (paid on the public API).
2. **LALAL.AI** (`LALAI_LICENSE_KEY`) — header `X-License-Key`. Stem-separation API.
3. **Cyanite** (`CYANITE_API_TOKEN`) — GraphQL, `Authorization: Bearer`. BPM / key / mood.

Copy `.env.example` to `.env` and fill them in — `.env` is gitignored, never committed.

---

## Prepare a song
**Option A — LALAL.AI API:**
```powershell
python lalalai.py "C:\path\song.mp3"     # stems  -> stems/song/
python musixmatch.py "Artist" "Title"      # lyrics -> lyrics/
```
**Option B — local, decoupled (never blocked by an API):**
separate with local **Demucs** (`separate_local.py`) or the LALAL.AI website and drop the
WAVs in `stems/<song>/` (`vocals.wav`, `drums.wav`, `bass.wav`, `other.wav`). The engine
is source-agnostic — it loads whatever WAVs are there, so the API plugs in alongside.

## Run
```powershell
python airstems.py
```

## Gesture map
| Hand | Gesture | Effect |
|---|---|---|
| Right | fingers up/down (index→pinky) | stem 1–4 ON/OFF (anti-flicker dead-zone) |
| Right | **fist** / **open hand** | full drop / full mix |
| Left | wrist height | low-pass filter (down = dark, up = open) |
| Left | open / close hand | reverb (open = full, fist = 0) |
| — | `space` | play / pause |
| — | `b` | **beat-sync ON/OFF** (stem changes snap to the beat) |
| — | `q` | quit |

**Differentiator — beat-sync:** on load, `librosa` detects the BPM and beat grid; with
beat-sync on, the stem changes you make with your hand **don't fire instantly — they snap
to the next beat**, so it always lands musically. Press `b` to show the before/after in
the video. (Cyanite can provide an alternative "official" BPM / key / mood.)

**Stretch ideas:** pinch = solo a single stem · distance between hands = master volume ·
word-by-word rich-sync lyrics · record the remix to WAV.

---

## Status
- Real-time **stereo** engine: stem mix + IIR low-pass + Schroeder reverb + tremolo.
  Tested offline with `smoke_test.py`.
- **Gesture mapping**: fingers → stems (anti-flicker dead-zone), hand height → filter,
  open/close → reverb.
- **Beat-sync** via `librosa` (beat grid on the drums stem; `b` key).
- **Musixmatch** synced lyrics verified; **Demucs** local stem separation verified.
- **LALAL.AI** client implemented against the v1 API (upload verified); **Cyanite**
  (BPM / key / mood) integration in progress.
- Next: demo video + live gesture-threshold tuning.

## For the demo video
- Use **your own** music or a **Creative Commons / royalty-free** track (avoids strikes).
- Record with OBS; 2–3 min; close-up of the hands driving the mix + lyrics.
- Clearly show **which API does what** (stems = LALAL.AI, lyrics = Musixmatch).

## Submission checklist
- [ ] Public repo + README + license
- [ ] Demo video (≤3 min)
- [ ] Devpost write-up (`pitch.md`)
- [ ] "Built with": Musixmatch API, LALAL.AI API, MediaPipe, sounddevice, OpenCV, librosa, Python
- [ ] (Optional) Cyanite / partner credits used

> Note: gesture thresholds and the audio block size are tuned live, depending on the
> camera and each machine's latency.
