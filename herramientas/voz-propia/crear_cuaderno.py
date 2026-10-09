"""Genera ARIA_voz_propia.ipynb (cuaderno de Google Colab). Así el cuaderno se revisa como código normal.

Uso: python3 crear_cuaderno.py   → escribe ARIA_voz_propia.ipynb junto a este archivo
"""
import json
from pathlib import Path

CELDAS = []


def md(texto):
    CELDAS.append({"cell_type": "markdown", "metadata": {}, "source": texto.strip("\n").splitlines(keepends=True)})


def code(texto):
    CELDAS.append({"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
                   "source": texto.strip("\n").splitlines(keepends=True)})


md("""
# 🎙️ Voz propia de ARIA

Crea una voz **femenina, dulce y cálida** a partir de las grabaciones de una persona que ha dado su permiso
(ver `GRABACION.md`), y la deja lista para la Raspberry (Piper, sin internet ni cuotas).

**Antes de empezar:** *Entorno de ejecución → Cambiar tipo de entorno de ejecución → GPU T4*.

| Parte | Qué hace | Tiempo aprox. (T4 gratis) |
|---|---|---|
| **A** | Prepara la referencia, prueba tonos y genera ~1.150 frases con la voz (Chatterbox, español de España) | 1–2 h |
| **B** | Filtra las frases con Whisper y entrena la voz de Piper | 5–8 h, en varias sesiones |

Todo se guarda en **Google Drive → `ARIA-voz/`**: si Colab corta la sesión, vuelve a ejecutar las celdas de la parte
en la que estabas y **continúa donde lo dejó**.

> Entre la parte A y la B: *Entorno de ejecución → Desconectar y eliminar el entorno de ejecución* (usan versiones distintas de PyTorch).
""")

md("## 0 · Drive y GPU (ejecútala siempre al empezar)")
code("""
from google.colab import drive
drive.mount('/content/drive')
import os, subprocess, pathlib
BASE = pathlib.Path('/content/drive/MyDrive/ARIA-voz')
for d in ['grabaciones', 'referencia', 'frases/wav', 'piper']:
    (BASE / d).mkdir(parents=True, exist_ok=True)
print(subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader'], capture_output=True, text=True).stdout or '⚠️ Sin GPU: cámbiala en Entorno de ejecución')
print('Carpeta de trabajo:', BASE)
print('Grabaciones encontradas:', [p.name for p in (BASE / 'grabaciones').iterdir()])
""")

md("""
# Parte A · Crear la voz

### A1 · Sube las grabaciones
Copia los archivos tal cual salen del móvil (m4a, mp3, wav…) a **Drive → `ARIA-voz/grabaciones/`** y vuelve a ejecutar la celda 0.
""")
code("""
!apt-get -qq install -y ffmpeg > /dev/null
!pip -q install "chatterbox-tts @ git+https://github.com/resemble-ai/chatterbox.git" librosa soundfile pyloudnorm huggingface_hub
""")

md("""
### A2 · Preparar la referencia
Une las grabaciones, quita silencios largos, iguala el volumen y guarda **varios trozos de ~12 s** para escuchar.
Elige el que suene **más limpio, dulce y natural** (sin ruidos ni titubeos).
""")
code("""
import librosa, numpy as np, soundfile as sf, pyloudnorm as pyln
from IPython.display import Audio, display
SR = 24000
partes = []
for p in sorted((BASE / 'grabaciones').iterdir()):
    y, _ = librosa.load(str(p), sr=SR, mono=True)
    trozos = librosa.effects.split(y, top_db=35)
    partes += [y[a:b] for a, b in trozos if (b - a) > SR * 0.6]
voz = np.concatenate([np.concatenate([t, np.zeros(int(SR * 0.25))]) for t in partes])
voz = pyln.normalize.loudness(voz, pyln.Meter(SR).integrated_loudness(voz), -20.0)
voz = voz / max(1.0, np.abs(voz).max() / 0.95)
print(f'{len(voz) / SR:.0f} s de voz útil')
candidatos = []
for i, ini in enumerate(range(0, max(1, len(voz) - SR * 12), SR * 10)):
    ruta = BASE / 'referencia' / f'candidato_{i:02d}.wav'
    sf.write(ruta, voz[ini:ini + SR * 12], SR)
    candidatos.append(ruta)
    print(ruta.name); display(Audio(str(ruta)))
""")
code("""
#@title Elige el trozo de referencia { run: "auto" }
CANDIDATO = 0 #@param {type:"integer"}
import shutil
shutil.copy(BASE / 'referencia' / f'candidato_{CANDIDATO:02d}.wav', BASE / 'referencia' / 'referencia.wav')
display(Audio(str(BASE / 'referencia' / 'referencia.wav')))
""")

