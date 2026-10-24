"""Protocolo RUNA v1 en Python: el mismo cifrado que la web de RUNA (apps/web/src/crypto en
https://github.com/BertMarti/runa), para que ARIA cree enlaces que se abren en cualquier navegador.

    K      = 32 bytes aleatorios            → solo viajan en el fragmento «#» del enlace
    salt   = HKDF(K, "runa/v1/salt")[:16]
    P      = PBKDF2-SHA256(NFC(contraseña), salt, 600 000)      (solo si hay contraseña)
    kEnc   = HKDF(K ‖ P, salt, "runa/v1/enc")   → AES-256-GCM
    token  = HKDF(K ‖ P, salt, "runa/v1/auth")  → prueba de contraseña
    link   = HKDF(K,     salt, "runa/v1/link")  → prueba de enlace

Al servidor de RUNA solo llegan el cifrado y SHA-256(token) / SHA-256(link): nunca K, la contraseña ni el texto.
Usa `cryptography`, que ya está en la imagen de ARIA (llega con PyJWT[crypto]).
"""
import base64
import hashlib
import json
import os
import re
import struct
import unicodedata

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

VERSION = "v1"
LONG_CLAVE = 32
LONG_SALT = 16
LONG_IV = 12
ITERACIONES_PBKDF2 = 600_000
# Bloques de relleno: el tamaño cifrado solo revela en cuál cae el secreto.
BLOQUES = [k * 1024 for k in (1, 4, 16, 64, 256, 1024, 4096)]
MAX_TEXTO = 100_000
MAX_ARCHIVO = 3 * 1024 * 1024
_FRAGMENTO = re.compile(r"^v1\.([A-Za-z0-9_-]{43})(\.p)?$")


class ProtocoloError(Exception):
    pass


def b64url(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).rstrip(b"=").decode("ascii")


def desde_b64url(texto: str) -> bytes:
    if not re.fullmatch(r"[A-Za-z0-9_-]*", texto) or len(texto) % 4 == 1:
        raise ProtocoloError("base64url no válido")
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def _hkdf(ikm: bytes, salt: bytes, info: str, longitud: int) -> bytes:
    # Sal vacía = HashLen ceros (RFC 5869), igual que Web Crypto.
    return HKDF(algorithm=hashes.SHA256(), length=longitud, salt=salt, info=info.encode()).derive(ikm)


def _derivar(clave: bytes, contrasena: str | None) -> dict:
    if len(clave) != LONG_CLAVE:
        raise ProtocoloError("Clave no válida")
    salt = _hkdf(clave, b"", f"runa/{VERSION}/salt", LONG_SALT)
    ikm = clave
    if contrasena:
        p = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERACIONES_PBKDF2)
        ikm = clave + p.derive(unicodedata.normalize("NFC", contrasena).encode("utf-8"))
    return {
        "enc": _hkdf(ikm, salt, f"runa/{VERSION}/enc", 32),
        "token": _hkdf(ikm, salt, f"runa/{VERSION}/auth", 32),
        "link": _hkdf(clave, salt, f"runa/{VERSION}/link", 32),
    }


def _aad(con_contrasena: bool) -> bytes:
    return f"runa/{VERSION}|{'p' if con_contrasena else '-'}".encode()


def nombre_seguro(nombre: str) -> str:
    """Igual que safeFileName de la web: sin rutas, controles, bidi ni anchura cero."""
    base = re.split(r"[\\/]", nombre or "")[-1]
    base = re.sub(r'[\x00-\x1f\x7f<>:"|?*]', "_", base)
    base = re.sub("[​-‏‪-‮⁠-⁤⁦-⁩﻿]", "", base)
    base = re.sub(r"^[.\s]+|[.\s]+$", "", base)
    return (base or "archivo")[:200]


