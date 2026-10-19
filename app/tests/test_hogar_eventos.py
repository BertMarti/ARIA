"""Eventos: detecciones de las cámaras con la casa vacía. Sin red: el servicio de grabaciones y las fotos son dobles."""
import asyncio
import time

import httpx
from fastapi.testclient import TestClient

from aria import auth, config, hogar_cache, hogar_camaras, hogar_eventos as he, hogar_grabaciones, hogar_vigilancia as hv, main, usuarios

LAN = "https://192.168.1.50"
CAM = "192.168.1.30"
MOVILES = [{"mac": "AA:BB:CC:00:00:01", "nombre": "Pixel", "ip": "192.168.1.40"}]


def cliente(u):
    c = TestClient(main.app, base_url=LAN, follow_redirects=False)
    c.cookies.set(auth.COOKIE, auth.crear_sesion(u))
    return c


def _preparar(monkeypatch, estado="fuera", eventos=None, foto=b"\xff\xd8foto", falla_foto=False, falla_servicio=False):
    """Vigilancia activa con una cámara y el estado pedido; el servicio devuelve `eventos` (o falla)."""
    monkeypatch.setattr(config, "TAPO_USUARIO", "usuario@example.com")
    monkeypatch.setattr(config, "TAPO_PASSWORD", "clave-de-prueba")
    monkeypatch.setattr(config, "TAPO_CAMARAS", [CAM, "192.168.1.31"])
    monkeypatch.setattr(he, "_consultado", {})
    monkeypatch.setattr(he, "_avisado", {})
    hv.iniciar()
    he.iniciar()
    hv.configurar({"activa": True, "minutos": 10, "camaras": [CAM], "moviles": [hv.ident(MOVILES[0]["mac"])]}, MOVILES)
    hv._guardar(estado=estado)
    registro = {"consultas": [], "fotos": 0, "avisos": [], "eventos": list(eventos or [])}

    async def consultar(ruta, parametros):
        registro["consultas"].append((ruta, dict(parametros)))
        if falla_servicio:
            return httpx.Response(504, json={"error": "lenta"})
        return httpx.Response(200, json={"eventos": list(registro["eventos"])})

    async def foto_camara(ip, max_edad=0):
        registro["fotos"] += 1
        if falla_foto:
            raise RuntimeError("dormida")
        return foto

    async def emitir(tipo, severidad, texto, enlace="", **kw):
        registro["avisos"].append((tipo, severidad, texto, enlace))
        return []
    monkeypatch.setattr(hogar_grabaciones, "consultar", consultar)
    monkeypatch.setattr(hogar_camaras, "foto", foto_camara)
    monkeypatch.setattr(he.avisos, "emitir", emitir)
    hogar_cache.limpiar()
    hogar_cache._datos["camaras"] = (time.monotonic(), [{"ip": CAM, "nombre": "Jardín"}])
    return registro


def test_no_hace_nada_con_alguien_en_casa_ni_sin_vigilancia(monkeypatch):
    r = _preparar(monkeypatch, estado="casa", eventos=[{"inicio": 1000, "fin": 1010, "tipo": 6}])
    assert asyncio.run(he.ciclo(2000)) == 0 and r["consultas"] == [] and r["fotos"] == 0
    hv._guardar(estado="fuera")
    hv.configurar({"activa": False}, MOVILES)
    assert asyncio.run(he.ciclo(2000)) == 0 and r["consultas"] == []
    assert he.listar() == []


def test_guarda_los_nuevos_con_foto_y_avisa_una_vez_por_camara(monkeypatch):
    t = 1_800_000_000
    r = _preparar(monkeypatch, eventos=[{"inicio": t - 300, "fin": t - 280, "tipo": 6}, {"inicio": t - 120, "fin": t - 100, "tipo": 6}])
    assert asyncio.run(he.ciclo(t)) == 2
    assert r["consultas"] == [("/eventos", {"cam": "c1", "desde": t - 3600, "hasta": t})]   # solo la cámara vigilada
    lista = he.listar()
    assert [e["inicio"] for e in lista] == [t - 120, t - 300]                              # el más reciente primero
    assert lista[0]["tiene_foto"] is True and lista[1]["tiene_foto"] is False and r["fotos"] == 1
    assert lista[0]["nombre"] == "Jardín" and lista[0]["dia"] == he.dia_local(t - 120) and lista[0]["visto"] is False
    assert he.foto(lista[0]["id"]) == b"\xff\xd8foto" and he.foto(lista[1]["id"]) is None
    assert len(r["avisos"]) == 1
    tipo, severidad, texto, enlace = r["avisos"][0]
    assert (tipo, severidad, enlace) == ("vigilancia", "grave", "hogar")
    assert texto == f"Movimiento en Jardín a las {he.hora_local(t - 120)} y no hay nadie en casa."
    # Segunda vuelta: lo mismo otra vez no se repite ni se avisa; la consulta sigue desde la anterior (con solape)
    assert asyncio.run(he.ciclo(t + 60)) == 0
    assert r["consultas"][-1][1] == {"cam": "c1", "desde": t - 60, "hasta": t + 60} and len(r["avisos"]) == 1
    # Otro evento nuevo antes de 5 min: se guarda pero no se avisa; pasados 5 min, sí
    r["eventos"] = [{"inicio": t + 100, "fin": t + 110, "tipo": 6}]
    assert asyncio.run(he.ciclo(t + 120)) == 1 and len(r["avisos"]) == 1
    r["eventos"] = [{"inicio": t + 290, "fin": t + 300, "tipo": 6}]
    assert asyncio.run(he.ciclo(t + 301)) == 1 and len(r["avisos"]) == 2
    assert len(he.listar()) == 4 and he.marcar_vistos() == 4 and all(e["visto"] for e in he.listar())
    assert he.marcar_vistos() == 0


