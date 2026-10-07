"""SSO con Cloudflare Access: JWT firmados con una clave RSA local y JWKS simulado (sin red)."""
import asyncio
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

from aria import auth, config, main, sso, usuarios

TEAM, AUD = "equipo.cloudflareaccess.com", "a" * 64
PUBLICO = "https://aria.example.com"


def _clave():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


CLAVE, OTRA = _clave(), _clave()


def jwks(*pares):
    keys = []
    for kid, k in pares:
        d = RSAAlgorithm.to_jwk(k.public_key(), as_dict=True)
        d.update(kid=kid, alg="RS256", use="sig")
        keys.append(d)
    return {"keys": keys}


def token(email="ana@example.com", kid="k1", clave=None, **extra):
    ahora = int(time.time())
    datos = {"aud": [AUD], "iss": f"https://{TEAM}", "iat": ahora, "nbf": ahora - 1, "exp": ahora + 600,
             "email": email, "type": "app"}
    datos.update(extra)
    datos = {k: v for k, v in datos.items() if v is not None}
    return jwt.encode(datos, clave or CLAVE, algorithm="RS256", headers={"kid": kid})


@pytest.fixture
def cf(monkeypatch):
    monkeypatch.setattr(config, "CF_TEAM", TEAM)
    monkeypatch.setattr(config, "CF_AUD", AUD)
    est = {"jwks": jwks(("k1", CLAVE)), "llamadas": 0, "fallo": False}

    async def descargar():
        est["llamadas"] += 1
        if est["fallo"]:
            raise OSError("sin red")
        return est["jwks"]
    monkeypatch.setattr(sso, "_descargar_jwks", descargar)
    return est


def ident(t):
    return asyncio.run(sso.identificar(t))


# --- Verificación del JWT ---
def test_jwt_valido(cf):
    assert ident(token("Ana@Example.com")) == (sso.OK, "ana@example.com")


@pytest.mark.parametrize("extra", [
    {"exp": int(time.time()) - 3600},                  # caducado
    {"aud": ["b" * 64]},                               # aud equivocado
    {"aud": None},                                     # sin aud
    {"iss": "https://otro.cloudflareaccess.com"},      # iss equivocado
    {"nbf": int(time.time()) + 3600},                  # todavía no válido
    {"iat": int(time.time()) + 3600, "nbf": None},     # emitido en el futuro
    {"email": None},                                   # sin email (token de servicio)
    {"email": "sin-arroba"},
    {"exp": None},
])
def test_jwt_rechazado(cf, extra):
    assert ident(token(**extra))[0] == sso.INVALIDO


def test_firmado_con_otra_clave(cf):
    assert ident(token(clave=OTRA)) == (sso.INVALIDO, None)


def test_kid_desconocido_tras_refrescar(cf):
    assert ident(token(kid="desconocido")) == (sso.INVALIDO, None)
    assert cf["llamadas"] == 1


def test_kid_nuevo_se_descubre_refrescando(cf):
    assert ident(token())[0] == sso.OK
    cf["jwks"] = jwks(("k1", CLAVE), ("k2", OTRA))
    sso._intento = 0.0
    assert ident(token(kid="k2", clave=OTRA))[0] == sso.OK
    assert cf["llamadas"] == 2


def test_cache_y_limite_de_descargas(cf):
    for _ in range(3):
        assert ident(token())[0] == sso.OK
    assert cf["llamadas"] == 1
    for i in range(5):
        ident(token(kid=f"x{i}"))
    assert cf["llamadas"] == 1   # un kid inventado no hace martillear a Cloudflare


def test_alg_none_y_hs256_rechazados(cf):
    sin_firma = jwt.encode({"aud": [AUD], "iss": f"https://{TEAM}", "iat": int(time.time()),
                            "exp": int(time.time()) + 60, "email": "a@b.co"}, None, algorithm="none", headers={"kid": "k1"})
    assert ident(sin_firma)[0] == sso.INVALIDO
    hs = jwt.encode({"aud": [AUD], "iss": f"https://{TEAM}", "iat": int(time.time()),
                     "exp": int(time.time()) + 60, "email": "a@b.co"}, "k" * 40, algorithm="HS256", headers={"kid": "k1"})
    assert ident(hs)[0] == sso.INVALIDO


def test_sin_red_es_transitorio(cf):
    cf["fallo"] = True
    assert ident(token()) == (sso.TRANSITORIO, None)


def test_basura_y_desactivado(cf, monkeypatch):
    assert ident("no-es-un-jwt")[0] == sso.INVALIDO and ident(None)[0] == sso.INVALIDO
    monkeypatch.setattr(config, "CF_AUD", "")
    assert ident(token())[0] == sso.INVALIDO


