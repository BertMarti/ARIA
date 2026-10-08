# aria-escaner: nmap en un contenedor mínimo y aislado. Sin puertos publicados ni socket de Docker.
# Se construye con el contexto ./app para compartir aria/escaneo_comun.py (guardia de red y parser).
FROM alpine:3.22

RUN apk add --no-cache nmap nmap-scripts python3 tzdata \
    && mkdir -p /opt/escaner /escaner \
    && chown 1000:1000 /escaner && chmod 2770 /escaner

COPY aria/escaneo_comun.py escaner/escaner.py /opt/escaner/

WORKDIR /opt/escaner
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
CMD ["python3", "/opt/escaner/escaner.py"]
