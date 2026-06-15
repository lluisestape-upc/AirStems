# AirStems — submission draft

> Paste this into the hub project form on **Monday, June 15** (projects unlock at
> kickoff — until then the form 403s on save). Fields below match the form.

---

## Project Title
```
AirStems
```

## One-Liner
```
Conduct and remix any song's stems with your bare hands — beat-locked, in real time, with synced karaoke lyrics.
```

## Full Description (Markdown)
```markdown
# AirStems 🖐️🎚️
**Pull any song apart and play it back with your hands — beat-locked.**

Stem separation and synced lyrics usually live behind a mouse and a timeline. AirStems turns them into a live instrument: point a webcam at your hands and *perform* the song — raise a finger to bring the vocal in, make a fist to drop the whole band, lift your hand to open a filter, open your palm for reverb. Every change snaps to the beat, so it always lands musically.

## What it does
- **LALAL.AI** splits any track into stems (vocals / drums / bass / other).
- **MediaPipe** tracks both hands in real time:
  - *right hand* — each finger mutes/unmutes a stem (fist = full drop, open hand = full mix)
  - *left hand* — height = low-pass filter, open/close = reverb
- **Beat-synced toggles** — a beat grid (librosa + **Cyanite** BPM/key/mood) quantizes every change to the next beat, so drops and returns always land on time.
- **Musixmatch** synced lyrics scroll in karaoke underneath (line-level subtitles → word-by-word rich sync).
- A custom **stereo, real-time DSP engine** mixes the stems and runs the effects live — no pre-rendered audio.

## How I built it
Python: OpenCV + MediaPipe for hands; a `sounddevice` callback that mixes the stem buffers in stereo and applies a per-channel effect chain (IIR low-pass + Schroeder reverb + tremolo). The hand-tracking and DSP build on my own open-source gesture instrument, *Aetheric Geometry*; the new work for the Musicathon is the multi-stem player, the beat-sync engine, and the three partner-API integrations.

## Challenges
- Click-free, **beat-quantized** stem switching (per-block gain ramps committed on the beat).
- Glitch-free audio while computer vision runs on the main thread (audio thread measured at ~11% load).
- Turning noisy hand landmarks into musical control that *feels* intentional (hysteresis + smoothing + scale-invariant open/close).

## Built with
python · musixmatch-api · lalal-ai-api · cyanite · mediapipe · opencv · sounddevice · numpy · librosa
```

## APIs & partner services to tick
- [x] **Musixmatch Subtitles**  (synced LRC — core)
- [x] **Musixmatch Rich Sync**  (word-by-word karaoke — BUILT + verified, Pro key has access)
- [x] **LALAL.ai**  (stem separation — core)
- [ ] Musixmatch Lyrics  (optional — Subtitles already covers it)
- [ ] Metadata / Search / Translations / Replit / Songstats  (not used)
- Note: **Cyanite has no checkbox** on the form → it's credited in the Full Description instead.

## Don't forget at submission
- Repo URL (public, started at kickoff; discloses the Aetheric Geometry base)
- 2–3 min demo video (own / royalty-free track to avoid copyright strikes)
