"""Exportación y eliminación de los datos personales de una cuenta."""
import io
import json
import zipfile
from contextlib import closing

from . import db, dispositivos_app, documentos, listas, usuarios


def _filas(con, tabla, uid):
    if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tabla,)).fetchone():
        return []
    return [dict(r) for r in con.execute(f"SELECT * FROM {tabla} WHERE user_id=? ORDER BY rowid", (uid,))]


def _json(valor):
    return json.dumps(valor, ensure_ascii=False, indent=2, default=str) + "\n"


def exportar(uid: int, perfil: dict) -> bytes:
    listas.iniciar()   # crea sus tablas si aún no existen (exportación de una cuenta que nunca usó listas)
    dispositivos_app.iniciar()
    with closing(db._con()) as con:
        convs = []
        for c in con.execute("SELECT * FROM conversaciones WHERE user_id=? ORDER BY creada, id", (uid,)):
            conv = dict(c)
            conv["mensajes"] = [dict(m) for m in con.execute(
                "SELECT * FROM mensajes WHERE conv_id=? ORDER BY id", (c["id"],))]
            convs.append(conv)
        apartados = {
            "perfil.json": {k: perfil.get(k) for k in ("nombre", "email", "rol", "creado")},
            "conversaciones.json": convs,
            "memoria.json": {"recuerdos": _filas(con, "recuerdos", uid), "diario": _filas(con, "diario", uid),
                              "ajustes": _filas(con, "memoria_ajustes", uid)},
            "notas.json": _filas(con, "notas", uid),
            "documentos.json": _filas(con, "documentos", uid),
            "listas.json": {"listas": [dict(r) for r in con.execute(
                                "SELECT * FROM listas WHERE propietario=? ORDER BY orden, id", (uid,))],
                            "items": [dict(r) for r in con.execute(
                                "SELECT i.* FROM lista_items i JOIN listas l ON l.id=i.lista_id WHERE i.autor=? ORDER BY i.creado", (uid,))]},
            "medios.json": _filas(con, "medios_progreso", uid),
            "agenda.json": {"eventos": _filas(con, "agenda_eventos", uid),
                            "cumpleanos": _filas(con, "agenda_cumpleanos", uid)},
            "recordatorios.json": _filas(con, "recordatorios", uid),
            "rutinas.json": _filas(con, "rutinas", uid),
            "finanzas.json": {t.removeprefix("fin_"): _filas(con, t, uid)
                              for t in ("fin_movimientos", "fin_categorias", "fin_presupuestos", "fin_reglas")},
            "propuestas.json": _filas(con, "propuestas", uid),
            "voz.json": _filas(con, "voz_preferencias", uid),
            "avisos.json": {"avisos": _filas(con, "avisos", uid), "ajustes": _filas(con, "avisos_ajustes", uid)},
            "ubicacion.json": _filas(con, "ubicaciones", uid),
            "dispositivos-app.json": [dict(r) for r in con.execute(
                "SELECT id, nombre, creado, ultimo_uso, caduca FROM app_dispositivos WHERE user_id=? ORDER BY rowid", (uid,))],
        }
    leeme = ("Exportación de tus datos de ARIA\n\n"
             "perfil.json: datos básicos de tu cuenta, sin contraseña ni secretos.\n"
             "conversaciones.json: tus conversaciones y mensajes.\n"
             "memoria.json: recuerdos, diario y preferencias de memoria.\n"
               "notas.json: tus notas personales.\n"
               "documentos.json: metadatos de tus documentos, sin los archivos originales.\n"
              "listas.json: tus listas propias y los artículos que añadiste.\n"
              "medios.json: tu progreso de reproducción, sin archivos multimedia.\n"
             "agenda.json: eventos y cumpleaños.\n"
             "recordatorios.json: tus recordatorios.\n"
             "rutinas.json: tus rutinas programadas.\n"
             "finanzas.json: movimientos, categorías, presupuestos y reglas.\n"
             "propuestas.json: propuestas de ARIA y su estado.\n"
             "voz.json: preferencias de voz.\n"
               "avisos.json: avisos y ajustes de avisos.\n\n"
               "dispositivos-app.json: móviles vinculados, sin tokens ni huellas.\n\n"
               "ubicacion.json: tu última ubicación temporal, si la has usado.\n\n"
             "La exportación no incluye contraseñas, secretos de dos pasos, tokens ni claves.\n")
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("LEEME.txt", leeme)
        for nombre, datos in apartados.items():
            z.writestr(nombre, _json(datos))
    return salida.getvalue()


def borrar(uid: int) -> None:
    """Elimina todas las filas personales antes de eliminar la cuenta."""
    u = usuarios.por_id(uid)
    if not u:
        raise usuarios.UsuarioError("Usuario no encontrado.")
    with closing(db._con()) as con, con:
        if u["protegido"]:
            raise usuarios.UsuarioError("Ese email figura en ARIA_ADMIN_EMAILS: no se puede eliminar.")
        if u["rol"] == "admin" and u["activo"] and con.execute(
                "SELECT COUNT(*) FROM usuarios WHERE rol='admin' AND activo=1").fetchone()[0] <= 1:
            raise usuarios.UsuarioError("No se puede eliminar al último administrador activo.")
        con.execute("DELETE FROM conversaciones WHERE user_id=?", (uid,))
        tablas = [r["name"] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for tabla in tablas:
            if tabla in ("usuarios", "conversaciones") or not tabla.replace("_", "").isalnum():
                continue
            columnas = {r["name"] for r in con.execute(f"PRAGMA table_info({tabla})")}
            if "user_id" in columnas:
                con.execute(f"DELETE FROM {tabla} WHERE user_id=?", (uid,))
        con.execute("DELETE FROM usuarios WHERE id=?", (uid,))
    documentos.borrar_archivos(uid)
