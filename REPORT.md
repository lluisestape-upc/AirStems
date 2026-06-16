# AirStems — Report de funcionalidad

**Qué es:** un instrumento que convierte la *separación de stems* + la *letra sincronizada*
en una **performance en directo**. Una webcam te sigue las manos y, con gestos,
remezclas en tiempo real las pistas de una canción (voz / batería / bajo / otros),
con los cambios **cuadrados al beat** y la **letra en karaoke**.

**Estado (2026-06-15):** núcleo **verificado offline** — separación local (Demucs),
motor de audio **estéreo**, detección de beats sobre el stem de batería
(129.2 BPM / 363 beats en la canción de prueba) y la app con tracking de manos + HUD + letra.
**APIs:** Musixmatch (letra sincronizada *y* rich sync palabra-por-palabra) **verificada**;
LALAL.AI *upload* verificado (la separación pide la licencia premium del hackathon);
Cyanite (BPM/tono/mood) **verificada** end-to-end (con MP3; la API falla en WAV).

---

## 1. Cómo funciona — dos flujos

**Flujo de AUDIO (qué suena):**
```
Canción ──▶  separador        ──▶  stems/<cancion>/{vocals,drums,bass,other}.wav
             (Demucs o LALAL.AI)
                                         │
                                         ▼
                      StemEngine: carga stems + detecta beat grid (librosa)
                                         │   callback sounddevice (44.1 kHz, bloque 512)
                                         ▼
        mezcla (gain por stem) ─▶ filtro paso-bajo ─▶ reverb ─▶ trémolo ─▶ salida
```

**Flujo de CONTROL (qué haces tú):**
```
Webcam ─▶ MediaPipe (2 manos) ─▶ landmarks
   ├─ mano derecha : dedos arriba/abajo   ─▶ gain ON/OFF por stem (con histéresis)
   ├─ mano izquierda: altura de la muñeca ─▶ filtro ; abrir/cerrar la mano ─▶ reverb
   └─ beat-sync (tecla b)                 ─▶ los cambios de gain se aplican en el siguiente beat
Letra (.lrc por línea  o  rich sync palabra-por-palabra) ─▶ karaoke sincronizado
```

---

## 2. Controles

> Primero **haz clic en la ventana "AirStems"** para que tenga el foco del teclado.

| Acción | Gesto / tecla |
|---|---|
| Play / pausa | `espacio` |
| Beat-sync ON/OFF | `b` |
| Cambiar de canción (siguiente) | `n` |
| Info / panel de controles | `i` |
| Salir | `q` |
| Stems 1–4 ON/OFF | mano derecha: subir/bajar cada dedo (índice→meñique) |
| Drop total / mezcla completa | puño / mano abierta |
| Filtro paso-bajo | mano izquierda: altura de la muñeca (abajo = oscuro, arriba = abierto) |
| Reverb | mano izquierda: abrir / cerrar la mano (abierta = full, puño = 0) |

Los dedos usan **histéresis** (`UP_MARGIN`/`DOWN_MARGIN`) para no parpadear en el umbral;
el filtro y la reverb usan **suavizado EMA** (`SMOOTH`).

---

## 3. El diferenciador — toggles cuadrados al beat

Al cargar la canción, **librosa** detecta el BPM y el tiempo de cada beat. Con beat-sync **ON**,
cuando muteas o activas un stem el cambio **no es instantáneo**: se guarda como *pendiente* y
se aplica en el **siguiente beat** (el callback de audio comprueba si cae un beat dentro del
bloque actual; el wrap del bucle cuenta como downbeat). Así cada *drop* y cada entrada **caen a
tiempo** y suenan intencionados. Con beat-sync **OFF**, los cambios son inmediatos.
Las transiciones de gain usan una **rampa por bloque** → sin clicks.

---

## 4. Motor de audio (`StemEngine`)

- Reproduce en bucle N stems (**estéreo**, 44.1 kHz) en un callback de **sounddevice** (bloque 512).
- **Mezcla** = Σ (stem × gain) con rampa de gain por bloque, × master; efectos **por canal** (estéreo).
- **Cadena de efectos** (reutilizada de tu `synth.py` de *Aetheric Geometry*):
  - Filtro **IIR paso-bajo** de 1er orden (corte 200–8000 Hz según altura de mano).
  - **Reverb Schroeder** (4 comb filters, feedback 0.82), wet suavizado.
  - **Trémolo** (LFO 0.5–10 Hz).
