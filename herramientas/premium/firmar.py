#!/usr/bin/env python3
"""Firma una licencia Premium para una instalación."""
import argparse
import base64
import json
from datetime import date, timedelta
from pathlib import Path

from cryptography.hazmat.primitives import serialization


def b64(datos):
    return base64.urlsafe_b64encode(datos).rstrip(b"=").decode()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--clave", required=True, type=Path)
    p.add_argument("--id", required=True)
    p.add_argument("--dias", required=True, type=int)
    p.add_argument("--instalacion")
    args = p.parse_args()
    if args.dias < 1:
        p.error("--dias debe ser positivo")
    clave = serialization.load_pem_private_key(args.clave.read_bytes(), password=None)
    hoy = date.today()
    payload = {"v": 1, "id": args.id, "plan": "premium", "emitida": hoy.isoformat(),
               "caduca": (hoy + timedelta(days=args.dias - 1)).isoformat(), "instalacion": args.instalacion}
    crudo = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    print(b64(crudo) + "." + b64(clave.sign(crudo)))


if __name__ == "__main__":
    main()
