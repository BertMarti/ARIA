FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install --no-install-recommends -y ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 1000 --no-create-home --shell /usr/sbin/nologin aria \
    && mkdir /cache /tmp \
    && chown aria:aria /cache /tmp

WORKDIR /srv
RUN pip install --no-cache-dir pytapo==3.4.27 aiofiles==24.1.0 starlette==0.46.2 uvicorn==0.34.0
COPY grabaciones/servicio.py .

USER aria
EXPOSE 8090
CMD ["uvicorn", "servicio:app", "--host", "0.0.0.0", "--port", "8090", "--no-server-header"]
