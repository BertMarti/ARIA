"""Briefing hablado: el resumen del día contado por ARIA en un minuto, con su voz.

`guion(d)` convierte el resumen diario (`resumen_diario.construir_resumen_diario`) en un texto para escuchar, sin
cifras «de ahora» que cambian cada pocos minutos. El guion se fija una vez por usuario, día y franja (mañana, tarde
o noche) y su audio se guarda en disco: así cada briefing gasta como mucho un par de peticiones a la cuota de voz
de Gemini, aunque se escuche diez veces. Si Gemini no está disponible, se usa la voz local (Piper) sin guardarla,
para volver a intentarlo con la voz elegida más tarde.
"""
import asyncio
import hashlib
import io
import json
import logging
import time
import wave
from datetime import date

import httpx

from . import config, invitados, resumen_diario, tiempo, voz

log = logging.getLogger("aria.briefing_voz")

RETENCION_DIAS = 3
MAX_GUION = 1150          # ~1 minuto de voz
_LOCAL_S = 1800           # audio con la voz local: en memoria 30 min y luego se reintenta con Gemini
_memoria: dict = {}       # clave -> (instante, wav, motor)
_bloqueos: dict = {}      # clave -> asyncio.Lock (dos peticiones a la vez no sintetizan dos veces)


def _dir():
    d = config.DATA_DIR / "briefing-voz"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _num(n, dec: int = 0) -> str:
    return f"{n:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _franja(ref=None) -> str:
    h = (ref or tiempo.ahora()).hour
    return "manana" if 6 <= h < 13 else "tarde" if 13 <= h < 21 else "noche"


def _hora(iso) -> str:
    s = str(iso or "")[11:16]
    return s.lstrip("0") if s[:2] != "00" else s


def _lista(cosas: list[str]) -> str:
    return cosas[0] if len(cosas) == 1 else ", ".join(cosas[:-1]) + " y " + cosas[-1]