md("""
### A3 · Cargar Chatterbox en español de España
Usa la versión ajustada al castellano (`ResembleAI/Chatterbox-Multilingual-es-es`, licencia MIT). Si no carga,
cae al modelo multilingüe general (v3).
""")
code("""
import torch, torchaudio as ta, shutil, pathlib
from huggingface_hub import snapshot_download, hf_hub_download
from chatterbox.mtl_tts import ChatterboxMultilingualTTS
base = snapshot_download('ResembleAI/chatterbox', allow_patterns=['ve.pt', 's3gen.pt', 'conds.pt', 'grapheme_mtl_merged_expanded_v1.json', 't3_mtl23ls_v3.safetensors'])
try:
    for f in ['t3_es_es.safetensors', 'grapheme_mtl_merged_expanded_v1.json']:
        shutil.copy(hf_hub_download('ResembleAI/Chatterbox-Multilingual-es-es', f), base)
    try:
        shutil.copy(hf_hub_download('ResembleAI/Chatterbox-Multilingual-es-es', 's3gen_v3.pt'), pathlib.Path(base) / 's3gen.pt')
    except Exception as e:
        print('Sin s3gen_v3.pt propio; se usa el general:', e)
    modelo = ChatterboxMultilingualTTS.from_local(base, 'cuda', t3_model='t3_es_es.safetensors')
    print('✅ Chatterbox español de España')
except Exception as e:
    print('⚠️ No cargó la versión es-ES (', e, '): uso la multilingüe v3')
    modelo = ChatterboxMultilingualTTS.from_pretrained('cuda', t3_model='v3')
REF = str(BASE / 'referencia' / 'referencia.wav')
""")

md("""
### A4 · Probar el tono
*Expresividad* sube la emoción (y el ritmo); *Guía* más baja = más pausado y natural. Escucha la cuadrícula y
apunta la combinación que suene **más dulce, cálida y tranquila**.
""")
code("""
PRUEBAS = ['Hola, buenos días. ¿Qué tal has dormido? Hoy hace un día precioso.',
           'Te recuerdo que a las cinco y media tienes cita en el dentista. No te preocupes, yo te aviso.',
           'Buenas noches, cariño. Que descanses, mañana será un gran día.']
for exp in [0.35, 0.5, 0.65]:
    for cfg in [0.3, 0.5]:
        wav = modelo.generate(PRUEBAS[0] + ' ' + PRUEBAS[2], language_id='es', audio_prompt_path=REF, exaggeration=exp, cfg_weight=cfg)
        print(f'Expresividad {exp} · Guía {cfg}'); display(Audio(wav.squeeze(0).numpy(), rate=modelo.sr))
""")
code("""
#@title Tono elegido
EXPRESIVIDAD = 0.5 #@param {type:"slider", min:0.25, max:0.9, step:0.05}
GUIA = 0.4 #@param {type:"slider", min:0.0, max:0.8, step:0.05}
TEMPERATURA = 0.7 #@param {type:"slider", min:0.4, max:1.0, step:0.05}
for t in PRUEBAS:
    display(Audio(modelo.generate(t, language_id='es', audio_prompt_path=REF, exaggeration=EXPRESIVIDAD, cfg_weight=GUIA, temperature=TEMPERATURA).squeeze(0).numpy(), rate=modelo.sr))
(BASE / 'tono.json').write_text(json.dumps({'exaggeration': EXPRESIVIDAD, 'cfg_weight': GUIA, 'temperature': TEMPERATURA}))
""".replace("(BASE / 'tono.json')", "import json\n(BASE / 'tono.json')"))

