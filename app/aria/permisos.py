"""Permisos por rol. Todo lo que no está en la lista blanca de `usuario` es solo para `admin` (denegar por defecto)."""
import re

# (método, patrón de ruta completo). Un `usuario` solo puede llamar a esto.
_USUARIO = [
    ("GET", r"/"),
    ("POST", r"/logout"),
    ("GET", r"/static/.*"),
    ("GET", r"/api/info"),
    ("GET", r"/api/services"),
    ("GET", r"/api/shield"),
    ("GET", r"/api/system"),
    ("GET", r"/api/vpn/clients"),
    ("GET", r"/api/spotify/status"),
    ("GET", r"/api/certificado"),
    ("POST", r"/api/password"),
    ("POST", r"/api/chat"),
    ("GET", r"/api/conversations"),
    ("GET", r"/api/conversations/[^/]+"),
    ("PATCH", r"/api/conversations/[^/]+"),
    ("DELETE", r"/api/conversations/[^/]+"),
    # Agentes: la lista ya viene filtrada por rol; el chat rechaza @seguridad a un usuario.
    ("GET", r"/api/agentes"),
    # Finanzas: cada usuario solo sus datos (las funciones filtran por user_id de la sesión).
    ("GET", r"/api/finanzas/(resumen|movimientos|reglas)"),
    ("POST", r"/api/finanzas/(movimientos|presupuestos|reglas|importar|importar/previa|sugerir)"),
    ("PATCH", r"/api/finanzas/movimientos/\d+"),
    ("DELETE", r"/api/finanzas/(movimientos|reglas)/\d+"),
    # Red: solo la salud (latencia ya medida, DNS, VPN y la última velocidad). Dispositivos, mediciones
    # nuevas y todo Seguridad son solo de admin.
    ("GET", r"/api/red/salud"),
]
_PATRONES = [(m, re.compile(p)) for m, p in _USUARIO]


def permitido(rol: str, metodo: str, ruta: str) -> bool:
    if rol == "admin":
        return True
    if rol != "usuario":
        return False
    metodo = "GET" if metodo == "HEAD" else metodo
    return any(m == metodo and p.fullmatch(ruta) for m, p in _PATRONES)
