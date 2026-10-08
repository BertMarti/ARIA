"""Spotify y Netflix aparcados (ARIA_SPOTIFY=0 / ARIA_NETFLIX=0, lo normal en producción)."""
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

CODIGO = """
from aria import agentes, config, tools
nombres = set(tools._REGISTRO)
assert not any(n.startswith("spotify_") for n in nombres), nombres
assert "buscar_en_netflix" not in nombres
for p in (config.system_prompt(True), config.system_prompt(False, admin=False)):
    assert "Spotify" not in p and "Netflix" not in p, p
    assert "Raspberry Pi o buscar información" in p
print("ok")
"""


def test_sin_spotify_ni_netflix():
    env = {**os.environ, "ARIA_SPOTIFY": "0", "ARIA_NETFLIX": "0", "ARIA_DATA_DIR": "/tmp/aria-prueba-aparcados"}
    r = subprocess.run([sys.executable, "-c", CODIGO], cwd=RAIZ, env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and r.stdout.strip().endswith("ok"), r.stderr[-2000:]


def test_info_expone_funciones():
    from fastapi.testclient import TestClient
    from aria import auth, main, usuarios
    c = TestClient(main.app, base_url="https://192.168.1.50")
    c.cookies.set(auth.COOKIE, auth.crear_sesion(usuarios.por_identificador("admin")))
    assert c.get("/api/info").json()["funciones"] == {"spotify": True, "netflix": True}
