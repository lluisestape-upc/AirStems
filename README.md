# AirStems 🖐️🎚️

**Dirige y remezcla los stems de una canción real con las manos.**
Mueves los dedos para meter/quitar voz, batería, bajo y "otros"; subes/bajas la
mano para abrir un filtro; abres la mano para añadir reverb. La letra
sincronizada va por debajo, en karaoke.

Entrada para el **Musicathon by Musixmatch Pro** (15–21 jun 2026).

---

## La idea en una frase
Cojo mi motor de **Aetheric Geometry** (tracking de manos MediaPipe + mis efectos
de DSP en tiempo real) y le cambio la *fuente*: en lugar de osciladores, reproduzco
y mezclo los **stems que separa LALAL.AI**, con la **letra sincronizada de Musixmatch**
superpuesta.

## Qué se reutiliza (de Gestural-Harmonic-Mapping)
| Fichero | Origen | Rol en AirStems |
|---|---|---|
| `gestures.py`, `renderer.py`, `config.py`, `config.yaml` | copiados tal cual | manos, dibujo, constantes |
| `stem_engine.py` | **nuevo**, forkeado de `synth.py` | mismo `sounddevice` + mismos efectos (`_lowpass`, `_comb_reverb`, trémolo); la fuente pasa de osciladores → mezcla de stems |
| `airstems.py` | **nuevo**, adaptado de `main.py` | bucle de cámara + mapeo gestos→stems + overlay de letra |
| `lalalai.py` | **nuevo** | separa una canción en stems (API LALAL.AI) |
| `musixmatch.py` | **nuevo** | descarga la letra sincronizada (.lrc) |

---

## Puesta en marcha
```powershell
cd $env:USERPROFILE\Desktop\Llluis\AirStems
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

### Claves de API (consíguelas del onboarding / canales del hackathon)
1. **Musixmatch** (`MUSIXMATCH_API_KEY`) — del onboarding `musicathon.replit.app/onboarding`.
   Es la key Pro del hackathon, con acceso a **synced/richsync** (en la API pública eso es de pago).
2. **LALAL.AI** (`LALAI_LICENSE_KEY`) — del canal `#lalala-ai`. Header `X-License-Key`. **Gratis toda la semana.**
3. **Cyanite** (`CYANITE_API_TOKEN`) — token del dashboard de Cyanite (GraphQL, `Authorization: Bearer`). BPM/tono/mood.

Guárdalas en `.env` (copia de `.env.example`) — está gitignored, no se sube ni aparece en chat.

---

## Preparar una canción
**Opción A — API (lo suyo para la demo):**
```powershell
python lalalai.py "C:\ruta\cancion.mp3"   # baja los stems a stems/cancion/
python musixmatch.py "Artista" "Titulo"    # baja la letra a lyrics/
```
**Opción B — desacoplado (para no quedarte bloqueado si la API tarda):**
pre-separa 1–2 canciones desde la **web de LALAL.AI** o con **Demucs** local y deja
los WAV en `stems/<cancion>/` (`vocals.wav`, `drums.wav`, `bass.wav`, `other.wav`).
El motor funciona igual; la API la enchufas en paralelo.

## Ejecutar
```powershell
python airstems.py
```

## Mapa de gestos (MVP — ajústalo a tu gusto)
| Mano | Gesto | Efecto |
|---|---|---|
| Derecha | dedos arriba/abajo (índice→meñique) | stem 1–4 ON/OFF (con zona muerta anti-parpadeo) |
| Derecha | **puño** / **mano abierta** | drop total / mezcla completa |
| Izquierda | altura de la muñeca | filtro paso-bajo (abajo=oscuro, arriba=abierto) |
| Izquierda | apertura pulgar↔meñique | reverb |
| — | `espacio` | play/pausa |
| — | `b` | **beat-sync ON/OFF** (los cambios de stem encajan al beat) |
| — | `q` | salir |

**Diferenciador ya implementado — beat-sync:** al cargar, `librosa` detecta BPM y la
rejilla de beats; con beat-sync activo, los cambios de stem que pides con la mano
**no saltan al instante, se cuadran al siguiente beat** → siempre suena musical.
Pulsa `b` para enseñar el antes/después en el vídeo. (BPM alternativo vía **Cyanite**.)

**Ideas de stretch:** pinch = solo de un stem · distancia entre manos = volumen
master · richsync palabra-por-palabra · grabar la remezcla a WAV (ya tienes el
código en `synth.py`).

---

## Plan de semana (con el examen de PSAVC el 19 en medio)
| Fechas | Foco |
|---|---|
| **Hoy–12** | Registrarte (cierra el **12**). Conseguir keys + créditos. Pre-separar 1 canción. Ya tienes el esqueleto corriendo. |
| **13–14 (finde)** | Que suene end-to-end: stems mezclándose con las manos + 1 efecto + letra. **Hito clave antes del crunch.** |
| **15–18** | Crunch de examen. Proyecto congelado, ~1h/día de pulido. |
| **19** | Examen. Por la tarde, con el DSP fresco, añade el diferenciador (cuantización al beat / segundo efecto / solo). |
| **20** | Pulir + grabar el vídeo de 2–3 min + writeup (usa `pitch.md`). |
| **21** | Enviar pronto, con margen. |

## Para el vídeo de Devpost
- Usa **tu propia música** o un tema **Creative Commons / libre de derechos** (evitas strikes).
- Graba con OBS; 2–3 min; primer plano de las manos moviendo la mezcla + letra.
- Enseña claramente **qué API hace qué** (stems = LALAL.AI, letra = Musixmatch).

## Checklist de entrega
- [ ] Repo público + README + licencia
- [ ] Vídeo demo (≤3 min)
- [ ] Texto Devpost (`pitch.md`)
- [ ] "Built with": Musixmatch API, LALAL.AI API, MediaPipe, sounddevice, OpenCV, Python
- [ ] (Opcional) Cyanite / créditos de partners usados

> ⚠️ Esqueleto **sin probar** en esta máquina (no hay cámara/audio/keys aquí).
> Espera afinar umbrales de gestos y el blocksize de audio al ejecutarlo.
