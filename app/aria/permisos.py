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
    ("POST", r"/api/chat"),  # también con imagen (visión); límite por usuario en el propio endpoint
    # Tickets leídos de una foto: confirmar o descartar la propuesta propia (ligada al usuario en el servidor).
    ("POST", r"/api/vision/tickets/[A-Za-z0-9_-]{16,64}"),
    ("DELETE", r"/api/vision/tickets/[A-Za-z0-9_-]{16,64}"),
    ("GET", r"/api/conversations"),
    ("GET", r"/api/conversations/[^/]+"),
    ("PATCH", r"/api/conversations/[^/]+"),
    ("DELETE", r"/api/conversations/[^/]+"),
    ("GET", r"/api/voz/estado"),
    ("POST", r"/api/voz/transcribir"),
    ("POST", r"/api/voz/hablar"),
    ("GET", r"/api/voz/despertar"),  # WebSocket (se comprueba en el propio endpoint)
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
    # Memoria y resumen de buenos días: cada usuario solo ve y cambia lo suyo (se filtra por sesión).
    ("GET", r"/api/memoria"),
    ("POST", r"/api/memoria"),
    ("POST", r"/api/memoria/ajustes"),
    ("PATCH", r"/api/memoria/\d+"),
    ("DELETE", r"/api/memoria/\d+"),
    ("DELETE", r"/api/memoria"),
    ("DELETE", r"/api/diario/\d{4}-\d{2}-\d{2}"),
    ("GET", r"/api/briefing"),
    # Avisos, recordatorios, Telegram y push: cada usuario solo lo suyo (el id sale de la sesión).
    ("GET", r"/api/avisos"),
    ("POST", r"/api/avisos/leidos"),
    ("POST", r"/api/avisos/\d+/leido"),
    ("GET", r"/api/avisos/ajustes"),
    ("POST", r"/api/avisos/ajustes"),
    ("POST", r"/api/avisos/probar"),
    ("GET", r"/api/recordatorios"),
    ("POST", r"/api/recordatorios"),
    ("DELETE", r"/api/recordatorios/\d+"),
    ("POST", r"/api/telegram/vincular"),
    ("DELETE", r"/api/telegram/chats/\d+"),
    ("POST", r"/api/push/suscripciones"),
    ("DELETE", r"/api/push/suscripciones/\d+"),
    ("POST", r"/api/push/prueba"),
]
_PATRONES = [(m, re.compile(p)) for m, p in _USUARIO]


def permitido(rol: str, metodo: str, ruta: str) -> bool:
    if rol == "admin":
        return True
    if rol != "usuario":
        return False
    metodo = "GET" if metodo == "HEAD" else metodo
    return any(m == metodo and p.fullmatch(ruta) for m, p in _PATRONES)

# Control parental (api_control.py): TODAS sus rutas /api/red/control/... son solo de admin. No están en la lista
# blanca de `usuario` y `test_permisos.py` comprueba una a una que un `usuario` recibe 403.
