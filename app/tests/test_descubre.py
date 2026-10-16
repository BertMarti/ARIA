"""Pruebas del descubrimiento local, sin tráfico de red."""
import ipaddress
import json
from types import SimpleNamespace

from descubre import descubre


def test_txt_y_capacidades(monkeypatch):
    monkeypatch.setattr(descubre, "RED", ipaddress.ip_network("192.168.1.0/24"))
    datos = SimpleNamespace(addresses=[b"\xc0\xa8\x01\x14"], port=8009, properties={b"fn": "Salón".encode(), b"md": b"Chromecast", b"id": b"abc", b"ca": b"1"})
    resultado = descubre._cast("cast._googlecast._tcp.local.", datos)
    assert resultado["nombre"] == "Salón"
    assert resultado["video"]


def test_cast_fuera_de_red(monkeypatch):
    monkeypatch.setattr(descubre, "RED", ipaddress.ip_network("192.168.1.0/24"))
    datos = SimpleNamespace(addresses=[b"\xc0\xa8\x02\x14"], port=8009, properties={b"ca": b"1"})
    assert descubre._cast("cast", datos) is None


def test_xml_rechaza_doctype(monkeypatch):
    class Respuesta:
        def __enter__(self): return self
        def __exit__(self, *_args): pass
        def read(self, _limite): return b"<!DOCTYPE root><root />"

    class Abridor:
        def open(self, *_args, **_kwargs): return Respuesta()

    monkeypatch.setattr(descubre.urllib.request, "build_opener", lambda *_args: Abridor())
    assert descubre._xml("http://192.168.1.20/device.xml", "192.168.1.20") is None


def test_control_de_otro_host_descartado():
    respuesta = b"HTTP/1.1 200 OK\r\nLOCATION: http://192.168.1.21/device.xml\r\n\r\n"
    assert descubre._dlna(respuesta, "192.168.1.20") is None


def test_escritura_atomica(monkeypatch, tmp_path):
    destino = tmp_path / "dispositivos.json"
    monkeypatch.setattr(descubre, "SALIDA", destino)
    descubre.VISTO.clear()
    descubre.VISTO["cast:abc"] = {"id": "cast:abc", "nombre": "Salón", "modelo": "TV", "tipo": "chromecast",
                                  "ip": "192.168.1.20", "puerto": 8009, "video": True, "grupo": False, "control": None,
                                  "_visto": descubre.time.time()}
    descubre.escribir()
    assert json.loads(destino.read_text())["dispositivos"][0]["id"] == "cast:abc"
