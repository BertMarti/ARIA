"""Hogar: historial de quién llega y se va, apagar luces al irse todos, avisos de salud de las cámaras y la
herramienta «quien_en_casa». Sin red: dobles del router, de las cámaras y de Govee."""
import asyncio
import json
import time

import pytest

from aria import config, hogar_govee, hogar_router, tools, usuarios
from test_hogar import MOVILES, PASS_FALSA, _vigilancia, cliente, limpio  # noqa: F401 - la fixture se reutiliza


def test_historial_apunta_salidas_con_la_ultima_vez_vista_y_llegadas(monkeypatch):
    hv, estado, cambios, emitidos = _vigilancia(monkeypatch, MOVILES)
    t = time.time()
    asyncio.run(hv.ciclo(t))                                             # todos en casa: aún no hay nada que apuntar
    assert hv.historial() == []
    estado["conectados"] = MOVILES[1:]                                   # el Pixel se va
    asyncio.run(hv.ciclo(t + 120))
    assert hv.historial() == []                                          # aún no lleva 10 min fuera
    asyncio.run(hv.ciclo(t + 11 * 60))
    h = hv.historial()
    assert [(x["nombre"], x["evento"]) for x in h] == [("Pixel", "sale")] and h[0]["ts"] == pytest.approx(t)
    asyncio.run(hv.ciclo(t + 20 * 60))
    assert len(hv.historial()) == 1                                      # no se repite
    estado["conectados"] = MOVILES
    asyncio.run(hv.ciclo(t + 30 * 60))
    h = hv.historial()
    assert (h[0]["nombre"], h[0]["evento"], h[0]["ts"]) == ("Pixel", "llega", t + 30 * 60)


def test_historial_sin_router_no_apunta_salidas(monkeypatch):
    hv, estado, cambios, emitidos = _vigilancia(monkeypatch, MOVILES)
    t = time.time()
    asyncio.run(hv.ciclo(t))
    estado["falla"] = True
    asyncio.run(hv.ciclo(t + 60 * 60))
    assert hv.historial() == []


def test_historial_endpoint_solo_admin(monkeypatch):
    hv, estado, cambios, emitidos = _vigilancia(monkeypatch, MOVILES)
    hv._anotar([(1000.0, "Pixel", "sale"), (2000.0, "Pixel", "llega")])
    monkeypatch.setattr(config, "ROUTER_PASSWORD", PASS_FALSA)
    admin = usuarios.por_identificador("admin")
    d = cliente(admin).get("/api/hogar/vigilancia/historial").json()
    assert [x["evento"] for x in d["historial"]] == ["llega", "sale"]
    ana = usuarios.crear("ana@example.com", "Ana", "usuario", "clave-larga-ana")
    assert cliente(ana).get("/api/hogar/vigilancia/historial").status_code == 403


def test_historial_se_recorta(monkeypatch):
    hv, *_ = _vigilancia(monkeypatch, MOVILES)
    monkeypatch.setattr(hv, "HISTORIAL_MAX", 5)
    hv._anotar([(float(i), "Pixel", "llega") for i in range(12)])
    h = hv.historial(50)
    assert len(h) == 5 and h[0]["ts"] == 11.0


def _luces(monkeypatch, filas, falla=()):
    apagadas = []

    async def luces():
        return filas

    async def cambiar(identificador, encendida=None, brillo=None, color=None):
        if identificador in falla:
            raise hogar_govee.GoveeError("no responde")
        apagadas.append((identificador, encendida))
        return {"ok": True}
    monkeypatch.setattr(hogar_govee, "configurado", lambda: True)
    monkeypatch.setattr(hogar_govee, "luces", luces)
    monkeypatch.setattr(hogar_govee, "cambiar", cambiar)
    return apagadas


def test_al_irse_todos_apaga_las_luces_encendidas_si_se_ha_pedido(monkeypatch):
    hv, estado, cambios, emitidos = _vigilancia(monkeypatch, MOVILES)
    apagadas = _luces(monkeypatch, [{"id": "a", "nombre": "Despacho", "encendida": True},
                                    {"id": "b", "nombre": "Salón", "encendida": False},
                                    {"id": "c", "nombre": "Cocina", "encendida": True}], falla={"c"})
    hv.configurar({"apagar_luces": True}, MOVILES)
    assert hv.resumen(MOVILES)["apagar_luces"] is True
    t = time.time()
    asyncio.run(hv.ciclo(t))
    estado["conectados"] = []
    assert asyncio.run(hv.ciclo(t + 15 * 60)) == "fuera"
    assert apagadas == [("a", False)]                                    # solo las encendidas; la que falla no tumba nada
    assert "apagado 1 luz." in emitidos[-1][1]


