# Voz propia de ARIA

Crea una voz **femenina, dulce y cálida** para ARIA a partir de las grabaciones de **una persona que da su permiso**,
y la instala en la Raspberry: suena **sin internet, sin cuotas y en tiempo real** (Piper).

> [!IMPORTANT]
> Usa solo la voz de alguien que haya firmado el consentimiento de [GRABACION.md](GRABACION.md). No uses grabaciones
> de otras personas ni audios de servicios de voz (Gemini, ElevenLabs…): la voz resultante sería una copia suya.

## Cómo funciona

```text
1 minuto de voz real ──► Chatterbox (español de España, MIT) ──► ~1.150 frases con esa voz y tono dulce
                                                                       │ Whisper descarta las que salen mal
                                                                       ▼
                     Raspberry (aria-voz) ◄── es_ES-aria-medium.onnx ◄── Piper: ajuste desde la voz española «davefx»
```

| Paso | Dónde | Tiempo |
|---|---|---|
| 1. Grabar ([GRABACION.md](GRABACION.md)) | El móvil de la persona | 5 minutos |
| 2. Parte A del cuaderno: referencia, tono y frases | Google Colab (GPU T4 gratis) | 1–2 h |
| 3. Parte B: filtrar y entrenar | Google Colab, en varias sesiones | 5–8 h |
| 4. Instalar | La Raspberry | 1 minuto |

## Pasos

1. **Grabar.** Pásale [GRABACION.md](GRABACION.md) a la persona: consentimiento, consejos y 25 frases.
2. **Abrir el cuaderno** [ARIA_voz_propia.ipynb](ARIA_voz_propia.ipynb) en Google Colab (*Archivo → Subir cuaderno*) y
   poner la GPU T4 (*Entorno de ejecución → Cambiar tipo*).
3. **Subir las grabaciones** a Google Drive → `ARIA-voz/grabaciones/`.
4. **Parte A:** elige el trozo de referencia más limpio, escucha la cuadrícula de tonos y elige el más dulce; genera las frases.
5. **Parte B:** reinicia el entorno, filtra con Whisper y entrena. Si Colab corta la sesión, vuelve a ejecutar las celdas:
   **continúa** desde el último punto guardado en Drive. A partir de ~400 épocas ya suele sonar bien; 800 es lo ideal.
6. **Instalar en ARIA:** copia `es_ES-aria-medium.onnx` y `es_ES-aria-medium.onnx.json` de Drive (`ARIA-voz/piper/`) a
   `~/homelab/ARIA/data/voz-propia/` en la Raspberry. ARIA la detecta sola (no hace falta reiniciar):
   - aparece arriba del todo en **Ajustes → Voz → Voz de ARIA** como «Voz propia de ARIA», con ▶ para probarla;
   - y pasa a ser la voz de **reserva** para todos cuando se agota la cuota de Gemini.

## Archivos

| Archivo | Para qué |
|---|---|
| [GRABACION.md](GRABACION.md) | Consentimiento, cómo grabar y las frases |
| [ARIA_voz_propia.ipynb](ARIA_voz_propia.ipynb) | El cuaderno de Colab (se genera con `crear_cuaderno.py`) |
| [corpus.py](corpus.py) | Las ~1.150 frases de entrenamiento (castellano, el día a día de ARIA) |

## Probado

El proceso de entrenamiento se ha probado de principio a fin en una Raspberry Pi 5 con un conjunto mínimo:
arrancar desde la voz española de Piper, entrenar, reanudar tras un corte, exportar a ONNX y hacer hablar a la voz
desde `aria-voz` (unos 4 s de audio en 0,85 s). Tres detalles que el cuaderno ya resuelve:

- El punto de partida es de una versión antigua de Piper: se usa `--model.warmstart_ckpt` (no `--ckpt_path`).
- En modo desarrollo hay que compilar el puente de espeak-ng: `python3 setup.py build_ext --inplace` (con `scikit-build`).
- Las versiones recientes de PyTorch exportan con otro motor que falla con Piper: se fuerza el clásico (`dynamo=False`).

## Privacidad y permiso

Las grabaciones, las frases generadas y la voz son **personales**: no las subas a ningún repositorio ni las compartas.
Si la persona retira su permiso, borra `ARIA-voz/` de Google Drive y `data/voz-propia/` de la Raspberry.
