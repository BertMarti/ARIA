"""Pruebas unitarias del puente de medios, sin descubrir ni conectar equipos reales."""
import asyncio
import json
import time

import pytest

from aria import api_tele, config, tele


def test_rangos():
    assert api_tele._rango("bytes=2-4", 10) == (2, 4)
    assert api_tele._rango("bytes=2-", 10) == (2, 9)
    assert api_tele._rango("bytes=-3", 10) == (7, 9)
    with pytest.raises(tele.TeleError):
        api_tele._rango("bytes=10-11", 10)


def test_red_y_token_caducado(monkeypatch):
    monkeypatch.setattr(config, "RED_PERMITIDA", "192.168.1.0/24")
    monkeypatch.setattr(config, "LAN_IP", "192.168.1.2")
    assert tele.en_red("192.168.1.20")
    assert not tele.en_red("192.168.2.20")
    s = tele.Sesion(None, 1)
    d = tele.Token("abc", "a" * 64, 1, 4, "video/mp4", "a.mp4", s, time.time() - tele.CADUCIDAD - 1)
    tele._tokens["abc"] = d
    assert tele.validar_token("abc") is None


def test_soap_escapa_xml():
    texto = tele.soap("x", "Play", "<Title>&</Title>")
    assert "<Title>&</Title>" in texto
    assert "Envelope" in texto


def test_xml_rechaza_doctype(monkeypatch):
    class Respuesta:
        content = b'<!DOCTYPE root><root />'

    class Cliente:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def get(self, url): return Respuesta()

    monkeypatch.setattr(tele.httpx, "AsyncClient", lambda **kwargs: Cliente())
    with pytest.raises(tele.TeleError):
        asyncio.run(tele._xml("http://192.168.1.20/device.xml"))


def test_descubrir_prefiere_json_fresco(monkeypatch, tmp_path):
    monkeypatch.setattr(tele, "_cache_dispositivos", (0, []))
    archivo = tmp_path / "dispositivos.json"
    archivo.write_text(json.dumps({"ts": time.time(), "dispositivos": [{"id": "cast:abc", "ip": "192.168.1.20"}]}))
    monkeypatch.setattr(config, "DESCUBRE_DIR", tmp_path)
    monkeypatch.setattr(tele.red, "dispositivos", lambda: pytest.fail("no debe usar el respaldo"))
    assert asyncio.run(tele.descubrir())[0]["id"] == "cast:abc"


def test_descubrir_usa_respaldo_si_json_viejo(monkeypatch, tmp_path):
    monkeypatch.setattr(tele, "_cache_dispositivos", (0, []))
    archivo = tmp_path / "dispositivos.json"
    archivo.write_text(json.dumps({"ts": 0, "dispositivos": []}))
    monkeypatch.setattr(config, "DESCUBRE_DIR", tmp_path)
    monkeypatch.setattr(tele, "_chromecast", lambda _ip: asyncio.sleep(0, result=None))
    monkeypatch.setattr(tele, "_dlna", lambda _ip: asyncio.sleep(0, result=None))
    monkeypatch.setattr(tele.red, "dispositivos", lambda: [{"ip": "192.168.1.20"}])
    assert asyncio.run(tele.descubrir()) == []