md("""
### A5 · Generar las frases
~1.150 frases (de `corpus.py`). Se guardan a 22.050 Hz en `ARIA-voz/frases/wav/`. **Si se corta, vuelve a ejecutar
A1, A3 y esta celda**: se salta las que ya existen.
""")
code("""
import json, urllib.request, time
URL_CORPUS = 'https://raw.githubusercontent.com/BertMarti/ARIA/main/herramientas/voz-propia/corpus.py'
destino = BASE / 'corpus.py'
if not destino.exists():
    urllib.request.urlretrieve(URL_CORPUS, destino)
import importlib.util
spec = importlib.util.spec_from_file_location('corpus', destino); corpus = importlib.util.module_from_spec(spec); spec.loader.exec_module(corpus)
FRASES = corpus.generar()
tono = json.loads((BASE / 'tono.json').read_text())
(BASE / 'frases' / 'textos.json').write_text(json.dumps(FRASES, ensure_ascii=False))
hechas, t0 = 0, time.time()
for i, texto in enumerate(FRASES):
    ruta = BASE / 'frases' / 'wav' / f'f{i:05d}.wav'
    if ruta.exists():
        continue
    wav = modelo.generate(texto, language_id='es', audio_prompt_path=REF, **tono)
    wav = ta.functional.resample(wav, modelo.sr, 22050)
    ta.save(str(ruta), wav, 22050)
    hechas += 1
    if hechas % 25 == 0:
        print(f'{i + 1}/{len(FRASES)} · {(time.time() - t0) / hechas:.1f} s por frase')
print('✅ Frases generadas:', len(list((BASE / 'frases' / 'wav').glob('*.wav'))))
""")

md("""
# Parte B · Entrenar la voz para la Raspberry

> Si vienes de la parte A: *Entorno de ejecución → Desconectar y eliminar el entorno de ejecución*, vuelve a
> poner la GPU T4 y ejecuta la celda **0**.

### B1 · Filtrar con Whisper
Transcribe cada frase y descarta las que no digan exactamente lo esperado (palabras cambiadas, cortes, ruidos).
""")
code("""
!pip -q install faster-whisper==1.1.1
import json, re, unicodedata, difflib
from faster_whisper import WhisperModel
def norm(t):
    t = unicodedata.normalize('NFKD', t.lower()); t = ''.join(c for c in t if not unicodedata.combining(c))
    return ' '.join(re.sub(r'[^a-zñ0-9 ]', ' ', t).split())
FRASES = json.loads((BASE / 'frases' / 'textos.json').read_text())
w = WhisperModel('medium', device='cuda', compute_type='float16')
buenas, malas = [], []
for i, texto in enumerate(FRASES):
    ruta = BASE / 'frases' / 'wav' / f'f{i:05d}.wav'
    if not ruta.exists():
        continue
    segs, _ = w.transcribe(str(ruta), language='es', beam_size=5)
    oido = ' '.join(s.text for s in segs)
    parecido = difflib.SequenceMatcher(None, norm(texto), norm(oido)).ratio()
    (buenas if parecido >= 0.92 else malas).append((ruta.name, texto, oido, parecido))
with open(BASE / 'piper' / 'metadata.csv', 'w') as f:
    for nombre, texto, _, _ in buenas:
        f.write(f'{nombre}|{texto}\\n')
print(f'✅ {len(buenas)} buenas · ❌ {len(malas)} descartadas')
for m in malas[:10]:
    print(f'  {m[3]:.2f}  «{m[1]}»  →  «{m[2]}»')
""")

md("""
### B2 · Instalar Piper (entrenamiento)
""")
code("""
!apt-get -qq install -y espeak-ng build-essential cmake ninja-build > /dev/null
%cd /content
!test -d piper1-gpl || git clone -q https://github.com/OHF-voice/piper1-gpl.git
%cd /content/piper1-gpl
!pip -q install -e '.[train]' && pip -q install scikit-build onnxscript onnx
!./build_monotonic_align.sh > /dev/null 2>&1; python3 setup.py build_ext --inplace > /dev/null 2>&1
!python3 -c "from piper import espeakbridge; print('✅ Piper listo para entrenar')"
""")

