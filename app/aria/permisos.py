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
    # Memoria y resumen de buenos días: cada usuario solo ve y cambia lo suyo (se filtra por sesión).
    ("GET", r"/api/memoria"),
    ("POST", r"/api/memoria"),
    ("POST", r"/api/memoria/ajustes"),
    ("PATCH", r"/api/memoria/\d+"),
    ("DELETE", r"/api/memoria/\d+"),
    ("DELETE", r"/api/memoria"),
    ("DELETE", r"/api/diario/\d{4}-\d{2}-\d{2}"),
    ("GET", r"/api/briefing"),
]
_PATRONES = [(m, re.compile(p)) for m, p in _USUARIO]


def permitido(rol: str, metodo: str, ruta: str) -> bool:
    if rol == "admin":
        return True
    if rol != "usuario":
        return False
    metodo = "GET" if metodo == "HEAD" else metodo
    return any(m == metodo and p.fullmatch(ruta) for m, p in _PATRONES)
