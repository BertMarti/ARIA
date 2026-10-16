"""Integración web para las aplicaciones Android de ARIA."""
import json
from pathlib import Path

from fastapi.testclient import TestClient

from aria import config, main


CLIENTE = TestClient(main.app, base_url="https://192.168.1.50")
STATIC = Path(__file__).resolve().parent.parent / "static"


def test_assetlinks_sin_huella_es_vacio_y_publico(monkeypatch):
    monkeypatch.setattr(config, "APP_SHA256", "")
    respuesta = CLIENTE.get("/.well-known/assetlinks.json")
    assert respuesta.status_code == 200
    assert respuesta.json() == []
    assert respuesta.headers["content-type"].startswith("application/json")


def test_assetlinks_contiene_las_dos_apps_y_normaliza_la_huella(monkeypatch):
    huella = "aa:bb:cc:dd:ee:ff:00:11:22:33:44:55:66:77:88:99:"
    huella += "aa:bb:cc:dd:ee:ff:00:11:22:33:44:55:66:77:88:99"
    monkeypatch.setattr(config, "APP_SHA256", huella)
    datos = CLIENTE.get("/.well-known/assetlinks.json").json()
    paquetes = [d["target"]["package_name"] for d in datos]
    assert paquetes == ["io.github.bertmarti.aria", "io.github.bertmarti.aria.lite"]
    assert datos[0]["target"]["sha256_cert_fingerprints"] == [huella.upper()]


def test_manifest_tiene_los_cuatro_atajos():
    manifest = json.loads((STATIC / "manifest.webmanifest").read_text(encoding="utf-8"))
    urls = {atajo["url"] for atajo in manifest["shortcuts"]}
    assert urls == {"/#hablar", "/#nota", "/#hud", "/#compartir"}


def test_index_carga_la_tarjeta_de_android():
    index = (STATIC / "index.html").read_text(encoding="utf-8")
    assert 'id="ajustes-android"' in index
    assert "Descargar ARIA Lite" in index
