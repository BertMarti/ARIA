"""Módulo «RUNA»: protocolo compatible con la web de RUNA, herramientas del chat y chequeo. Sin red: RUNA
falso con httpx.MockTransport. Los vectores los generó la implementación real (apps/web/src/crypto de RUNA)."""
import asyncio
import base64
import hashlib
import importlib.util
import json
import re
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aria import avisos, modulos, tools

REPO_MODULOS = Path(__file__).resolve().parents[2] / "modulos"
pytestmark = pytest.mark.skipif(not (REPO_MODULOS / "runa").is_dir(), reason="sin la carpeta modulos/ del repositorio")
PUBLICA = "https://192.168.1.50:8485"
ENLACE = re.compile(r"https://192\.168\.1\.50:8485/s/([A-Za-z0-9_-]{22})#(v1\.[A-Za-z0-9_-]{43}(?:\.p)?)")
TICKET = re.compile(r"https://192\.168\.1\.50/api/modulos/runa/recoger/([A-Za-z0-9_-]{43})")

# Secretos cifrados por la web de RUNA (valores inventados).
VECTORES_WEB = json.loads(r"""[
    {
        "contrasena": null,
        "texto": "Wifi de invitados: Aurora-Boreal-2026!",
        "ciphertext": "9olyJI1nQrsLQzGms9ISId1x7zRrX2N5n-aucDhJlzNf0skNHXnDnilwHkb0p4jnbF-n2ZRVSWgBDxTx7zoG3yEzMGjKEnMnhh6U3j6W4PECv64TTfXCnAdCZPw5pKXC0ElAV5lMBxzB35vQxAfqLbKIODP-Glw-dWKIQuyIeNsGyLlCDlzMNg5tAWAvihdk34gaXh8GVezyWbuzLDjgcFGylsFVX303dYBfCXTfejDMqz4M7Kw3bX4UlOtwyT2yff8yEZ5eb4RV5-ZiHHJSsZVfdu1CzwcPbd-8AY1qw7QWbyfV7X6tqjqE4WTuTNudQwWorSNtlkvbiXdtLkCSJ8mmNqffq_lNgf-hbPXs9S0zpAsPS6EKe5S_po1G7fq2IUssm0ADtziqu7kecWHRMgpeePpR_M5t5NX-M_WkrXaJy1MTDt8bijeoU5rlCSGiTWkD--h_rEn091V6jXvV4_bQCrIqrUbbaTGZYuzDSqLEzt-JMOc-0LIBwQR0bq7kjnWIcNwv18SlMcwtwQ4aL63Nla4wEoteVgm5BzYq9hC6E5ZGIFS0Yhh2HOSpjhuk4W5u3hbRgCfq0ciiV_1rB3CpI2kvpcaejoXrGNuh83ri_rdcTlrLJ-oVAVy_PZEJIq9w7YX-bDuYdctQUSAM3_1AMywNhxOlkidAjV4EZFCa6XOjVwj_IWWG4Cim8IA0HRYUVC6u_tT14jPF7xrJ_OTWtC7V51HjTPckqS00If4IqAfl-SaupVzSDPHQBtYqfxtMWz-ni8jIJDtGv1Tm2uwRUOMpYf__qScJBx1p0-74kwT9fV1Uaslb9z_Ukv0EqjVpxvUtxiOzSenezrFPgG8va6kanoqG5jaFLpv-RzCysSI6m9EaS-VUKz9D3ImifTjq7LNKTROt0hXcZjhAdVec9KZ7onV1HpUd1xzD1h_xVgVO2gOv-vChRPIby7nWemLUtiCT77i3Bzn2P4PEZRxmar2lnLd9NYcqrMVlwe6gl3e3BF3RCHcbAhzs2FwlzItja8QDoA9WBg0lPQ-NDkh4Bz5-n4IoKv-4Y17obG7j-WSxqjN1h8piUYvam5ojjis3NxOme52g9QLnns5coAfl3hVxEcfd-RfH2XeMiFpySIb2ifbiwfOk9IiqFaOahWiYvTGzrBB1_7mdCEvgYZoN5y-AmOzxvIVxc8t5lxTruYkWO7pk_5ECwbI24dITDi-1HNxhRk2ZhZYD8-X_WkmDSctSguz68W3AuSxXORPGT0RIryy3ev81CYwIPbpOzPblbsf7wWIwFMF9CVx77_TAzVgakErEd5UjdbvWHr1Dp_cyBtL3IYsRKU5_2zGAwgYvNEx1OzjMYJ7lMO26y_Dqf5c61cV9Q1CwOvLcK3DhgNHjUogX93J6_ek",
        "fragment": "v1.w0DpQbrmEZ7zJVjEjG8gQV8A8qZNWGNqFHZeNu966qY",
        "proof": {
            "link": "4408e3a2c08efdd1b1b506248f44a4069534f0246b662b74a77751ae79384ee4",
            "token": "ff3f09638d05cfee1f1bcec5c0fe7c2bbff6ad022d9e88deda075ae68ffe3c82"
        }
    },
    {
        "contrasena": "caballo correcto batería grapa",
        "texto": "Clave del router: ñandú-42 ✓",
        "ciphertext": "4Elr9mmcf6MhaiTEn1ofpj5J6WyNcTKOHpk_Vvs3XR16m7nx_EnwAUkTimAIh1d_KxuNplaWcmApoXrha-bobjrh2g-AGzPfFIFFYYmOcNVzUuuYlibbAfqWEFCC3JkiL3in09ZPm2EmTjZdKEYoSC_jE2fteozkWhuWpVpTIeVYFYwdp9vbHHAoiBCj6GLt1XLXeLM_J_-qYxl34a7bsOAhlASgRltxa700mlBangtNPBH-yRrd9UXb56_CNkeCDTPFad5pgbG0fM1nkUru2UhELT11NGPBmGUQ1a_Sb7tzHV-qK-sNinletEm818lJwrRXRXRr2fJS81LtETN1gzY6pVZT2C-OAhioLDsN__lDzyQVJZXuw8kwj-TmQDYHRlIv9RBxju_onrx1T0fdjaKDWJ5nT02zLLOt7WSfcVCLsKBoxE7o-0sb9FrLoauiJo0GIvAGdJ7ouF-xDQVYvmFPo0W58B9KiY7AaJfolJJK0yhz_CbxD_pHd-0QJvAux9bTtJJ0hhKeiQz_CaZpxS7rfq7UwWlKrG3gsn7Nd58gJzcZq7is7u7FD27XGwRPRMMeqlTT4QNB7OC2O4GpwnEi8UDcF0y8N2es8iznY1W2b3I8cKE-ApDUgPdLUmoxGwuR0ihXDGFIDLphlRzmtD78l6lIstey_tI9ZZFMiYYtVBgNpZp93j-BNmQzocwE2Yo4bjwDHw5TwTeQX54a8vRDq498IoA3eNcO2i4ExTUwrc1Uz2UQkA2O37MWtU-MBAq47bDXCTxA_fEFQg5biyR_rhNt_DAVBJSxQB_WtpF6bk3V1AXK_eONdvvzswWoJM5JjnX2GE0YOVOi6VUv22G03IXOHxzUvjjxe7TvFcqrVSacGiba_xtpuCreZjHS_uGbLndVzhRQxIWWcsexbWqpqVpF65dX7GLY8LBJxOuE7vZHpqpHyx36Cv-UPTXusY-3MmnpmP8IY_cAskDWHytAXlhDc2dD6fQ-LoiJwrqraHuxjGC0NBQv0njny4s8xDXTJqtC4Uc0QqGhUxzWEBztRTQPzRb9mU6HIRUCljtLsxKVwQLAZPiD57HgPVjkrENoR-W1f-ZrgC_uttl6L1CM-AZXQcPb52DDrkmFtc7tkYSW_HvWQ7iW-qDp5aOWvQnUp5r3oGtdfNhN-yQwcW6AgLdE4m_zFh974g10B3TCjWOd3DSCDBwCjb6ODiF42160ua6vFmScG1f93WO27adwKUVvMqnlIxqOWxkWj50ch-w8aRjEZdPFtI5dZpLz5bKRenWPOJzg5Shmn-EtS6EPHYoTOYMAkvIgNylmefyiaIBuZJQJPDBLEtL4eHJsiuPFtzclO4juVsXXhZQ3lb3nRChwqOzl5ETHwNCqoZX8HaGsuyHGS_rGAWA",
        "fragment": "v1.woNsC-8icNONpDJHVJsl_7uwSfRXbPrY6rgBOK6DhQA.p",
        "proof": {
            "link": "489df800b9f4e8fb4d34632dfcc50221975f5c06fed888dc5182af59d14a7bad",
            "token": "d99b9e24184a06a1e02531d20c2ef58459eef62b6cb2f8ddb3f993316c01282d"
        }
    }
]""")


