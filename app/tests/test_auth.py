import pytest

from aria import auth, usuarios


def _admin():
    return usuarios.por_identificador("admin")


def test_hash_verifica_y_rechaza():
    h = auth.hashear("clave-muy-larga-1")
    assert h.startswith("scrypt$") and "clave-muy-larga-1" not in h
    assert auth.verificar_hash("clave-muy-larga-1", h)
    assert not auth.verificar_hash("otra", h)
    assert not auth.verificar_hash("x", "basura") and not auth.verificar_hash("x", "md5$1$2$3$4$5")


def test_sal_distinta_cada_vez():
    assert auth.hashear("abc") != auth.hashear("abc")


def test_env_por_defecto():
    assert usuarios.autenticar("admin", "contraseña-del-env")
    assert usuarios.autenticar("ADMIN", "contraseña-del-env")
    assert not usuarios.autenticar("admin", "mal")
    assert not usuarios.autenticar("otro", "contraseña-del-env")


def test_login_por_email_o_usuario():
    usuarios.crear("ana@example.com", "Ana", "usuario", "clave-larga-ana")
    assert usuarios.autenticar("ana@example.com", "clave-larga-ana")["nombre"] == "Ana"
    assert usuarios.autenticar("ANA@example.com", "clave-larga-ana")
    assert not usuarios.autenticar("ana@example.com", "otra-clave-larga")


def test_sin_password_no_entra_por_la_lan():
    usuarios.crear("sso@example.com", "Solo SSO", "usuario")
    assert not usuarios.autenticar("sso@example.com", "")
    assert not usuarios.autenticar("sso@example.com", "contraseña-del-env")


def test_cambio_de_password_y_prioridad():
    assert usuarios.cambiar_password(_admin()["id"], "contraseña-del-env", "nueva-clave-123", "nueva-clave-123") is None
    assert usuarios.autenticar("admin", "nueva-clave-123")
    assert not usuarios.autenticar("admin", "contraseña-del-env")  # el hash manda sobre el .env


@pytest.mark.parametrize("actual,nueva,rep", [
    ("mala", "nueva-clave-123", "nueva-clave-123"),
    ("contraseña-del-env", "corta", "corta"),
    ("contraseña-del-env", "nueva-clave-123", "distinta-clave-1"),
    ("contraseña-del-env", "contraseña-del-env", "contraseña-del-env"),
])
def test_cambio_rechazado(actual, nueva, rep):
    assert usuarios.cambiar_password(_admin()["id"], actual, nueva, rep)
    assert usuarios.autenticar("admin", "contraseña-del-env")


def test_cambio_invalida_otras_sesiones():
    t = auth.crear_sesion(_admin())
    assert auth.sesion_usuario(t)
    usuarios.cambiar_password(_admin()["id"], "contraseña-del-env", "nueva-clave-123", "nueva-clave-123")
    assert not auth.sesion_usuario(t)
    assert auth.sesion_usuario(auth.crear_sesion(_admin()))


def test_desactivar_mata_la_sesion():
    u = usuarios.crear("ana@example.com", "Ana", "usuario", "clave-larga-ana")
    t = auth.crear_sesion(u)
    assert auth.sesion_usuario(t)["id"] == u["id"]
    usuarios.actualizar(u["id"], activo=False)
    assert auth.sesion_usuario(t) is None
    usuarios.actualizar(u["id"], activo=True)
    assert auth.sesion_usuario(t) is None  # reactivar tampoco resucita la sesión antigua


def test_cookie_antigua_del_admin_unico_sigue_valiendo():
    t = auth._ser.dumps({"u": "admin", "v": 1})
    assert auth.sesion_usuario(t)["usuario"] == "admin"
    usuarios.cambiar_password(_admin()["id"], "contraseña-del-env", "nueva-clave-123", "nueva-clave-123")
    assert auth.sesion_usuario(t) is None


def test_cookie_manipulada():
    assert auth.sesion_usuario("basura") is None and auth.sesion_usuario(None) is None
    assert auth.sesion_usuario(auth._ser.dumps({"u": 9999, "v": 1})) is None