md("""
### B3 · Entrenar
Parte de la voz española **davefx** de Piper (calidad *medium*): el timbre cambia por completo con tus frases y aprende
el castellano mucho más rápido que desde cero. Guarda un punto de control en Drive en cada época.

**Si Colab corta la sesión:** ejecuta 0, B2 y esta celda otra vez: **continúa** desde el último punto guardado.
Cuantas más épocas, mejor (a partir de ~400 ya suele sonar bien; 800–1000 es lo ideal). Puedes escuchar cómo va en B4
sin parar el entrenamiento más que el tiempo de la prueba.
""")
code("""
#@title Entrenamiento
EPOCAS_EXTRA = 800 #@param {type:"integer"}
LOTE = 24 #@param {type:"integer"}
import glob, os, pathlib
from huggingface_hub import hf_hub_download
P = BASE / 'piper'
ckpts = sorted(glob.glob(str(P / 'entreno' / '**' / '*.ckpt'), recursive=True), key=os.path.getmtime)
if ckpts:
    ARRANQUE = f'--ckpt_path "{ckpts[-1]}"'; print('▶️ Continúo desde', ckpts[-1])
else:
    davefx = hf_hub_download('rhasspy/piper-checkpoints', 'es/es_ES/davefx/medium/epoch=5629-step=1605020.ckpt', repo_type='dataset')
    # El punto de partida es de una versión antigua de Piper: se copian sus pesos («warmstart»), no se «reanuda»
    ARRANQUE = f'--model.warmstart_ckpt "{davefx}"'; print('🆕 Empiezo desde la voz española davefx')
MAX_EPOCAS = EPOCAS_EXTRA
!python3 -m piper.train fit \\
  --data.voice_name "aria" \\
  --data.csv_path "{P}/metadata.csv" \\
  --data.audio_dir "{BASE}/frases/wav" \\
  --model.sample_rate 22050 \\
  --data.espeak_voice "es" \\
  --data.cache_dir "/content/cache" \\
  --data.config_path "{P}/es_ES-aria-medium.onnx.json" \\
  --data.batch_size {LOTE} \\
  --trainer.max_epochs {MAX_EPOCAS} \\
  --trainer.default_root_dir "{P}/entreno" \\
  {ARRANQUE}
""")

md("""
### B4 · Exportar y escuchar
Convierte el último punto de control en `es_ES-aria-medium.onnx` (lo que usa la Raspberry) y lo prueba.
""")
code("""
import glob, os, pathlib
from IPython.display import Audio, display
P = BASE / 'piper'
ultimo = sorted(glob.glob(str(P / 'entreno' / '**' / '*.ckpt'), recursive=True), key=os.path.getmtime)[-1]
print('Exporto', ultimo)
# El exportador nuevo de PyTorch falla con Piper: se usa el clásico (dynamo=False)
exportar = '''
import functools, runpy, sys, torch
torch.onnx.export = functools.partial(torch.onnx.export, dynamo=False)
sys.argv = ["export_onnx", "--checkpoint", sys.argv[1], "--output-file", sys.argv[2]]
runpy.run_module("piper.train.export_onnx", run_name="__main__")
'''
pathlib.Path('/content/exportar.py').write_text(exportar)
!python3 /content/exportar.py "{ultimo}" "{P}/es_ES-aria-medium.onnx"
for i, t in enumerate(['Hola, soy ARIA. Estoy aquí para ayudarte en lo que necesites.',
                       'Hoy en Madrid hace un día precioso, con veintidós grados.',
                       'Buenas noches, cariño. Que descanses.']):
    !echo "{t}" | python3 -m piper -m "{P}/es_ES-aria-medium.onnx" -f "/content/prueba{i}.wav"
    display(Audio(f'/content/prueba{i}.wav'))
print('✅ Archivos para la Raspberry en Drive → ARIA-voz/piper/: es_ES-aria-medium.onnx y es_ES-aria-medium.onnx.json')
""")

md("""
## Instalar en ARIA
Copia `es_ES-aria-medium.onnx` y `es_ES-aria-medium.onnx.json` a la Raspberry, en `~/homelab/ARIA/data/voz-propia/`.
ARIA la detecta sola: aparecerá en **Ajustes → Voz** como «Voz propia de ARIA» con su botón ▶ para probarla.

**Privacidad:** las grabaciones, las frases y la voz son personales. No las publiques. Si la persona retira su permiso,
borra `ARIA-voz/` de Drive y `data/voz-propia/` de la Raspberry.
""")

nb = {"cells": CELDAS, "metadata": {"accelerator": "GPU", "colab": {"provenance": [], "gpuType": "T4"},
                                    "kernelspec": {"name": "python3", "display_name": "Python 3"},
                                    "language_info": {"name": "python"}},
      "nbformat": 4, "nbformat_minor": 0}
salida = Path(__file__).with_name("ARIA_voz_propia.ipynb")
salida.write_text(json.dumps(nb, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print("Escrito", salida, "con", len(CELDAS), "celdas")