def empaquetar(texto: str, archivo: tuple[str, str, bytes] | None = None) -> bytes:
    """`u32 BE longitud cabecera | cabecera JSON | archivo | ceros` hasta el bloque siguiente."""
    if len(texto) > MAX_TEXTO:
        raise ProtocoloError("El texto supera el máximo")
    cabecera: dict = {"text": texto}
    datos = b""
    if archivo:
        nombre, tipo, datos = archivo
        if len(datos) > MAX_ARCHIVO:
            raise ProtocoloError("El archivo supera el máximo")
        tipo = tipo if re.fullmatch(r"[\w.+-]+/[\w.+-]+", tipo or "") and len(tipo) <= 100 else "application/octet-stream"
        cabecera["file"] = {"name": nombre_seguro(nombre), "type": tipo, "size": len(datos)}
    cab = json.dumps(cabecera, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    cuerpo = struct.pack(">I", len(cab)) + cab + datos
    bloque = next((b for b in BLOQUES if b >= len(cuerpo)), None)
    if bloque is None:
        raise ProtocoloError("El secreto supera el tamaño máximo")
    return cuerpo + bytes(bloque - len(cuerpo))


def desempaquetar(datos: bytes) -> dict:
    if len(datos) < 4 or len(datos) > BLOQUES[-1]:
        raise ProtocoloError("Formato no válido")
    (largo,) = struct.unpack(">I", datos[:4])
    if largo > len(datos) - 4:
        raise ProtocoloError("Formato no válido")
    cab = json.loads(datos[4:4 + largo].decode("utf-8"))
    if not isinstance(cab, dict) or not isinstance(cab.get("text"), str):
        raise ProtocoloError("Formato no válido")
    salida = {"text": cab["text"]}
    f = cab.get("file")
    if f:
        size = f.get("size") if isinstance(f, dict) else None
        if not isinstance(size, int) or not 0 <= size <= MAX_ARCHIVO or 4 + largo + size > len(datos):
            raise ProtocoloError("Formato no válido")
        inicio = 4 + largo
        salida["file"] = {"name": nombre_seguro(str(f.get("name", ""))), "type": str(f.get("type", "")),
                          "data": datos[inicio:inicio + size]}
    return salida


def sellar(texto: str, contrasena: str | None = None, archivo: tuple[str, str, bytes] | None = None) -> dict:
    """Cifra un secreto. Devuelve lo que se sube al servidor y el fragmento del enlace (que nunca se sube)."""
    clave = os.urandom(LONG_CLAVE)
    d = _derivar(clave, contrasena or None)
    iv = os.urandom(LONG_IV)
    cifrado = AESGCM(d["enc"]).encrypt(iv, empaquetar(texto, archivo), _aad(bool(contrasena)))
    return {
        "ciphertext": b64url(iv + cifrado),
        "verifier": hashlib.sha256(d["token"]).hexdigest(),
        "linkVerifier": hashlib.sha256(d["link"]).hexdigest(),
        "prueba": {"link": d["link"].hex(), "token": d["token"].hex()},
        "fragmento": f"{VERSION}.{b64url(clave)}" + (".p" if contrasena else ""),
    }


def leer_fragmento(fragmento: str) -> tuple[bytes, bool]:
    m = _FRAGMENTO.match(fragmento.lstrip("#"))
    if not m:
        raise ProtocoloError("Enlace incompleto")
    clave = desde_b64url(m.group(1))
    if len(clave) != LONG_CLAVE:
        raise ProtocoloError("Enlace incompleto")
    return clave, bool(m.group(2))


def prueba(fragmento: str, contrasena: str | None = None) -> dict:
    """Pruebas de acceso (hex) que pide el servidor para abrir o destruir."""
    clave, con = leer_fragmento(fragmento)
    if con != bool(contrasena):
        raise ProtocoloError("Contraseña requerida")
    d = _derivar(clave, contrasena or None)
    return {"link": d["link"].hex(), "token": d["token"].hex()}


def abrir(cifrado: str, fragmento: str, contrasena: str | None = None) -> dict:
    """Descifra lo que entrega el servidor. Lanza si se ha alterado o la clave no es la buena."""
    clave, con = leer_fragmento(fragmento)
    if con != bool(contrasena):
        raise ProtocoloError("Contraseña requerida")
    datos = desde_b64url(cifrado)
    if len(datos) <= LONG_IV + 16:
        raise ProtocoloError("Cifrado no válido")
    d = _derivar(clave, contrasena or None)
    try:
        plano = AESGCM(d["enc"]).decrypt(datos[:LONG_IV], datos[LONG_IV:], _aad(con))
    except Exception as e:
        raise ProtocoloError("No se pudo descifrar") from e
    return desempaquetar(plano)
