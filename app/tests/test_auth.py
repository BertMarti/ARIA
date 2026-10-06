import pytest

from aria import auth, config


@pytest.fixture(autouse=True)
def entorno(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "AUTH_FILE", tmp_path / "auth.json")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "USER", "admin")
    monkeypatch.setattr(config, "PASSWORD", "contraseña-del-env")
    monkeypatch.setattr(config, "SECRET", "x" * 40)
    monkeypatch.setattr(auth, "_ser", auth.URLSafeTimedSerializer("x" * 40, salt="aria-session"))


def test_hash_verifica_y_rechaza():
    h = auth.hashear("clave-muy-larga-1")
    assert h.startswith("scrypt$") and "clave-muy-larga-1" not in h
    assert auth.verificar_hash("clave-muy-larga-1", h)
    assert not auth.verificar_hash("otra", h)
    assert not auth.verificar_hash("x", "basura") and not auth.verificar_hash("x", "md5$1$2$3$4$5")


def test_sal_distinta_cada_vez():
    assert auth.hashear("abc") != auth.hashear("abc")


def test_env_por_defecto():
    assert auth.credenciales_ok("admin", "contraseña-del-env")
    assert not auth.credenciales_ok("admin", "mal")
    assert not auth.credenciales_ok("otro", "contraseña-del-env")


def test_cambio_de_password_y_prioridad():
    assert auth.cambiar_password("contraseña-del-env", "nueva-clave-123", "nueva-clave-123") is None
    assert auth.credenciales_ok("admin", "nueva-clave-123")
    assert not auth.credenciales_ok("admin", "contraseña-del-env")  # el hash manda sobre el .env
    assert oct(auth.AUTH_FILE.stat().st_mode & 0o777) == "0o600"


@pytest.mark.parametrize("actual,nueva,rep", [
    ("mala", "nueva-clave-123", "nueva-clave-123"),
    ("contraseña-del-env", "corta", "corta"),
    ("contraseña-del-env", "nueva-clave-123", "distinta-clave-1"),
    ("contraseña-del-env", "contraseña-del-env", "contraseña-del-env"),
])
def test_cambio_rechazado(actual, nueva, rep):
    assert auth.cambiar_password(actual, nueva, rep)
    assert not auth.AUTH_FILE.exists()


def test_cambio_invalida_otras_sesiones():
    t = auth.crear_sesion()
    assert auth.sesion_valida(t)
    auth.cambiar_password("contraseña-del-env", "nueva-clave-123", "nueva-clave-123")
    assert not auth.sesion_valida(t)
    assert auth.sesion_valida(auth.crear_sesion())