def guion(d: dict, hoy: date | None = None) -> str:
    """Texto hablado del resumen. Solo usa lo que el resumen ya filtra por rol (casa y red: administradores)."""
    hoy = hoy or tiempo.hoy()
    p = [f"{d.get('saludo') or tiempo.saludo_horario()}. Hoy es {d.get('fecha_texto') or ''}.".replace(" .", ".")]
    t = d.get("tiempo")
    if t:
        x = f"En {t['ciudad']}, {t['cielo']}, entre {t['min']} y {t['max']} grados."
        if (t.get("lluvia") or 0) >= 40:
            x += f" Hay un {t['lluvia']} % de probabilidad de lluvia: mejor llevar paraguas."
        if t.get("aviso_manana"):
            x += " " + t["aviso_manana"].replace("–", " a ").replace("°C", "grados")
        p.append(x)
    lz = d.get("luz")
    if lz and lz.get("barata") and lz.get("cara"):
        p.append(f"La luz estará más barata a las {lz['barata']['hora']} y más cara a las {lz['cara']['hora']}.")
    ag = d.get("agenda") or {}
    cosas = [(e.get("inicio") or "", ("todo el día, " if e.get("todo_el_dia") else f"a las {_hora(e.get('inicio'))}, ") + str(e.get("titulo")))
             for e in ag.get("eventos", [])]
    cosas += [(r.get("cuando") or "", f"a las {_hora(r.get('cuando'))}, {r.get('texto')}") for r in d.get("recordatorios", [])]
    cosas.sort(key=lambda c: (not c[1].startswith("todo"), c[0]))
    if cosas:
        n = len(cosas)
        p.append(("Tienes una cosa en la agenda: " if n == 1 else f"Tienes {n} cosas en la agenda: ") + _lista([c[1] for c in cosas[:5]]) + ".")
    else:
        p.append("Tu agenda está despejada.")
    cumple_hoy = [c for c in ag.get("cumpleanos", []) if c.get("fecha") == hoy.isoformat()]
    if cumple_hoy:
        p.append("Y no te olvides: hoy es el cumpleaños de " + _lista([str(c["nombre"]) for c in cumple_hoy]) + ".")
    a = d.get("aplicaciones")
    if a:
        problemas = a.get("problemas") or []
        if problemas:
            p.append("En casa hay que revisar " + ("una cosa: " if len(problemas) == 1 else f"{len(problemas)} cosas: ") + _lista(problemas[:3]) + ".")
        else:
            x = "En casa, todo en orden"
            if a.get("shield") and a["shield"].get("bloqueadas"):
                x += f", y Ping lleva {_num(a['shield']['bloqueadas'])} anuncios atrapados"
            p.append(x + ".")
    r = d.get("red")
    if r:
        if r.get("nuevos"):
            p.append(f"Han entrado {len(r['nuevos'])} dispositivos nuevos en la red." if len(r["nuevos"]) > 1 else "Ha entrado un dispositivo nuevo en la red.")
        elif r.get("n_desconocidos"):
            p.append(f"Hay {r['n_desconocidos']} dispositivos sin identificar en la red." if r["n_desconocidos"] > 1 else "Hay un dispositivo sin identificar en la red.")
    f = d.get("finanzas")
    if f and f.get("gastos"):
        x = f"Este mes llevas {_num(f['gastos'] / 100)} euros gastados"
        previo = f.get("mes_anterior_mismo_dia")
        if previo:
            dif = round((f["gastos"] - previo) * 100 / previo)
            if abs(dif) >= 5:
                x += f", un {abs(dif)} % {'más' if dif > 0 else 'menos'} que el mes pasado a estas alturas"
        p.append(x + ".")
        pasados = [b.get("categoria") for b in f.get("presupuestos") or [] if b.get("superado")]
        if pasados:
            p.append("Ojo: te has pasado del presupuesto en " + _lista([str(c) for c in pasados[:3]]) + ".")
    inv = (d.get("inversiones") or {}).get("valores") or []
    movidos = sorted((v for v in inv if v.get("variacion_dia") is not None), key=lambda v: -abs(v["variacion_dia"]))
    if movidos and abs(movidos[0]["variacion_dia"]) >= 0.5:
        v = movidos[0]
        p.append(f"En los mercados, lo que más se mueve es {v.get('nombre') or v.get('simbolo')}: "
                 f"{'sube' if v['variacion_dia'] > 0 else 'baja'} un {_num(abs(v['variacion_dia']), 1)} %.")
    if d.get("cierre"):
        p.append(d["cierre"])
    texto = " ".join(x.strip() for x in p if x and x.strip())
    if len(texto) > MAX_GUION:   # se recorta por frases enteras, nunca a mitad
        corte = texto.rfind(". ", 0, MAX_GUION)
        texto = texto[:corte + 1] if corte > 0 else texto[:MAX_GUION]
    return texto


def _prefs_clave(uid: int) -> tuple[dict, str]:
    pref = voz.preferencias_de(uid)
    return pref, f"{pref['voz']}-{pref['tono']}-{pref['acento']}"


def _base(usuario: dict, limites: dict | None = None, ref=None) -> str:
    """Por usuario, rol y perfil (el guion de un admin cuenta cosas de la casa; el de una visita, menos), día y franja."""
    perfil = (limites or {}).get("perfil", "")
    return f"{usuario['id']}-{usuario.get('rol', 'usuario')}{perfil}-{tiempo.hoy(ref).isoformat()}-{_franja(ref)}"


def purgar() -> int:
    limite, n = time.time() - RETENCION_DIAS * 86400, 0
    for f in _dir().glob("*"):
        try:
            if f.stat().st_mtime < limite:
                f.unlink()
                n += 1
        except OSError:
            pass
    return n


