#!/usr/bin/env python3
"""Genera el par Ed25519 usado para firmar licencias de ARIA."""
import argparse
import base64
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--salida", required=True, type=Path)
    args = p.parse_args()
    args.salida.mkdir(parents=True, exist_ok=True, mode=0o700)
    if (args.salida / "privada.pem").exists():
        p.error("Ya hay una clave privada ahí: si la sustituyes, ninguna licencia emitida seguirá valiendo.")
    clave = Ed25519PrivateKey.generate()
    privada = clave.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                  serialization.NoEncryption())
    publica = clave.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    fd = os.open(args.salida / "privada.pem", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)   # nunca legible por otros
    with os.fdopen(fd, "wb") as f:
        f.write(privada)
    (args.salida / "publica.b64").write_text(base64.b64encode(publica).decode() + "\n")
    print(f"Claves creadas en {args.salida}. La privada NUNCA debe ir a git.")


if __name__ == "__main__":
    main()
