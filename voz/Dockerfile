FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HF_HUB_OFFLINE=1 VOZ_MODELOS=/modelos

# libatomic1: la necesita libvosk.so en arm64.
RUN apt-get update && apt-get install -y --no-install-recommends libatomic1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 1000 --no-create-home --shell /usr/sbin/nologin voz

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Modelos dentro de la imagen: Whisper base (fallback local), voz de Piper y Vosk pequeño en español.
ARG VOZ_WHISPER=base
ARG VOZ_PIPER=es_ES-davefx-medium
ARG VOZ_VOSK=vosk-model-small-es-0.42
ENV VOZ_WHISPER=${VOZ_WHISPER} VOZ_PIPER=${VOZ_PIPER}
COPY descargar.py .
RUN HF_HUB_OFFLINE=0 VOZ_VOSK=${VOZ_VOSK} python descargar.py && rm descargar.py

COPY servidor.py .
USER voz
EXPOSE 8001
CMD ["uvicorn", "servidor:app", "--host", "0.0.0.0", "--port", "8001", "--no-server-header", "--ws-max-size", "65536"]
