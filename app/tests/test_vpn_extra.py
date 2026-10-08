from datetime import datetime, timezone

import asyncio
import httpx

from aria import avisos, vpn, vpn_ubicaciones


def test_caducidades_en_utc():
    ahora = datetime(2026, 12, 1, 12, tzinfo=timezone.utc)
    assert vpn.caducidad("24h", ahora) == "2026-12-02T12:00:00Z"
    assert vpn.caducidad("7d", ahora) == "2026-12-08T12:00:00Z"
    assert vpn.caducidad("2026-12-31", ahora) == "2026-12-31T00:00:00Z"


def test_endpoint_ipv4_ipv6_y_privadas():
    assert vpn_ubicaciones.extraer_ip("1.2.3.4:51820") == "1.2.3.4"
    assert vpn_ubicaciones.extraer_ip("[2001:4860:4860::8888]:51820") == "2001:4860:4860::8888"
    assert vpn_ubicaciones.extraer_ip("10.8.0.2:51820") is None


def test_geo_cache_y_aviso_solo_al_cambiar(monkeypatch):
    vpn_ubicaciones.iniciar()
    monkeypatch.setattr(vpn, "configurado", lambda: True)
    cliente = {"id": 4, "nombre": "movil-prueba", "conectado": True, "endpoint": "1.2.3.4:51820"}
    monkeypatch.setattr(vpn, "listar", lambda: asyncio.sleep(0, result=[cliente]))
    llamadas = []

    def atender(request):
        llamadas.append(request.url)
        return httpx.Response(200, json={"success": True, "country": "Pais", "city": "Ciudad",
                                         "connection": {"isp": "Operador"}})

    monkeypatch.setattr(vpn_ubicaciones, "_transporte", httpx.MockTransport(atender))
    assert asyncio.run(vpn_ubicaciones.comprobar()) == []
    assert asyncio.run(vpn_ubicaciones.comprobar()) == []
    assert len(llamadas) == 1
    cliente["endpoint"] = "5.6.7.8:51820"
    assert asyncio.run(vpn_ubicaciones.comprobar()) == []  # misma ubicación, solo aprende la IP
    assert len(llamadas) == 2


def test_usuario_no_puede_herramienta_de_ubicaciones():
    from aria import tools
    assert "ubicaciones_vpn" not in tools.permitidas("usuario")
    assert "ubicaciones_vpn" in tools.permitidas("admin")
