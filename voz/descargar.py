"""Descarga los modelos al construir la imagen (el contenedor no tiene salida a Internet)."""
import os
import pathlib
import shutil
import sys
import urllib.request
import zipfile

from faster_whisper.utils import download_model

MODELOS = pathlib.Path(os.environ.get("VOZ_MODELOS", "/modelos"))
WHISPER = os.environ["VOZ_WHISPER"]   # base | small
VOZ = os.environ["VOZ_PIPER"]         # p. ej. es_ES-davefx-medium
VOSK = os.environ["VOZ_VOSK"]         # p. ej. vosk-model-small-es-0.42

PIPER = "https://huggingface.co/rhasspy/piper-voices/resolve/main/"


def bajar(url: str, destino: pathlib.Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    print("descargando", url, file=sys.stderr)
    urllib.request.urlretrieve(url, destino)


idioma, nombre, calidad = VOZ.split("-")
for ext in (".onnx", ".onnx.json"):
    bajar(f"{PIPER}{idioma.split('_')[0]}/{idioma}/{nombre}/{calidad}/{VOZ}{ext}", MODELOS / "piper" / f"{VOZ}{ext}")

zip_vosk = MODELOS / "vosk.zip"
bajar(f"https://alphacephei.com/vosk/models/{VOSK}.zip", zip_vosk)
with zipfile.ZipFile(zip_vosk) as z:
    z.extractall(MODELOS / "vosk")
zip_vosk.unlink()

destino = MODELOS / "whisper" / WHISPER
download_model(WHISPER, output_dir=str(destino))
shutil.rmtree(destino / ".cache", ignore_errors=True)
