"""Notificaciones push: cifrado aes128gcm (RFC 8291), cabecera VAPID, suscripciones por usuario, poda de
caducadas y service worker."""
import asyncio
import json
import struct

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi.testclient import TestClient

from aria import auth, avisos, main, push, usuarios

LAN = "https://192.168.1.50"
EP = "https://fcm.googleapis.com/fcm/send/abc123"


def correr(c):
    return asyncio.run(c)


def cliente_de(u) -> TestClient:
    c = TestClient(main.app, base_url=LAN, follow_redirects=False)
    c.cookies.set(auth.COOKIE, auth.crear_sesion(u))
    return c


@pytest.fixture
def admin():
    return usuarios.por_identificador("admin")


@pytest.fixture
def ana():
    return usuarios.crear("ana@example.com", "Ana", "usuario", "clave-larga-ana")


class Navegador:
    """El lado del navegador (user agent): sus claves y el descifrado según RFC 8291."""

    def __init__(self, endpoint=EP):
        self.k = ec.generate_private_key(ec.SECP256R1())
        self.pub = self.k.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        self.auth = b"0123456789abcdef"
        self.endpoint = endpoint

    def sub(self):
        return {"endpoint": self.endpoint, "keys": {"p256dh": push.b64u(self.pub), "auth": push.b64u(self.auth)}}

    def descifrar(self, cuerpo: bytes) -> bytes:
        sal, rs, idlen = cuerpo[:16], struct.unpack(">I", cuerpo[16:20])[0], cuerpo[20]
        as_pub = cuerpo[21:21 + idlen]
        assert rs == 4096 and idlen == 65
        comp = self.k.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_pub))
        prk_k = push._hmac(self.auth, comp)
        ikm = push._hmac(prk_k, b"WebPush: info\x00" + self.pub + as_pub + b"\x01")
        prk = push._hmac(sal, ikm)
        cek = push._hmac(prk, b"Content-Encoding: aes128gcm\x00\x01")[:16]
        nonce = push._hmac(prk, b"Content-Encoding: nonce\x00\x01")[:12]
        claro = AESGCM(cek).decrypt(nonce, cuerpo[21 + idlen:], None)
        assert claro.endswith(b"\x02")
        return claro[:-1]


def test_cifrado_ida_y_vuelta():
    n = Navegador()
    cif = push.cifrar(b'{"hola": "mundo"}', push.b64u(n.pub), push.b64u(n.auth))
    assert n.descifrar(cif) == b'{"hola": "mundo"}'
    otra = push.cifrar(b'{"hola": "mundo"}', push.b64u(n.pub), push.b64u(n.auth))
    assert otra != cif  # sal y clave efímera nuevas en cada mensaje


def test_cabecera_vapid():
    pub, priv = push.claves()
    cab = push.cabecera_vapid(EP)
    t, k = cab.removeprefix("vapid t=").split(", k=")
    assert k == pub
    clave = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), push.de_b64u(pub))
    datos = jwt.decode(t, clave, algorithms=["ES256"], audience="https://fcm.googleapis.com")
    assert datos["sub"].startswith("mailto:") and datos["exp"] > 0


def test_claves_se_generan_una_vez(tmp_path):
    a = push.claves()
    push._claves.clear()
    assert push.claves() == a and (tmp_path / "vapid.json").stat().st_mode & 0o777 == 0o600
    assert len(push.de_b64u(a[0])) == 65 and len(push.de_b64u(a[1])) == 32


@pytest.mark.parametrize("ep,ok", [
    (EP, True), ("https://updates.push.services.mozilla.com/wpush/v2/x", True),
    ("https://web.push.apple.com/QGx", True), ("https://wns2-db5p.notify.windows.com/w/?token=x", True),
    ("http://fcm.googleapis.com/x", False), ("https://192.168.0.1/x", False), ("https://evil.com/fcm.googleapis.com", False),
    ("https://fcm.googleapis.com.evil.com/x", False), ("https://user@fcm.googleapis.com/x", False),
    ("https://fcm.googleapis.com:8443/x", False), ("https://localhost/x", False), (None, False),
])
def test_solo_servicios_push_conocidos(ep, ok):
    assert push.endpoint_valido(ep) is ok


def test_crud_de_suscripciones_por_api_e_idor(admin, ana):
    ca, cadm = cliente_de(ana), cliente_de(admin)
    n = Navegador()
    r = ca.post("/api/push/suscripciones", json={"suscripcion": n.sub(), "nombre": "Móvil de Ana"})
    assert r.status_code == 200 and r.json()["dispositivo"]["nombre"] == "Móvil de Ana"
    sid = r.json()["dispositivo"]["id"]
    assert ca.get("/api/avisos/ajustes").json()["push"]["dispositivos"][0]["id"] == sid
    assert cadm.get("/api/avisos/ajustes").json()["push"]["dispositivos"] == []
    assert cadm.delete(f"/api/push/suscripciones/{sid}").status_code == 404
    malo = n.sub() | {"endpoint": "https://atacante.example/x"}
    assert ca.post("/api/push/suscripciones", json={"suscripcion": malo}).status_code == 400
    assert ca.post("/api/push/suscripciones", json={"suscripcion": {"endpoint": EP, "keys": {"p256dh": "x", "auth": "y"}}}).status_code == 400
    assert ca.delete(f"/api/push/suscripciones/{sid}").status_code == 200 and push.listar(ana["id"]) == []


