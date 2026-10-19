import asyncio
from datetime import date

import httpx
import pytest

from aria import luz, tools


def correr(c):
    return asyncio.run(c)


def respuesta(precios_mwh):
    valores = [{"value": v, "datetime": f"2026-10-09T{h:02d}:00:00.000+02:00"} for h, v in enumerate(precios_mwh)]
    return {"included": [{"type": "Precio mercado spot", "attributes": {"values": []}},
                         {"type": "PVPC", "attributes": {"title": "PVPC", "values": valores}}]}


@pytest.fixture
def ree(monkeypatch):
    estado = {"peticiones": 0, "datos": respuesta([100 + h * 5 for h in range(24)]), "caido": False}
    def manejar(req):
        estado["peticiones"] += 1
        assert req.url.host == "apidatos.ree.es" and req.url.params["time_trunc"] == "hour"
        return httpx.Response(503) if estado["caido"] else httpx.Response(200, json=estado["datos"])
    real = httpx.AsyncClient
    monkeypatch.setattr(luz.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(manejar), **kw))
    luz._cache.clear()
    return estado


def test_precios_en_euros_por_kwh_y_cache(ree):
    p = correr(luz.precios(date(2026, 10, 9)))
    assert len(p) == 24 and p[0] == {"hora": 0, "precio": 0.1} and p[23]["precio"] == 0.215
    correr(luz.precios(date(2026, 10, 9)))
    assert ree["peticiones"] == 1


def test_resumen_de_horas():
    serie = [{"hora": h, "precio": p} for h, p in enumerate([0.2] * 8 + [0.1, 0.05, 0.3] + [0.2] * 13)]
    r = luz.resumen(serie, hora_actual=9)
    assert r["barata"] == {"hora": 9, "precio": 0.05} and r["cara"]["hora"] == 10
    assert r["nivel"] == "barata" and [x["hora"] for x in r["mejores_restantes"]][0] == 9
    t = luz.texto(r)
    assert "a las 9:00 (0,050 €/kWh)" in t and "Ahora mismo" in t


def test_api_caida_da_error_legible(ree):
    ree["caido"] = True
    with pytest.raises(luz.LuzError):
        correr(luz.precios(date(2026, 10, 9)))
    assert "no está disponible" in correr(tools.precio_luz())


def test_sin_pvpc_publicado(ree):
    ree["datos"] = {"included": []}
    with pytest.raises(luz.LuzError, match="publicado"):
        correr(luz.precios(date(2026, 10, 10)))


def _serie_dia():
    # Barata de 13 a 16 (0,05), cara de 19 a 22 (0,25), el resto 0,12.
    return [{"hora": h, "precio": 0.05 if 13 <= h < 16 else 0.25 if 19 <= h < 22 else 0.12} for h in range(24)]


def test_franja_barata_y_cara():
    assert luz.franja(_serie_dia()) == {"desde": 13, "hasta": 16, "media": 0.05}
    assert luz.franja(_serie_dia(), cara=True) == {"desde": 19, "hasta": 22, "media": 0.25}
    t = luz.texto_manana(_serie_dia())
    assert "de 13:00 a 16:00" in t and "Evita de 19:00 a 22:00" in t and "0,050 €/kWh" in t


def test_aviso_de_la_luz_una_vez_por_dia_y_solo_por_la_tarde(monkeypatch):
    from datetime import datetime
    from aria import avisos, tiempo
    avisos.iniciar()
    enviados = []

    async def emitir(tipo, severidad, texto, enlace="", destinatarios=None, **kw):
        enviados.append((tipo, texto, destinatarios))
        return []

    async def precios(dia=None):
        return _serie_dia()
    monkeypatch.setattr(avisos, "emitir", emitir)
    monkeypatch.setattr(luz, "precios", precios)
    monkeypatch.setattr(luz, "activo", lambda: True)
    monkeypatch.setattr(avisos, "_luz_reintento", 0.0)
    avisos.guardar_ajustes(1, {"tipos": {"luz": True}})
    tarde = datetime(2026, 10, 17, 18, 0, tzinfo=tiempo.zona())
    assert asyncio.run(avisos.luz_de_manana(tarde)) is False          # antes de las 20:45: aún no
    noche = datetime(2026, 10, 17, 21, 0, tzinfo=tiempo.zona())
    assert asyncio.run(avisos.luz_de_manana(noche)) is True
    assert asyncio.run(avisos.luz_de_manana(noche)) is False          # una sola vez por día
    assert len(enviados) == 1 and enviados[0][0] == "luz" and "13:00 a 16:00" in enviados[0][1]
    assert enviados[0][2]                                              # a todos los usuarios activos


def test_aviso_de_la_luz_espera_si_aun_no_hay_precios(monkeypatch):
    from datetime import datetime
    from aria import avisos, tiempo
    avisos.iniciar()
    llamadas = []

    async def precios(dia=None):
        llamadas.append(dia)
        raise luz.LuzError("Red Eléctrica aún no ha publicado el precio de ese día.")
    monkeypatch.setattr(luz, "precios", precios)
    monkeypatch.setattr(luz, "activo", lambda: True)
    monkeypatch.setattr(avisos, "_luz_reintento", 0.0)
    noche = datetime(2026, 10, 17, 21, 0, tzinfo=tiempo.zona())
    assert asyncio.run(avisos.luz_de_manana(noche)) is False
    assert asyncio.run(avisos.luz_de_manana(noche)) is False          # no vuelve a preguntar hasta 15 min después
    assert len(llamadas) == 1