def correr(c):
    return asyncio.run(c)


@pytest.fixture(scope="module")
def protocolo():
    spec = importlib.util.spec_from_file_location("runa_protocolo", REPO_MODULOS / "runa" / "protocolo.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class RunaFalso:
    """Imita la API de RUNA: valida lo que recibe como el servidor real y guarda el cifrado."""

    def __init__(self):
        self.secretos: dict[str, dict] = {}
        self.codigo: int | None = None    # fuerza una respuesta (429, 507...)
        self.sano = True

    def __call__(self, req: httpx.Request) -> httpx.Response:
        assert req.url.host == "runa" and req.url.port == 8080
        if req.method == "GET" and req.url.path == "/api/health":
            return httpx.Response(200 if self.sano else 503, json={"status": "ok"})
        assert req.method == "POST" and req.url.path == "/api/secrets"
        if self.codigo:
            return httpx.Response(self.codigo, json={"error": "x"})
        b = json.loads(req.content)
        assert set(b) == {"ciphertext", "verifier", "linkVerifier", "ttl", "views"}
        assert re.fullmatch(r"[0-9a-f]{64}", b["verifier"]) and re.fullmatch(r"[0-9a-f]{64}", b["linkVerifier"])
        assert b["ttl"] in (300, 3600, 86_400, 604_800) and 1 <= b["views"] <= 10
        crudo = base64.urlsafe_b64decode(b["ciphertext"] + "=" * (-len(b["ciphertext"]) % 4))
        assert len(crudo) - 28 in [k * 1024 for k in (1, 4, 16, 64, 256, 1024, 4096)]   # bloque exacto
        sid = f"id{len(self.secretos):020d}"
        self.secretos[sid] = b
        return httpx.Response(201, json={"id": sid, "expiresAt": "2026-10-25T10:00:00.000Z"})


@pytest.fixture
def runa(monkeypatch):
    falso = RunaFalso()
    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(falso), **kw))
    return falso