def test_sin_foto_y_sin_servicio_se_sigue_adelante(monkeypatch):
    t = 1_800_000_000
    r = _preparar(monkeypatch, eventos=[{"inicio": t - 10, "fin": t, "tipo": 2}], falla_foto=True)
    assert asyncio.run(he.ciclo(t)) == 1 and r["fotos"] == 1
    e = he.listar()[0]
    assert e["tiene_foto"] is False and e["tipo"] == 2 and len(r["avisos"]) == 1   # el evento y el aviso, igual
    r2 = _preparar(monkeypatch, eventos=[{"inicio": t - 5, "fin": t, "tipo": 2}], falla_servicio=True)
    assert asyncio.run(he.ciclo(t + 60)) == 0 and r2["avisos"] == [] and he._consultado == {}   # se reintentará desde el principio


def test_sin_nombre_conocido_dice_una_camara_y_actualiza_el_fin(monkeypatch):
    t = 1_800_000_000
    r = _preparar(monkeypatch, eventos=[{"inicio": t - 30, "fin": t - 20, "tipo": 6}])
    hogar_cache.limpiar()
    asyncio.run(he.ciclo(t))
    assert r["avisos"][0][2].startswith("Movimiento en una cámara a las ")
    r["eventos"] = [{"inicio": t - 30, "fin": t - 5, "tipo": 6}]            # la cámara alargó la misma detección
    assert asyncio.run(he.ciclo(t + 60)) == 0
    assert [(e["inicio"], e["fin"]) for e in he.listar()] == [(t - 30, t - 5)]


def test_purga_por_cantidad_y_por_edad(monkeypatch):
    t = 1_800_000_000
    _preparar(monkeypatch)
    viejos = [{"inicio": t - 31 * 86400, "fin": t - 31 * 86400 + 5, "tipo": 6}]
    muchos = [{"inicio": t - i, "fin": t - i + 1, "tipo": 6} for i in range(1, 320)]
    he._insertar(CAM, viejos + muchos, t)
    lista = he.listar(limite=500)
    assert len(lista) == he.MAX_FILAS and lista[0]["inicio"] == t - 1 and all(e["inicio"] >= t - 300 for e in lista)


def test_api_solo_admin_y_sin_blobs(monkeypatch):
    t = 1_800_000_000
    _preparar(monkeypatch, eventos=[{"inicio": t - 10, "fin": t, "tipo": 6}])
    asyncio.run(he.ciclo(t))
    admin = usuarios.por_identificador("admin")
    c = cliente(admin)
    d = c.get("/api/hogar/eventos").json()["eventos"]
    assert len(d) == 1 and set(d[0]) == {"id", "ip", "nombre", "inicio", "fin", "tipo", "tiene_foto", "visto", "dia"}
    assert d[0]["nombre"] == "Jardín" and d[0]["tiene_foto"] is True and d[0]["dia"] == he.dia_local(t - 10)
    f = c.get(f"/api/hogar/eventos/{d[0]['id']}/foto")
    assert f.status_code == 200 and f.content == b"\xff\xd8foto" and f.headers["content-type"] == "image/jpeg"
    assert f.headers["cache-control"] == "no-store"
    assert c.get("/api/hogar/eventos/999999/foto").status_code == 404
    assert c.post("/api/hogar/eventos/vistos").json() == {"vistos": 1}
    assert c.get("/api/hogar/eventos").json()["eventos"][0]["visto"] is True
    ana = usuarios.crear("ana@example.com", "Ana", "usuario", "clave-larga-ana")
    pepa = usuarios.actualizar(usuarios.crear("pepa@example.com", "Pepa", "usuario", "clave-larga-pepa")["id"], ver_camaras=True)
    for quien in (ana, pepa):   # ni siquiera con permiso de «ver cámaras»
        u = cliente(quien)
        assert u.get("/api/hogar/eventos").status_code == 403
        assert u.get(f"/api/hogar/eventos/{d[0]['id']}/foto").status_code == 403
        assert u.post("/api/hogar/eventos/vistos").status_code == 403
