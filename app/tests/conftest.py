import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
# Las pruebas cubren también Spotify y Netflix, aunque en producción estén aparcados.
os.environ.setdefault("ARIA_SPOTIFY", "1")
os.environ.setdefault("ARIA_NETFLIX", "1")
# Módulos: main.py carga los de prueba (uno bueno y uno roto), no los del repositorio.
os.environ["ARIA_MODULOS_DIR"] = str(Path(__file__).resolve().parent / "modulos_prueba")
os.environ.pop("ARIA_MODULOS", None)
import pytest

from aria import agenda, auth, avisos, cerebros, config, control, cve, db, finanzas, push, recordatorios, red, sso, telegram, usuarios


@pytest.fixture(autouse=True)
def entorno(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "AUTH_FILE", tmp_path / "auth.json")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "USER", "admin")
    monkeypatch.setattr(config, "PASSWORD", "contraseña-del-env")
    monkeypatch.setattr(config, "SECRET", "x" * 40)
    monkeypatch.setattr(config, "ADMIN_EMAILS", [])
    monkeypatch.setattr(config, "CF_TEAM", "")
    monkeypatch.setattr(config, "CF_AUD", "")
    monkeypatch.setattr(config, "HOSTS", {"192.168.1.50", "aria.local"})
    monkeypatch.setattr(auth, "_ser", auth.URLSafeTimedSerializer("x" * 40, salt="aria-session"))
    monkeypatch.setattr(auth, "_fallos", {})
    monkeypatch.setattr(sso, "_claves", {})
    monkeypatch.setattr(sso, "_descargada", 0.0)
    monkeypatch.setattr(sso, "_intento", 0.0)
    monkeypatch.setattr(config, "ESCANER_DIR", tmp_path / "escaner")
    db.iniciar()
    usuarios.iniciar()
    finanzas.iniciar()
    red.iniciar()
    control.iniciar()
    monkeypatch.setattr(control, "_ult_refresco", 0.0)
    cve.iniciar()
    avisos.iniciar()
    recordatorios.iniciar()
    agenda.iniciar()
    push.iniciar()
    telegram.iniciar()
    monkeypatch.setattr(push, "_claves", {})
