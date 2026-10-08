import pytest

from aria import tools

SIN_HERRAMIENTAS = [
    "Hola", "Buenos días, ¿qué tal?", "Cuéntame un chiste", "Explícame qué es un DNS",
    "Explícame qué es la memoria RAM", "¿Cómo funciona un servidor web?", "Gracias, eres genial",
    "Escribe un poema sobre el mar", "¿Qué es una VPN?",
]


@pytest.mark.parametrize("texto", SIN_HERRAMIENTAS)
def test_conversacion_sin_herramientas(texto):
    assert tools.relevantes(texto) == set()


@pytest.mark.parametrize("texto,esperada", [
    ("¿Qué hora es?", "fecha_hora"),
    ("¿Cuántos anuncios has bloqueado hoy?", "estado_bloqueador"),
    ("Dame las estadísticas de Pi-hole", "estado_bloqueador"),
    ("Pausa el bloqueador 5 minutos", "pausar_bloqueador"),
    ("Desactiva la publicidad 10 minutos", "pausar_bloqueador"),
    ("Reanuda el bloqueador", "reanudar_bloqueador"),
    ("Activa el bloqueador de anuncios", "reanudar_bloqueador"),
    ("¿Qué dispositivos hay en la VPN?", "dispositivos_vpn"),
    ("¿Quién está conectado a la VPN?", "dispositivos_vpn"),
    ("¿Qué temperatura tiene la Raspberry?", "estado_sistema"),
    ("¿Cuánto espacio libre queda en el disco?", "estado_sistema"),
    ("¿Cuánta RAM está usada?", "estado_sistema"),
    ("Pon música de Queen", "spotify_play"),
    ("Busca una serie en Netflix", "buscar_en_netflix"),
])
def test_herramienta_correcta(texto, esperada):
    assert esperada in tools.relevantes(texto)


def test_pausar_no_ofrece_spotify_ni_fecha():
    r = tools.relevantes("Pausa el bloqueador 5 minutos")
    assert r == {"pausar_bloqueador"}


def test_temperatura_no_ofrece_spotify():
    assert not any(n.startswith("spotify") for n in tools.relevantes("¿Cuánto disco libre tiene la Raspberry?"))


def test_toda_herramienta_tiene_intencion():
    ofrecidas = set().union(*(n for _, n in tools._INTENCIONES))
    assert set(tools._REGISTRO) <= ofrecidas


def test_rescatar_llamada_json_en_texto():
    ll = tools.rescatar_llamada('{"name": "pausar_bloqueador", "parameters": {"minutos": 15}}', {"pausar_bloqueador"})
    assert ll == {"function": {"name": "pausar_bloqueador", "arguments": {"minutos": "15"}}}


def test_rescatar_llamada_con_cadena_y_unicode():
    ll = tools.rescatar_llamada('{"name": "buscar_en_netflix", "titulo": "El se\\u00f1or"}', {"buscar_en_netflix"})
    assert ll["function"]["arguments"]["titulo"] == "El señor"


def test_rescatar_llamada_sin_argumentos_obligatorios():
    assert tools.rescatar_llamada('{"name": "buscar_en_netflix"}', {"buscar_en_netflix"}) is None


def test_rescatar_llamada_herramienta_no_permitida():
    assert tools.rescatar_llamada('{"name": "estado_sistema"}', {"fecha_hora"}) is None


def test_rescatar_llamada_sin_parametros():
    assert tools.rescatar_llamada('{"name":"reanudar_bloqueador"}', {"reanudar_bloqueador"})["function"]["name"] == "reanudar_bloqueador"


def test_pausar_valida_rango():
    import asyncio
    assert "entre 1 y 120" in asyncio.run(tools.ejecutar("pausar_bloqueador", {"minutos": 500}))
    assert "entre 1 y 120" in asyncio.run(tools.ejecutar("pausar_bloqueador", {"minutos": 0}))


@pytest.mark.parametrize("texto,esperadas", [
    ("Añade un dispositivo a la VPN llamado movil-ana", {"crear_dispositivo_vpn"}),
    ("Crea un móvil nuevo en la VPN", {"crear_dispositivo_vpn"}),
    ("Desactiva el dispositivo tele en la VPN", {"activar_dispositivo_vpn", "desactivar_dispositivo_vpn"}),
    ("Desactiva el dispositivo Tele del salón", {"desactivar_dispositivo_vpn"}),
    ("Activa otra vez el dispositivo Móvil de Ana", {"activar_dispositivo_vpn"}),
])
def test_gestion_vpn(texto, esperadas):
    assert esperadas <= tools.relevantes(texto)


@pytest.mark.parametrize("texto", ["Hola, ¿qué tal?", "Cuéntame un chiste", "Explícame cómo funciona una VPN",
                                   "¿Qué es WireGuard?", "Crea un poema", "Activa tu imaginación",
                                   "¿Qué dispositivos son compatibles con Netflix?"])
def test_gestion_vpn_no_se_activa_en_charla(texto):
    r = tools.relevantes(texto)
    assert not r & {"crear_dispositivo_vpn", "activar_dispositivo_vpn", "desactivar_dispositivo_vpn"}


def test_borrar_vpn_sigue_sin_ser_herramienta():
    # (borrar_recordatorio y borrar_rutina solo tocan lo del propio usuario)
    assert not any("eliminar" in n or "borrar" in n for n in tools._REGISTRO
                   if n not in ("borrar_recordatorio", "borrar_rutina", "borrar_automatizacion"))


def test_nombre_invalido_en_crear():
    import asyncio
    assert "no válido" in asyncio.run(tools.ejecutar("crear_dispositivo_vpn", {"nombre": "../malo"}))