async def obtener_guion(usuario: dict, refrescar: bool = False, limites: dict | None = None) -> str:
    """El guion de esta franja del día: se fija la primera vez y se reutiliza (salvo `refrescar`)."""
    ruta = _dir() / (_base(usuario, limites) + ".json")
    if not refrescar and ruta.is_file():
        try:
            return json.loads(ruta.read_text())["guion"]
        except (OSError, ValueError, KeyError):
            pass
    d = await resumen_diario.construir_resumen_diario(usuario, refrescar=refrescar)
    texto = guion(invitados.recortar_resumen(d, limites))
    await asyncio.to_thread(ruta.write_text, json.dumps({"guion": texto, "generado": time.time()}, ensure_ascii=False))
    return texto


def _unir(wavs: list[bytes]) -> bytes:
    """Concatena WAV PCM con el mismo formato (lo están: salen todos del mismo motor)."""
    if len(wavs) == 1:
        return wavs[0]
    out = io.BytesIO()
    with wave.open(io.BytesIO(wavs[0])) as w0:
        params = w0.getparams()
    with wave.open(out, "wb") as w:
        w.setparams(params)
        for b in wavs:
            with wave.open(io.BytesIO(b)) as r:
                w.writeframes(r.readframes(r.getnframes()))
                w.writeframes(b"\0\0" * int(params.framerate * 0.25 * params.nchannels))   # respiro entre trozos
    return out.getvalue()


def _trozos(texto: str, maximo: int = voz.MAX_TTS) -> list[str]:
    frases, out, act = texto.replace(": ", ": \u0000").replace(". ", ". \u0000").split("\u0000"), [], ""
    for f in frases:
        if len(act) + len(f) > maximo and act:
            out.append(act.strip())
            act = ""
        act += f
    if act.strip():
        out.append(act.strip())
    return out


async def _sintetizar(texto: str, pref: dict) -> tuple[bytes, str]:
    trozos = _trozos(texto)
    wavs, motores = [], set()
    for t in trozos:
        wav, motor = await voz.sintetizar_info(t, 1.0, pref)
        wavs.append(wav)
        motores.add(motor)
    if len(motores) > 1:   # un trozo con Gemini y otro con la voz local: mejor todo con la local, que suena igual
        wavs = [await voz.sintetizar_local(t, 1.0) for t in trozos]
        motores = {"local"}
    return _unir(wavs), motores.pop()


async def audio(usuario: dict, refrescar: bool = False, limites: dict | None = None) -> tuple[bytes, str, str]:
    """(wav, motor, guion) del briefing de esta franja del día."""
    uid = usuario["id"]
    texto = await obtener_guion(usuario, refrescar, limites)
    pref, voz_clave = await asyncio.to_thread(_prefs_clave, uid)
    huella = hashlib.sha256((texto + voz_clave).encode()).hexdigest()[:12]
    clave = f"{_base(usuario, limites)}-{huella}"
    ruta = _dir() / f"{clave}.wav"
    async with _bloqueos.setdefault(clave, asyncio.Lock()):
        if ruta.is_file():
            return await asyncio.to_thread(ruta.read_bytes), "guardado", texto
        m = _memoria.get(clave)
        if m and time.time() - m[0] < _LOCAL_S:
            return m[1], m[2], texto
        wav, motor = await _sintetizar(texto, pref)
        if motor == "local":
            _memoria[clave] = (time.time(), wav, motor)
        else:
            await asyncio.to_thread(ruta.write_bytes, wav)
            await asyncio.to_thread(purgar)
    _bloqueos.pop(clave, None)
    return wav, motor, texto


async def ogg(wav: bytes) -> tuple[bytes, str]:
    """Para Telegram: OGG/Opus (nota de voz) convertido en aria-voz; si no se puede, el WAV tal cual."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=5)) as c:
            r = await c.post(f"{voz.VOZ_URL}/ogg", content=wav, headers={"Content-Type": "audio/wav"})
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("audio/ogg"):
            return r.content, "audio/ogg"
    except httpx.HTTPError:
        log.warning("aria-voz no convierte a OGG: el briefing va como archivo WAV")
    return wav, "audio/wav"