def test_mismo_navegador_cambia_de_usuario(admin, ana):
    n = Navegador()
    push.suscribir(admin["id"], n.sub(), "PC")
    push.suscribir(ana["id"], n.sub(), "PC")
    assert push.listar(admin["id"]) == [] and len(push.listar(ana["id"])) == 1


def test_limite_de_dispositivos(ana):
    for i in range(push.MAX_SUSCRIPCIONES):
        push.suscribir(ana["id"], Navegador(f"{EP}{i}").sub(), str(i))
    with pytest.raises(push.PushError):
        push.suscribir(ana["id"], Navegador(EP + "x").sub(), "uno más")


def test_envio_y_poda_de_caducadas(ana, monkeypatch):
    vivo, muerto = Navegador(EP + "vivo"), Navegador(EP + "muerto")
    push.suscribir(ana["id"], vivo.sub(), "vivo")
    push.suscribir(ana["id"], muerto.sub(), "muerto")
    recibidos = []

    async def enviador(ep, cab, cuerpo):
        assert cab["Content-Encoding"] == "aes128gcm" and cab["Authorization"].startswith("vapid t=")
        if ep.endswith("muerto"):
            return 410
        recibidos.append(json.loads(vivo.descifrar(cuerpo)))
        return 201
    monkeypatch.setattr(push, "enviador", enviador)
    r = correr(push.enviar(ana["id"], "ARIA", "Hola", "/#ajustes"))
    assert r == {"enviados": 1, "borrados": 1, "fallidos": 0}
    assert recibidos == [{"titulo": "ARIA", "cuerpo": "Hola", "url": "/#ajustes", "etiqueta": "aria"}]
    assert [d["nombre"] for d in push.listar(ana["id"])] == ["vivo"] and push.listar(ana["id"])[0]["ultimo_envio"]
    # una URL externa en el mensaje se cambia por la raíz
    correr(push.enviar(ana["id"], "x", "y", "https://evil.com"))
    assert recibidos[-1]["url"] == "/"


def test_canal_push_del_motor_de_avisos(admin, monkeypatch):
    n = Navegador()
    push.suscribir(admin["id"], n.sub(), "PC")
    llegados = []

    async def enviador(ep, cab, cuerpo):
        llegados.append((cab["Urgency"], json.loads(n.descifrar(cuerpo))))
        return 201
    monkeypatch.setattr(push, "enviador", enviador)
    monkeypatch.setattr(avisos, "_CANALES", {"push": push.canal})
    monkeypatch.setattr(avisos, "en_silencio", lambda a, ref=None: False)
    r = correr(avisos.emitir("servicios", "grave", "SHIELD-DNS caído", "control"))
    assert r[0]["canales"] == ["push"]
    assert llegados[0] == ("high", {"titulo": "ARIA · Importante", "cuerpo": "SHIELD-DNS caído", "url": "/#control",
                                    "etiqueta": "aria-servicios"})
    avisos.guardar_ajustes(admin["id"], {"canales": {"push": False}})
    assert correr(avisos.emitir("servicios", "grave", "otra vez"))[0]["canales"] == []


def test_prueba_push_por_api(ana, monkeypatch):
    async def enviador(ep, cab, cuerpo):
        return 201
    monkeypatch.setattr(push, "enviador", enviador)
    push.suscribir(ana["id"], Navegador().sub(), "PC")
    assert cliente_de(ana).post("/api/push/prueba").json()["enviados"] == 1


def test_push_requiere_sesion_y_origen():
    c = TestClient(main.app, base_url=LAN, follow_redirects=False)
    assert c.post("/api/push/suscripciones", json={}).status_code == 401
    assert c.post("/api/push/prueba").status_code == 401


def test_push_rechaza_otro_origen(ana):
    r = cliente_de(ana).post("/api/push/suscripciones", json={"suscripcion": Navegador().sub()},
                             headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_service_worker():
    c = TestClient(main.app, base_url=LAN)
    r = c.get("/sw.js")
    assert r.status_code == 200 and r.headers["service-worker-allowed"] == "/"
    assert r.headers["content-type"].startswith("text/javascript")
    assert "__VERSION__" not in r.text and main._VERSION_ESTATICOS in r.text
    assert "caches" not in r.text and "fetch" not in r.text.replace("// ", "")  # sin caché sin conexión
    assert "worker-src 'self'" in r.headers["content-security-policy"]
