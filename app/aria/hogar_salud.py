"""Salud de las cámaras: avisa si a una le queda poca batería o si deja de responder un buen rato.

Se alimenta de la lista que el precalentado de Hogar ya pide cada 10 minutos (no despierta a ninguna cámara de más).
Cada aviso sale una vez y se rearma cuando la cámara se recupera (batería ≥ 30 % o vuelve a responder).
"""
import logging

from . import avisos

log = logging.getLogger("aria.hogar")
BATERIA_BAJA = 20
BATERIA_RECUPERADA = 30
VUELTAS_SIN_RESPUESTA = 3   # 3 vueltas de 10 min: media hora sin contestar

_nombres: dict = {}
_sin_respuesta: dict = {}
_avisado: set = set()   # {(ip, "bateria" | "caida")}


async def revisar(filas: list) -> list:
    """Compara la última lista de cámaras con lo que ya se sabía. Devuelve los textos avisados (para las pruebas)."""
    textos = []
    for c in filas or []:
        ip = c.get("ip")
        if not ip:
            continue
        if c.get("en_linea"):
            if c.get("nombre") and c["nombre"] != ip:
                _nombres[ip] = c["nombre"]
            nombre = _nombres.get(ip, "una cámara")
            if (ip, "caida") in _avisado:
                _avisado.discard((ip, "caida"))
                textos.append(f"La cámara «{nombre}» vuelve a responder.")
            _sin_respuesta[ip] = 0
            bateria = c.get("bateria")
            if isinstance(bateria, int):
                if bateria <= BATERIA_BAJA and (ip, "bateria") not in _avisado:
                    _avisado.add((ip, "bateria"))
                    textos.append(f"A la cámara «{nombre}» le queda un {bateria} % de batería: cárgala pronto.")
                elif bateria >= BATERIA_RECUPERADA:
                    _avisado.discard((ip, "bateria"))
        else:
            _sin_respuesta[ip] = _sin_respuesta.get(ip, 0) + 1
            if _sin_respuesta[ip] >= VUELTAS_SIN_RESPUESTA and (ip, "caida") not in _avisado:
                _avisado.add((ip, "caida"))
                textos.append(f"La cámara «{_nombres.get(ip, 'una cámara')}» lleva más de media hora sin responder "
                              "(¿sin batería, sin wifi o desenchufada?).")
    for texto in textos:
        try:
            await avisos.emitir("camaras", "aviso", texto, "hogar")
        except Exception:  # noqa: BLE001
            log.warning("No se pudo enviar un aviso de cámaras")
    return textos
