import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pytest

from aria import auth, avisos, cerebros, config, cve, db, finanzas, push, recordatorios, red, sso, telegram, usuarios


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
    cve.iniciar()
    avisos.iniciar()
    recordatorios.iniciar()
    push.iniciar()
    telegram.iniciar()
    monkeypatch.setattr(push, "_claves", {})
