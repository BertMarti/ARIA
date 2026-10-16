# aria-descubre: oye los anuncios mDNS (Google Cast) y SSDP (DLNA) de la red de casa, como Chrome, y deja la lista en
# /descubre/dispositivos.json para la app. Sin puertos publicados, sin capacidades, usuario nobody y sistema de archivos
# de solo lectura (ver docker-compose.yml).
FROM python:3.12-alpine

RUN pip install --no-cache-dir "zeroconf>=0.132,<1" \
    && mkdir -p /opt/descubre /descubre \
    && chown 65534:1000 /descubre && chmod 2750 /descubre

COPY descubre/descubre.py /opt/descubre/

WORKDIR /opt/descubre
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 65534:1000
CMD ["python3", "/opt/descubre/descubre.py"]
