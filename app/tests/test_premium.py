"""Pruebas de licencias, prueba local y bloqueo Premium."""
import base64
import json
from datetime import date, timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from fastapi.testclient import TestClient

from aria import auth, automatizaciones, config, main, premium, usuarios


def licencia(monkeypatch, **cambios):
    clave = Ed25519PrivateKey.generate()
    publica = clave.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    monkeypatch.setattr(premium, "CLAVE_PUBLICA_B64", base64.b64encode(publica).decode())
    datos = {"v": 1, "id": "licencia-ejemplo", "plan": "premium", "emitida": date.today().isoformat(),
             "caduca": (date.today() + timedelta(days=30)).isoformat(), "instalacion": None}
    datos.update(cambios)
    crudo = json.dumps(datos, separators=(",", ":")).encode()
    codifica = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()
    return codifica(crudo) + "." + codifica(clave.sign(crudo))


def test_firma_valida_invalida_y_manipulada(monkeypatch):
    premium.iniciar()
    texto = licencia(monkeypatch)
    assert premium.instalar_licencia(texto)["estado"] == "premium"
    datos, firma = texto.split(".")
    crudo = bytearray(base64.urlsafe_b64decode(firma + "=" * (-len(firma) % 4)))
    crudo[10] ^= 0xFF   # firma alterada de verdad (cambiar el último carácter puede no tocar ningún bit útil)
    manipulada = datos + "." + base64.urlsafe_b64encode(bytes(crudo)).rstrip(b"=").decode()
    with pytest.raises(premium.PremiumError):
        premium.instalar_licencia(manipulada)
    otro = json.loads(base64.urlsafe_b64decode(datos + "=" * (-len(datos) % 4)))
    otro["caduca"] = "2099-12-31"   # alargar la fecha sin volver a firmar
    falsa = base64.urlsafe_b64encode(json.dumps(otro).encode()).rstrip(b"=").decode() + "." + firma
    with pytest.raises(premium.PremiumError):
        premium.instalar_licencia(falsa)
    with pytest.raises(premium.PremiumError):
        premium.instalar_licencia(texto + "x")


def test_caducada_y_gracia(monkeypatch):
    premium.iniciar()
    monkeypatch.setattr(premium, "_hoy", lambda: date(2026, 1, 30))
    premium.instalar_licencia(licencia(monkeypatch, caduca="2026-01-20"))
    assert premium.estado()["estado"] == "gracia"
    premium.instalar_licencia(licencia(monkeypatch, caduca="2025-12-01"))
    assert premium.estado()["estado"] == "caducada"


def test_prueba_solo_una_vez(monkeypatch):
    premium.iniciar()
    assert premium.empezar_prueba()["estado"] == "prueba"
    with pytest.raises(premium.PremiumError):
        premium.empezar_prueba()


def test_exigencia_desactivada_desbloquea_todo(monkeypatch):
    premium.iniciar()
    monkeypatch.setattr(config, "PREMIUM_EXIGIR", False)
    assert all(premium.tiene(x) for x in premium.FUNCIONES)
    assert premium.limite("documentos") is None


def test_exigencia_activa_bloquea(monkeypatch):
    premium.iniciar()
    monkeypatch.setattr(config, "PREMIUM_EXIGIR", True)
    assert not premium.tiene("hud")
    assert premium.limite("automatizaciones") == 3


LAN = "https://192.168.1.50"


def cliente(u):
    c = TestClient(main.app, base_url=LAN, follow_redirects=False)
    c.cookies.set(auth.COOKIE, auth.crear_sesion(u))
    return c


def test_rutas_premium_devuelven_402_y_lo_gratis_sigue(monkeypatch):
    premium.iniciar()
    monkeypatch.setattr(config, "PREMIUM_EXIGIR", True)
    c = cliente(usuarios.por_identificador("admin"))
    r = c.get("/api/cerebro")
    assert r.status_code == 402 and r.json()["premium"] == "cerebro"
    assert c.post("/api/tele/enviar", json={}).status_code == 402
    assert c.post("/api/finanzas/reglas", json={}).status_code == 402
    assert c.post("/api/seguridad/hallazgos/x/accion", json={}).status_code == 402
    assert c.get("/api/finanzas/movimientos").status_code == 200   # lo básico de finanzas sigue gratis
    assert c.get("/api/premium").json()["funciones"]["cerebro"] is False
    premium.empezar_prueba()
    assert c.get("/api/cerebro").status_code == 200


def test_gratis_permite_tres_automatizaciones_y_no_mas(monkeypatch):
    premium.iniciar(); automatizaciones.iniciar()
    monkeypatch.setattr(config, "PREMIUM_EXIGIR", True)
    c = cliente(usuarios.por_identificador("admin"))
    regla = {"nombre": "Avisar", "disparador": {"tipo": "aviso", "aviso": "servicios"}, "condiciones": {},
             "acciones": [{"tipo": "avisar", "texto": "Ha ocurrido algo."}]}
    for _ in range(3):
        assert c.post("/api/automatizaciones", json=regla).status_code == 200
    r = c.post("/api/automatizaciones", json=regla)
    assert r.status_code == 400 and "ARIA Gratis" in r.json()["error"]


def test_gratis_vincula_un_movil(monkeypatch):
    premium.iniciar()
    monkeypatch.setattr(config, "PREMIUM_EXIGIR", True)
    c = cliente(usuarios.por_identificador("admin"))
    assert c.post("/api/app/dispositivos", json={"nombre": "Móvil"}).status_code == 200
    r = c.post("/api/app/dispositivos", json={"nombre": "Tableta"})
    assert r.status_code == 402 and r.json()["premium"] == "app_extra"


def test_gratis_limita_usuarios(monkeypatch):
    premium.iniciar()
    monkeypatch.setattr(config, "PREMIUM_EXIGIR", True)
    usuarios.crear("ana@example.com", "Ana", "usuario", "clave-larga-ana")
    with pytest.raises(usuarios.UsuarioError):
        usuarios.crear("luis@example.com", "Luis", "usuario", "clave-larga-luis")


def test_un_usuario_no_activa_licencias():
    premium.iniciar()
    ana = usuarios.crear("ana@example.com", "Ana", "usuario", "clave-larga-ana")
    c = cliente(ana)
    assert c.get("/api/premium").status_code == 200
    assert c.post("/api/premium/licencia", json={"licencia": "x"}).status_code == 403
    assert c.post("/api/premium/prueba", json={}).status_code == 403
    assert c.delete("/api/premium/licencia").status_code == 403
