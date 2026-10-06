FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

RUN useradd --uid 1000 --no-create-home --shell /usr/sbin/nologin aria \
    && mkdir /data && chown aria /data

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY aria ./aria
COPY static ./static

USER aria
EXPOSE 8000
CMD ["uvicorn", "aria.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*", "--no-server-header"]
