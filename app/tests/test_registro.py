import asyncio
import time
from contextlib import closing

from fastapi.testclient import TestClient

from aria import auth, db, main, registro, tools, usuarios

LAN = "https://192.168.1.50"


def cliente_de(u):
    c = TestClient(main.app, base_url=LAN, follow_redirects=False)
    c.cookies.set(auth.COOKIE, auth.crear_sesion(u))
    return c


def filas():
    return registro.listar(limite=500)


def test_limpiar_args_oculta_y_recorta():
    r = registro.limpiar_args({"Password": "secreto", "texto": "x" * 300, "uid": 9, **{f"k{i}": i for i in range(25)}})
    assert r["Password"] == "***" and len(r["texto"]) == 200 and "uid" not in r and len(r) <= 20


def test_ejecutar_anota_resultado_error_y_desconocida(monkeypatch):
    asyncio.run(tools.ejecutar("fecha_hora", {}, uid=1))
    monkeypatch.setitem(tools._REGISTRO["fecha_hora"], "fn", lambda: (_ for _ in ()).throw(RuntimeError("fallo")))
    asyncio.run(tools.ejecutar("fecha_hora", {}, uid=1, agente="aria"))
    asyncio.run(tools.ejecutar("no_existe", {}, uid=1))
    assert [f["ok"] for f in filas()[:3]] == [0, 0, 1]


def test_ejecutar_anota_denegado_y_origen():
    with registro.origen("rutina"):
        asyncio.run(tools.ejecutar("spotify_play", {}, "usuario", uid=2))
    f = filas()[0]
    assert f["ok"] == 0 and f["origen"] == "rutina" and f["resultado"] == "No tienes permiso para esa acción: pídesela al administrador."


def test_purgar():
    with closing(db._con()) as con, con:
        con.execute("INSERT INTO registro_herramientas(ts,rol,origen,herramienta,args,ok,resultado,ms) VALUES(?,?,?,?,?,?,?,?)",
                    (time.time() - 31 * 86400, "admin", "chat", "vieja", "{}", 1, "", 1))
    registro.purgar()
    assert not any(f["herramienta"] == "vieja" for f in filas())


def test_api_registro_solo_admin_y_filtros():
    admin = usuarios.por_identificador("admin")
    ana = usuarios.crear("ana@example.com", "Ana", "usuario", "clave-larga-ana")
    asyncio.run(tools.ejecutar("fecha_hora", {}, uid=admin["id"]))
    asyncio.run(tools.ejecutar("spotify_play", {}, "usuario", uid=ana["id"]))
    assert cliente_de(ana).get("/api/registro").status_code == 403
    r = cliente_de(admin).get("/api/registro?herramienta=spotify_play&errores=1")
    assert r.status_code == 200 and all(f["herramienta"] == "spotify_play" and not f["ok"] for f in r.json()["filas"])
