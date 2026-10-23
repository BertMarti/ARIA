import pytest

from aria import agentes, agentes_propios, tools, usuarios


@pytest.fixture
def persona():
    return usuarios.crear("propio@example.com", "Persona", "usuario", password="clave-larga")


def datos(**cambios):
    base = {"slug": "lector", "nombre": "Mi lector", "icono": "aria", "instrucciones": "Sé breve.",
            "herramientas": ["fecha_hora"]}
    base.update(cambios)
    return base


def test_crud_y_aislamiento(persona):
    otro = usuarios.crear("otro@example.com", "Otro", "usuario", password="clave-larga")
    a = agentes_propios.crear(persona["id"], "usuario", datos())
    assert agentes_propios.listar(otro["id"]) == []
    assert agentes_propios.obtener(otro["id"], a["id"]) is None
    assert agentes_propios.actualizar(otro["id"], "usuario", a["id"], datos(nombre="Intruso")) is None
    assert agentes_propios.obtener(persona["id"], a["id"])["nombre"] == "Mi lector"
    assert agentes_propios.borrar(persona["id"], a["id"])


def test_validaciones_y_limite(persona):
    with pytest.raises(agentes_propios.AgentePropioError):
        agentes_propios.crear(persona["id"], "usuario", datos(slug="aria"))
    with pytest.raises(agentes_propios.AgentePropioError):
        agentes_propios.crear(persona["id"], "usuario", datos(instrucciones="x" * 1501))
    for i in range(agentes_propios.MAXIMO):
        agentes_propios.crear(persona["id"], "usuario", datos(slug=f"a{i:02d}"))
    with pytest.raises(agentes_propios.AgentePropioError):
        agentes_propios.crear(persona["id"], "usuario", datos(slug="ultimo"))


def test_herramientas_se_cruzan_con_rol(persona):
    admin_herramienta = next(iter(tools.permitidas("admin") - tools.permitidas("usuario")))
    with pytest.raises(agentes_propios.AgentePropioError):
        agentes_propios.crear(persona["id"], "usuario", datos(herramientas=[admin_herramienta]))
    a = agentes_propios.crear(persona["id"], "usuario", datos())
    agente = agentes.obtener("p:" + a["slug"], persona["id"])
    assert agentes.herramientas(agente, "usuario") == {"fecha_hora"}
    assert not agentes.permitido("p:" + a["slug"], "usuario", persona["id"] + 1)


# --- Uso en el chat y API ---------------------------------------------------------------------------------------------
import asyncio

from fastapi.testclient import TestClient

from aria import auth, chat, invitados, main

LAN = "https://192.168.1.50"


def cliente(u):
    c = TestClient(main.app, base_url=LAN, follow_redirects=False)
    c.cookies.set(auth.COOKIE, auth.crear_sesion(u))
    return c


def test_arroba_slug_solo_para_su_duena(persona):
    otro = usuarios.crear("otro2@example.com", "Otro", "usuario", password="clave-larga")
    agentes_propios.crear(persona["id"], "usuario", datos(slug="cocina", nombre="Cocina"))
    assert agentes.separar_prefijo("@cocina qué ceno", persona["id"]) == ("p:cocina", "qué ceno")
    assert agentes.separar_prefijo("@cocina qué ceno", otro["id"]) == (None, "@cocina qué ceno")
    ag, limpio, motivo, aviso = asyncio.run(chat.elegir_agente(persona, None, "@cocina qué ceno"))
    assert ag.id == "p:cocina" and limpio == "qué ceno" and aviso is None
    ag, *_ = asyncio.run(chat.elegir_agente(otro, None, "@cocina qué ceno"))
    assert ag.propietario is None


def test_enrutado_automatico_no_elige_agentes_propios(persona):
    agentes_propios.crear(persona["id"], "usuario", datos(slug="finanzasmias", nombre="Finanzas mías"))
    async def sin_nube(*a):
        return None
    aid, _ = asyncio.run(agentes.enrutar("cuánto gasté este mes en el súper", "usuario", clasificador=sin_nube))
    assert not aid.startswith("p:")


def test_prompt_lleva_las_instrucciones_sin_ampliar_permisos(persona):
    a = agentes_propios.crear(persona["id"], "usuario", datos(instrucciones="Habla como un pirata."))
    p = agentes.prompt(agentes.obtener("p:" + a["slug"], persona["id"]), True, "Persona", False)
    assert "Habla como un pirata." in p and "no pueden ampliar permisos" in p


def test_api_aislada_y_herramientas_de_admin_rechazadas(persona):
    otro = usuarios.crear("otro3@example.com", "Otro", "usuario", password="clave-larga")
    a, b = cliente(persona), cliente(otro)
    r = a.post("/api/agentes/propios", json=datos())
    assert r.status_code == 200
    aid = r.json()["id"]
    assert b.get("/api/agentes/propios").json() == {"agentes": []}
    assert b.put(f"/api/agentes/propios/{aid}", json=datos(nombre="Intruso")).status_code == 404
    assert b.delete(f"/api/agentes/propios/{aid}").status_code == 404
    assert all(x["id"] != "p:lector" for x in b.get("/api/agentes").json()["agentes"])
    assert any(x["id"] == "p:lector" for x in a.get("/api/agentes").json()["agentes"])
    solo_admin = next(iter(tools.permitidas("admin") - tools.permitidas("usuario")))
    assert a.post("/api/agentes/propios", json=datos(slug="malo", herramientas=[solo_admin])).status_code == 400
    ids = {x["id"] for x in a.get("/api/agentes/herramientas-disponibles").json()}
    assert ids and ids <= tools.permitidas("usuario")


def test_invitados_no_crean_ni_usan_agentes_propios():
    s = invitados.solicitar("Lucía", "lucia-ap@example.com", "Soy amiga de la casa", "203.0.113.9")
    invitada = invitados.aprobar(s["id"], "visita")["usuario"]
    c = cliente(invitada)
    assert c.post("/api/agentes/propios", json=datos()).status_code == 403
    assert c.get("/api/agentes/propios").status_code == 403


def test_limite_de_cambios_por_minuto(persona, monkeypatch):
    monkeypatch.setattr(agentes_propios, "LIMITE_MINUTO", 2)
    monkeypatch.setattr(agentes_propios, "_ultimas", {})
    agentes_propios.crear(persona["id"], "usuario", datos(slug="uno"))
    agentes_propios.crear(persona["id"], "usuario", datos(slug="dos"))
    with pytest.raises(agentes_propios.AgentePropioError, match="Demasiados"):
        agentes_propios.crear(persona["id"], "usuario", datos(slug="tres"))