@pytest.fixture
def cargar(monkeypatch):
    antes = dict(modulos._CARGADOS)
    cargados = []

    def hacer(url="http://runa:8080", publica=PUBLICA, aria_publica=None, hosts=None):
        for clave, valor in (("RUNA_URL", url), ("RUNA_URL_PUBLICA", publica), ("ARIA_LAN_IP", "192.168.1.50"),
                             ("ARIA_URL_PUBLICA", aria_publica), ("ARIA_HOSTS", hosts)):
            if valor is None:
                monkeypatch.delenv(clave, raising=False)
            else:
                monkeypatch.setenv(clave, valor)
        hacer.app = FastAPI()
        res = modulos.cargar(hacer.app, REPO_MODULOS, {"runa"})
        cargados.append(res)
        return res["runa"]
    yield hacer
    for res in cargados:
        for m in res.values():
            m.retirar()
    modulos._CARGADOS.clear()
    modulos._CARGADOS.update(antes)


def abrir_enlace(protocolo, runa, salida):
    """Lo que haría el navegador de quien recibe: id + fragmento → descifrar lo que guardó RUNA."""
    enlaces = ENLACE.findall(salida)
    return [(runa.secretos[sid], protocolo.abrir(runa.secretos[sid]["ciphertext"], frag)["text"]) for sid, frag in enlaces]


# --- Protocolo ------------------------------------------------------------------------------------------------