def test_sin_la_opcion_no_toca_las_luces(monkeypatch):
    hv, estado, cambios, emitidos = _vigilancia(monkeypatch, MOVILES)
    apagadas = _luces(monkeypatch, [{"id": "a", "nombre": "Despacho", "encendida": True}])
    t = time.time()
    asyncio.run(hv.ciclo(t))
    estado["conectados"] = []
    assert asyncio.run(hv.ciclo(t + 15 * 60)) == "fuera"
    assert apagadas == [] and "luz" not in emitidos[-1][1]
    with pytest.raises(ValueError):
        hv.configurar({"apagar_luces": "si"}, MOVILES)


# --- Salud de las cámaras -------------------------------------------------------------------------------------------
@pytest.fixture
def salud(monkeypatch):
    from aria import hogar_salud as hs
    monkeypatch.setattr(hs, "_nombres", {})
    monkeypatch.setattr(hs, "_sin_respuesta", {})
    monkeypatch.setattr(hs, "_avisado", set())
    emitidos = []

    async def emitir(tipo, severidad, texto, enlace="", destinatarios=None, **kw):
        emitidos.append((tipo, texto))
        return []
    monkeypatch.setattr(hs.avisos, "emitir", emitir)
    return hs, emitidos


def test_bateria_baja_avisa_una_vez_y_se_rearma_al_cargar(salud):
    hs, emitidos = salud
    fila = {"ip": "192.168.1.30", "nombre": "Patio", "en_linea": True, "bateria": 18}
    asyncio.run(hs.revisar([fila]))
    asyncio.run(hs.revisar([dict(fila, bateria=15)]))
    assert len(emitidos) == 1 and emitidos[0][0] == "camaras" and "Patio" in emitidos[0][1] and "18 %" in emitidos[0][1]
    asyncio.run(hs.revisar([dict(fila, bateria=25)]))                    # entre 20 y 30: sigue sin repetir
    asyncio.run(hs.revisar([dict(fila, bateria=90)]))
    asyncio.run(hs.revisar([dict(fila, bateria=19)]))
    assert len(emitidos) == 2


def test_camara_sin_responder_media_hora_avisa_con_su_nombre_y_al_volver(salud):
    hs, emitidos = salud
    asyncio.run(hs.revisar([{"ip": "192.168.1.31", "nombre": "Pasillo", "en_linea": True}]))
    caida = {"ip": "192.168.1.31", "nombre": "192.168.1.31", "en_linea": False}
    asyncio.run(hs.revisar([caida]))
    asyncio.run(hs.revisar([caida]))
    assert emitidos == []
    asyncio.run(hs.revisar([caida]))
    asyncio.run(hs.revisar([caida]))
    assert len(emitidos) == 1 and "«Pasillo»" in emitidos[0][1] and "192.168" not in emitidos[0][1]
    asyncio.run(hs.revisar([{"ip": "192.168.1.31", "nombre": "Pasillo", "en_linea": True}]))
    assert "vuelve a responder" in emitidos[-1][1] and len(emitidos) == 2


def test_camara_sin_bateria_no_avisa(salud):
    hs, emitidos = salud
    asyncio.run(hs.revisar([{"ip": "192.168.1.32", "nombre": "Pasillo", "en_linea": True}]))
    assert emitidos == []


# --- Chat: ¿quién hay en casa? --------------------------------------------------------------------------------------
def test_quien_en_casa(monkeypatch):
    hv, estado, cambios, emitidos = _vigilancia(monkeypatch, MOVILES)
    monkeypatch.setattr(config, "ROUTER_PASSWORD", PASS_FALSA)
    t = time.time()
    asyncio.run(hv.ciclo(t - 3600))
    hv._anotar([(t - 600, "Galaxy", "sale")])
    estado["conectados"] = MOVILES[:2]
    texto = asyncio.run(tools.quien_en_casa())
    assert "Pixel: en casa" in texto and "Galaxy: fuera hace" in texto and "Galaxy se fue" in texto
    assert "AA:BB" not in texto and "192.168" not in texto
    assert "quien_en_casa" not in tools.permitidas("usuario") and "quien_en_casa" in tools.permitidas("admin")


def test_quien_en_casa_sin_moviles(monkeypatch):
    from aria import hogar_vigilancia as hv
    hv.iniciar()
    monkeypatch.setattr(config, "ROUTER_PASSWORD", PASS_FALSA)

    async def conectados():
        return []
    monkeypatch.setattr(hogar_router, "conectados", conectados)
    assert "Aún no hay móviles" in asyncio.run(tools.quien_en_casa())