- Expone: `position_seconds` (sincroniza la letra), `bpm`, `beat_pulse` (HUD), `quantize`.

---

## 5. Letra / karaoke (`lyrics.py`)

Parsea un `.lrc` (timestamps `[mm:ss.xx]`) y devuelve la **línea activa** según la posición de
reproducción del motor. También soporta el **rich sync** de Musixmatch (`.richsync.json`): timing
**palabra por palabra**, y el HUD resalta la parte ya cantada (`current_karaoke`). Si hay rich sync
se prefiere; si no, cae al `.lrc`.

---

## 6. Origen de los stems (desacoplado) + APIs de partners

El motor **solo carga WAVs** de `stems/<cancion>/` — le da igual quién los generó. Por eso las
fuentes son **intercambiables** — descubre **todas** las canciones bajo `stems/`, se alternan
**en vivo** con `n`, y empareja `lyrics/<nombre>` + `analysis/<nombre>` por nombre:

| Módulo | Partner | Rol |
|---|---|---|
| `separate_local.py` | — (Demucs, open-source) | separación **local/offline**, sin key → desarrollo y *fallback* |
| `lalalai.py` | **LALAL.AI** | separación en la nube (v1 API) → integración **oficial** para la entrega |
| `musixmatch.py` | **Musixmatch** | descarga la **letra sincronizada** (`.lrc`) |
| `cyanite.py` | **Cyanite** | **BPM / tono / mood** "oficial" (librosa hace la rejilla de beats local) |

---

## 7. HUD (lo que se ve en pantalla)

- Barra por stem (verde = ON, gris = off).
- Barras de **filtro** y **reverb**.
- **Pulso** circular en cada beat + **BPM** + estado de beat-sync.
- **Línea de letra** sincronizada.
- Contador de **FPS**.

---

## 8. Componentes (ficheros)

| Fichero | Rol |
|---|---|
| `airstems.py` | bucle principal: cámara, tracking, mapeo gestos→params, HUD, teclas |
| `stem_engine.py` | `StemEngine`: audio en tiempo real, mezcla, efectos, beat grid + beat-sync |
| `lyrics.py` | parser LRC + línea actual |
| `separate_local.py` | separación local con Demucs (carga audio vía soundfile) |
| `lalalai.py` | cliente LALAL.AI v1 (`upload → split → check → download`) |
| `musixmatch.py` | cliente de letra sincronizada |
| `cyanite.py` | cliente de análisis (BPM/tono/mood) |
| `smoke_test.py` | verificación headless (sin cámara ni altavoz) |
| `gestures.py`, `renderer.py`, `config.py` + `config.yaml` | reutilizados de *Aetheric Geometry* (landmarks, dibujo, constantes) |

---

## 9. Stack técnico

Python · OpenCV · MediaPipe · sounddevice · soundfile · NumPy · librosa
· (Demucs / torch para separación local) · APIs: **LALAL.AI**, **Musixmatch**, **Cyanite**.

---

## 10. Cómo ejecutar

Con el venv de *Aetheric* (mediapipe 0.10.9, que sí tiene `mp.solutions`):
```powershell
& "C:\Users\luigi\Desktop\Llluis\Gestural-Harmonic-Mapping\venv\Scripts\python.exe" `
  "C:\Users\luigi\Desktop\Llluis\AirStems\airstems.py"
```
Separar otra canción:
```powershell
python separate_local.py "C:\ruta\cancion.wav"      # local (Demucs)
python lalalai.py        "C:\ruta\cancion.wav"      # LALAL.AI (con key)
```

---

## 11. Pendiente / próximos pasos

- **Cyanite:** **verificado** end-to-end — análisis V7 (BPM/tono/mood) funcionando con MP3 (la API
  falla en WAV PCM-16). Falta surtir BPM/mood al HUD.
- **LALAL.AI:** correr una separación real al activarse la licencia premium del hackathon
  (hoy: *upload* verificado; Demucs cubre desarrollo y demo).
- **Mío (post-examen):** afinar umbrales de gestos en vivo, elegir tema y grabar el vídeo.
- **Stretch:** export de la remezcla a WAV · `pinch` = solo de un stem · volumen master con la
  distancia entre manos.