def test_abre_secretos_creados_por_la_web(protocolo):
    for v in VECTORES_WEB:
        assert protocolo.abrir(v["ciphertext"], v["fragment"], v["contrasena"])["text"] == v["texto"]
        assert protocolo.prueba(v["fragment"], v["contrasena"]) == v["proof"]


def test_ida_y_vuelta_y_verificadores(protocolo):
    s = protocolo.sellar("Clave: Ñu-77 ✓", "fiordo azul")
    assert s["fragmento"].endswith(".p") and s["fragmento"].split(".")[1] not in s["ciphertext"]
    assert protocolo.abrir(s["ciphertext"], s["fragmento"], "fiordo azul")["text"] == "Clave: Ñu-77 ✓"
    p = protocolo.prueba(s["fragmento"], "fiordo azul")
    assert hashlib.sha256(bytes.fromhex(p["token"])).hexdigest() == s["verifier"]
    assert hashlib.sha256(bytes.fromhex(p["link"])).hexdigest() == s["linkVerifier"]
    with pytest.raises(protocolo.ProtocoloError):
        protocolo.abrir(s["ciphertext"], s["fragmento"], "otra")


def test_relleno_alteracion_y_nombres(protocolo):
    corto, largo = protocolo.sellar("a"), protocolo.sellar("a" * 900)
    assert len(protocolo.desde_b64url(corto["ciphertext"])) == len(protocolo.desde_b64url(largo["ciphertext"])) == 1052
    crudo = bytearray(protocolo.desde_b64url(corto["ciphertext"]))
    crudo[-20] ^= 1
    with pytest.raises(protocolo.ProtocoloError):
        protocolo.abrir(protocolo.b64url(bytes(crudo)), corto["fragmento"])
    assert protocolo.nombre_seguro("../../etc/passwd") == "passwd"
    assert protocolo.nombre_seguro("factura‮fdp.exe") == "facturafdp.exe"
    with pytest.raises(protocolo.ProtocoloError):
        protocolo.leer_fragmento("#v1.corta")


# --- Módulo ---------------------------------------------------------------------------------------------------

def test_estados_segun_configuracion(cargar):
    assert cargar(url=None).estado == "sin_configurar"
    m = cargar(url="ftp://runa:8080")
    assert m.estado == "error" and "RUNA_URL" in m.error
    m = cargar()
    assert m.estado == "activo", m.error
    assert {h["nombre"] for h in m.herramientas} == {"runa_compartir", "runa_generar"} and m.chequeos == ["caido"]
    assert {"runa_compartir", "runa_generar"} <= tools.permitidas("usuario")
    assert "runa_compartir" not in tools.RUTINAS     # crea cosas: nunca en rutinas
    assert set(m.rutas_usuario) == {("GET", "/api/modulos/runa/recoger/{ticket}"),
                                    ("GET", "/api/modulos/runa/abrir")}   # con sesión: lo impone permisos.py


def test_compartir(cargar, runa, protocolo):
    cargar()
    salida = correr(tools.ejecutar("runa_compartir",
                                   {"texto": "Wifi invitados: Aurora-2026", "caducidad": "1 hora", "lecturas": "3"},
                                   "usuario"))
    assert "Aurora-2026" not in salida and "caduca en 1 hora, 3 lecturas" in salida
    assert "sigue en esta conversación" in salida                 # aviso honesto: el texto pasó por el chat
    [(guardado, texto)] = abrir_enlace(protocolo, runa, salida)
    assert texto == "Wifi invitados: Aurora-2026" and guardado["ttl"] == 3600 and guardado["views"] == 3
    assert "Aurora" not in json.dumps(guardado)                   # a RUNA solo llega ruido


@pytest.mark.parametrize("pedido,ttl", [("", 86_400), ("5 min", 300), ("media hora", 3600), ("45", 3600), ("90", 86_400),
                                        ("un día", 86_400), ("2 días", 604_800), ("una semana", 604_800),
                                        ("un mes", 604_800)])
def test_caducidad(cargar, runa, pedido, ttl):
    cargar()
    correr(tools.ejecutar("runa_compartir", {"texto": "x", "caducidad": pedido, "lecturas": 99}, "admin"))
    guardado = list(runa.secretos.values())[-1]
    assert guardado["ttl"] == ttl and guardado["views"] == 10