# --- Integración con la aplicación ---
@pytest.fixture
def cliente(cf, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_EMAILS", ["pepe@example.com", "pepe2@example.com"])
    usuarios.crear("ana@example.com", "Ana", "usuario")
    usuarios.crear("baja@example.com", "Baja", "usuario")
    usuarios.actualizar(usuarios.por_email("baja@example.com")["id"], activo=False)
    return TestClient(main.app, base_url=PUBLICO, follow_redirects=False)


def con(t=None, **h):
    h = {k.replace("_", "-"): v for k, v in h.items()}
    return {**({"Cf-Access-Jwt-Assertion": t} if t else {}), **h}


def test_sso_entra_sin_formulario_y_crea_cookie(cliente):
    r = cliente.get("/", headers=con(token("ana@example.com")))
    assert r.status_code == 200
    assert auth.COOKIE in r.headers.get("set-cookie", "")
    # con la cookie ya no hace falta el JWT
    assert cliente.get("/api/info").json()["email"] == "ana@example.com"


def test_email_falsificado_sin_jwt_no_da_nada(cliente):
    for h in (con(Cf_Access_Authenticated_User_Email="pepe@example.com"),
              con("jwt-falso", Cf_Access_Authenticated_User_Email="pepe@example.com"),
              con(token(clave=OTRA), Cf_Access_Authenticated_User_Email="pepe@example.com")):
        r = cliente.get("/api/info", headers=h)
        assert r.status_code == 401
        r = cliente.get("/", headers=h)
        assert r.status_code == 303 and r.headers["location"] == "/login"
        assert auth.COOKIE not in r.headers.get("set-cookie", "")
    assert usuarios.por_email("pepe@example.com") is None  # ni siquiera se autocrea


def test_jwt_valido_de_quien_no_es_usuario(cliente):
    r = cliente.get("/", headers=con(token("intruso@example.com")))
    assert r.status_code == 403
    assert "Tu cuenta (intruso@example.com) no tiene acceso a ARIA. Pide al administrador que te invite." in r.text
    assert auth.COOKIE not in r.headers.get("set-cookie", "")
    assert "Chat con ARIA" not in r.text and usuarios.por_email("intruso@example.com") is None
    assert cliente.get("/api/conversations", headers=con(token("intruso@example.com"))).status_code == 403


def test_usuario_desactivado_no_entra(cliente):
    assert cliente.get("/", headers=con(token("baja@example.com"))).status_code == 403


def test_email_en_la_pagina_va_escapado(cliente):
    r = cliente.get("/", headers=con(token('"><script>x</script>@e.co')))
    assert r.status_code == 403 and "<script>x" not in r.text


def test_admin_se_autocrea(cliente):
    r = cliente.get("/api/info", headers=con(token("pepe2@example.com")))
    assert r.status_code == 200 and r.json()["rol"] == "admin"
    assert usuarios.por_email("pepe2@example.com")["rol"] == "admin"


def test_admin_email_se_restaura_si_alguien_lo_degrada_en_la_bd(cliente):
    cliente.get("/api/info", headers=con(token("pepe@example.com")))
    u = usuarios.por_email("pepe@example.com")
    with usuarios.closing(usuarios.db._con()) as c, c:
        c.execute("UPDATE usuarios SET rol='usuario', activo=0 WHERE id=?", (u["id"],))
    cliente.cookies.clear()
    assert cliente.get("/api/info", headers=con(token("pepe@example.com"))).json()["rol"] == "admin"


def test_cambio_de_cuenta_en_el_mismo_navegador(cliente):
    cliente.get("/", headers=con(token("ana@example.com")))
    assert cliente.get("/api/info").json()["email"] == "ana@example.com"
    r = cliente.get("/api/info", headers=con(token("pepe@example.com")))
    assert r.json()["email"] == "pepe@example.com"


def test_login_en_dominio_publico_con_sso_redirige(cliente):
    r = cliente.get("/login", headers=con(token("ana@example.com")))
    assert r.status_code == 303 and r.headers["location"] == "/" and auth.COOKIE in r.headers["set-cookie"]


def test_fallo_transitorio_muestra_entrando_y_reintenta(cliente, cf):
    cf["fallo"] = True
    for ruta in ("/login", "/"):
        r = cliente.get(ruta, headers=con(token("ana@example.com")))
        assert r.status_code == 503 and "Entrando con tu cuenta de Cloudflare…" in r.text
        assert 'http-equiv="refresh"' in r.text and 'type="password"' not in r.text
    assert cliente.get("/api/info", headers=con(token("ana@example.com"))).status_code == 401


def test_sin_jwt_en_dominio_publico_formulario_de_respaldo(cliente):
    r = cliente.get("/login")
    assert r.status_code == 200 and 'type="password"' in r.text


def test_salir_por_el_dominio_publico_cierra_cloudflare(cliente):
    cliente.get("/", headers=con(token("ana@example.com")))
    r = cliente.post("/logout")
    assert r.status_code == 303 and r.headers["location"] == f"https://{TEAM}/cdn-cgi/access/logout"
    assert cliente.get("/api/info").status_code == 401


def test_salir_en_la_lan_sigue_igual(cf):
    c = TestClient(main.app, base_url="https://192.168.1.50", follow_redirects=False)
    assert c.post("/logout").headers["location"] == "/login"


def test_sso_desactivado_ignora_el_jwt(cliente, monkeypatch):
    monkeypatch.setattr(config, "CF_AUD", "")
    assert cliente.get("/api/info", headers=con(token("ana@example.com"))).status_code == 401