def test_generar_no_pasa_contrasena_ni_llaves_por_el_modelo(cargar, runa, protocolo):
    cargar()
    salida = correr(tools.ejecutar("runa_generar", {"longitud": 24, "lecturas": 2}, "usuario"))
    # Al modelo (y al historial) solo llegan tickets de ARIA: ni la contraseña ni enlaces de RUNA con su llave.
    assert "#v1." not in salida and ":8485" not in salida and not ENLACE.search(salida)
    ver, compartir = TICKET.findall(salida)
    cli = TestClient(cargar.app, base_url="https://192.168.1.50")

    r = cli.get(f"/api/modulos/runa/recoger/{ver}", follow_redirects=False)
    assert r.status_code == 303 and r.headers["cache-control"] == "no-store"
    [(guardado_ver, clave)] = abrir_enlace(protocolo, runa, r.headers["location"])
    r = cli.get(f"/api/modulos/runa/recoger/{compartir}")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    [(guardado_compartir, clave2)] = abrir_enlace(protocolo, runa, r.text)

    assert clave == clave2 and len(clave) == 24 and clave not in salida
    assert guardado_ver["views"] == 1 and guardado_compartir["views"] == 2
    assert not re.search(r"[0OlI1]", clave)                       # sin caracteres que se confunden
    # Un solo uso, y un ticket inventado no sirve
    for t in (ver, compartir, "x" * 43, "corto"):
        assert cli.get(f"/api/modulos/runa/recoger/{t}", follow_redirects=False).status_code == 404


def test_tickets_caducan(cargar, runa, monkeypatch):
    cargar()
    salida = correr(tools.ejecutar("runa_generar", {}, "admin"))
    ver, _ = TICKET.findall(salida)
    import time as reloj
    ahora = reloj.time()
    monkeypatch.setattr(reloj, "time", lambda: ahora + 31 * 60)
    assert TestClient(cargar.app).get(f"/api/modulos/runa/recoger/{ver}", follow_redirects=False).status_code == 404


def test_errores_de_runa(cargar, runa):
    cargar()
    runa.codigo = 429
    assert "limitando" in correr(tools.ejecutar("runa_compartir", {"texto": "x"}, "admin"))
    runa.codigo = 507
    assert "espacio" in correr(tools.ejecutar("runa_compartir", {"texto": "x"}, "admin"))
    assert "Falta el texto" in correr(tools.ejecutar("runa_compartir", {"texto": "  "}, "admin"))


def test_intenciones(cargar):
    cargar()
    assert "runa_compartir" in tools.relevantes("comparte la contraseña del wifi con mi hermana")
    assert "runa_compartir" in tools.relevantes("mándalo por runa")
    assert "runa_generar" in tools.relevantes("genera una contraseña nueva para el router")
    for charla in ("hola", "explícame qué es un dns", "¿qué tiempo hace mañana?"):
        assert not {"runa_compartir", "runa_generar"} & tools.relevantes(charla)


def test_chequeo_caido(cargar, runa):
    cargar()
    c = avisos.chequeos()["modulo:runa:caido"]
    assert c.intervalo_s == 300 and c.solo_admin
    assert correr(c.fn()) == []
    runa.sano = False
    [problema] = correr(c.fn())
    assert problema.clave == "runa"


@pytest.mark.parametrize("host,destino", [
    ("192.168.1.50", "https://192.168.1.50:8485/"),        # en casa por IP: el RUNA de la LAN (se puede crear)
    ("aria.local", "https://aria.local:8485/"),            # en casa por nombre (ARIA_HOSTS)
    ("aria.example.com", "https://runa.example.com/"),     # desde fuera por el túnel: el RUNA público
    ("malo.example", "https://runa.example.com/"),         # un Host desconocido nunca decide el destino
])
def test_mosaico_abre_el_runa_adecuado(cargar, host, destino):
    cargar(publica="https://runa.example.com", aria_publica="https://aria.example.com",
           hosts="aria.local,aria.example.com")
    r = TestClient(cargar.app, base_url=f"https://{host}").get("/api/modulos/runa/abrir", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == destino
