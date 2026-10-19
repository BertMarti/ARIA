"""Capturas de la ARIA de demostración (datos ficticios) y de su escaparate público con Chromium headless vía CDP.

Uso: python3 capturar.py SALIDA [nombre ...]   (necesita chromium, Pillow y websockets)
"""
import asyncio
import base64
import os
import io
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import websockets
from PIL import Image

BASE = "http://127.0.0.1:18080"
AQUI = Path(__file__).parent
DATOS = Path(os.environ.get("ARIA_DEMO_DIR", AQUI / ".demo"))
PUERTO = 9341

# nombre: (hash, ancho, alto, móvil, js previo, espera)
HABLAR = ("window._t = setInterval(() => dispatchEvent(new CustomEvent('aria:estado', {detail: {estado: 'hablando', nivel: .55 + Math.random() * .35}})), 80);"
          "dispatchEvent(new CustomEvent('aria:hud-texto', {detail: {texto: 'Buenas tardes, Ana. Hoy en Madrid hará 20 grados y cielo despejado. A las 17:30 tienes el dentista.'}}));")
ESCUCHANDO = ("document.body.classList.add('escuchando'); const s = document.getElementById('subtitulo');"
              "s.textContent = 'Ah, y esa lucecita nerviosa es Ping. No le hagas mucho caso.'; s.classList.add('visible');")
VER_COMO_VISITA = ("fetch('/api/vista', {method: 'POST', headers: {'Content-Type': 'application/json'},"
                   " body: JSON.stringify({perfil: 'visita'})}).then(() => location.reload())")
def _soltar_video(nombre="Serie Demo - Capítulo 2.webm"):
    """JS que «suelta» en Compartir el vídeo de demostración (barras de colores propias) y lo deja en el segundo 3."""
    b64 = base64.b64encode((AQUI / "video-demo.webm").read_bytes()).decode()
    return ("(async () => { const b = Uint8Array.from(atob('" + b64 + "'), c => c.charCodeAt(0)); const dt = new DataTransfer();"
            " for (const n of ['" + nombre + "', 'Serie Demo - Capítulo 10.webm', 'Serie Demo - Capítulo 1.webm'])"
            " dt.items.add(new File([b], n, {type: 'video/webm', lastModified: 1700000000000}));"
            " document.getElementById('medios-soltar').dispatchEvent(new DragEvent('drop', {dataTransfer: dt, bubbles: true}));"
            " setTimeout(() => { const v = document.getElementById('medios-video'); v.currentTime = 3; v.pause(); }, 1500); })()")


PULSAR = "[...document.querySelectorAll('#v-notas button')].find(b => b.textContent.trim() === '{}')?.click()"

CAPTURAS = {
    "captura-inicio": ("inicio", 1280, 1400, False, "", 6),
    "captura-hud": ("hud", 1440, 900, False, HABLAR, 6),
    "captura-hud-opciones": ("hud", 1440, 900, False, "document.getElementById('hud-opciones').click()", 4),
    "ux-chat": ("chat", 1280, 820, False, "", 5),
    "ux-movil-chat": ("chat", 390, 844, True, "", 5),
    "ux-movil-notas": ("notas", 390, 844, True, "", 5),
    "ux-finanzas": ("finanzas", 1280, 900, False, "", 5),
    "ux-movil-finanzas": ("finanzas", 390, 844, True, "", 5),
    "captura-agenda": ("agenda", 1280, 900, False, "document.querySelector('.agenda-tab[data-modo=mes]').click()", 4),
    "captura-agenda-semana": ("agenda", 1280, 760, False, "document.querySelector('.agenda-tab[data-modo=semana]').click()", 4),
    "captura-informacion": ("informacion", 1280, 900, False, "", 6),
    "captura-mapa": ("mapa", 1280, 800, False, "", 8),
    "captura-mapa-3d": ("mapa", 1280, 800, False, "localStorage.setItem('aria_mapa_modo', '3d'); location.reload()", 40),
    "captura-red": ("red", 1280, 1000, False, "", 5),
    "captura-centro-control": ("control", 1280, 1100, False, "", 6),
    "captura-ajustes": ("ajustes", 1280, 900, False, "localStorage.setItem('aria_ajustes_seccion','ia'); location.reload()", 5),
    "captura-avisos": ("inicio", 1280, 800, False, "document.querySelector('#campana, .campana, [aria-label*=Avisos]')?.click()", 4),
    "captura-movil-inicio": ("inicio", 390, 844, True, "", 5),
    "captura-movil-hud": ("hud", 390, 844, True, HABLAR, 4),
    "tour-movil-1": ("inicio", 390, 844, True, "Tour.iniciar({forzar: true})", 5),
    "tour-movil-3": ("inicio", 390, 844, True, "Tour.iniciar({forzar: true}); setTimeout(() => { document.dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowRight', bubbles: true})); setTimeout(() => document.dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowRight', bubbles: true})), 1200); }, 1200)", 5),
    "movil-h-hud": ("hud", 844, 390, True, "", 5),
    "movil-v-hud-completo": ("hud", 390, 844, True, "", 5),
    "movil-v-inicio": ("inicio", 390, 844, True, "", 5),
    "movil-v-hud-abajo": ("hud", 390, 844, True, "document.getElementById('v-hud').scrollTop = 700", 5),
    "captura-movil-agenda": ("agenda", 390, 844, True, "document.querySelector('.agenda-tab[data-modo=lista]').click()", 4),
    "captura-movil-red": ("red", 390, 844, True, "document.getElementById('red-tabla').scrollIntoView()", 4),
    "captura-movil-ajustes": ("ajustes", 390, 844, True, "localStorage.setItem('aria_ajustes_seccion','general'); location.reload()", 5),
    # Escaparate público (/hola): rutas que empiezan por «/» se abren tal cual, sin #vista
    "captura-escaparate": ("/hola", 1440, 900, False, ESCUCHANDO, 4),
    "captura-escaparate-menu": ("/hola", 1440, 900, False, "document.getElementById('menu').scrollIntoView()", 4),
    "captura-ping": ("/hola", 1280, 820, False, "document.querySelector('[data-demo=demo-casa]').click()", 5),
    "captura-movil-escaparate": ("/hola", 390, 844, True, "", 4),
    "captura-acceso": ("/acceso", 1280, 1000, False, "", 4),
    "captura-cerebro": ("cerebro", 1280, 860, False, "", 8),
    "captura-compartir": ("compartir", 1280, 820, False, _soltar_video(), 5),
    "captura-salud": ("control", 1280, 1300, False, "", 7),
    "captura-listas": ("notas", 1280, 860, False, PULSAR.format("Listas"), 5),
    "captura-documentos": ("notas", 1280, 860, False, PULSAR.format("Documentos"), 5),
    "captura-seguridad": ("seguridad", 1280, 1500, False, "", 8),
    "captura-ping-aviso": ("inicio", 1280, 800, False, "localStorage.setItem('aria_ping_modo', 'pasea'); window.dispatchEvent(new CustomEvent('aria:avisos', {detail: [{id: 'demo-ping', texto: 'Aviso naranja por lluvia en Madrid esta tarde', severidad: 'grave'}]}))", 4),
    "captura-movil-ping": ("inicio", 390, 844, True, "localStorage.setItem('aria_ping_modo', 'pasea'); window.dispatchEvent(new CustomEvent('aria:avisos', {detail: [{id: 'demo-ping-2', texto: 'Tienes cita con el dentista mañana a las 10:00'}, {id: 'demo-ping-3', texto: 'Copia de seguridad hecha'}]}))", 4),
    "captura-cerebro-panel": ("cerebro", 1280, 860, False, "(() => { const c = document.getElementById('cerebro-canvas');"
                              " const r = c.getBoundingClientRect(), x = r.left + r.width * .53, y = r.top + r.height * .155;"
                              " for (const t of ['pointerdown', 'pointerup']) c.dispatchEvent(new PointerEvent(t, {clientX: x, clientY: y,"
                              " bubbles: true, button: 0, pointerId: 1})); })()", 8),
    # iPad (Air 11": 820×1180 vertical, 1180×820 horizontal; Pro 13": 1032×1376)
    "ipad-v-inicio": ("inicio", 820, 1180, False, "", 6),
    "ipad-v-hud": ("hud", 820, 1180, False, "", 6),
    "ipad-v-chat": ("chat", 820, 1180, False, "", 5),
    "ipad-v-ajustes": ("ajustes", 820, 1180, False, "", 5),
    "ipad-v-agenda": ("agenda", 820, 1180, False, "", 5),
    "ipad-h-inicio": ("inicio", 1180, 820, False, "", 6),
    "ipad-h-hud": ("hud", 1180, 820, False, "", 6),
    "ipad-h-informacion": ("informacion", 1180, 820, False, "", 6),
    "ipad-pro-hud": ("hud", 1032, 1376, False, "", 6),
    "ipad-v-hud-final": ("hud", 820, 1180, False, "document.querySelectorAll('#v-hud, #v-hud *').forEach((e) => { if (e.scrollHeight > e.clientHeight + 20) e.scrollTop = e.scrollHeight; })", 6),
    # Va la última: deja la sesión en «Probar como Visita» (la siguiente ejecución vuelve a entrar desde cero)
    "captura-probar-visita": ("inicio", 1280, 900, False, VER_COMO_VISITA, 5),
}


def clave():
    for l in (DATOS / "demo.env").read_text().splitlines():
        if l.startswith("ARIA_PASSWORD="):
            return l.split("=", 1)[1]


class CDP:
    def __init__(self, ws):
        self.ws, self.n = ws, 0

    async def __call__(self, metodo, **p):
        self.n += 1
        mid = self.n
        await self.ws.send(json.dumps({"id": mid, "method": metodo, "params": p}))
        while True:
            m = json.loads(await self.ws.recv())
            if m.get("id") == mid:
                if "error" in m:
                    raise RuntimeError(f"{metodo}: {m['error']}")
                return m.get("result", {})

    async def js(self, codigo):
        r = await self("Runtime.evaluate", expression=codigo, awaitPromise=True, returnByValue=True, userGesture=True)
        return r.get("result", {}).get("value")


async def main(salida: Path, nombres):
    perfil = DATOS / "perfil-chromium"
    proc = subprocess.Popen(["chromium", "--headless=new", "--enable-unsafe-swiftshader", "--use-angle=swiftshader", f"--remote-debugging-port={PUERTO}", "--no-first-run",
                             "--hide-scrollbars", "--force-color-profile=srgb", f"--user-data-dir={perfil}", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(40):
            try:
                pestañas = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PUERTO}/json"))
                break
            except OSError:
                time.sleep(.5)
        ws_url = next(p for p in pestañas if p["type"] == "page")["webSocketDebuggerUrl"]
        async with websockets.connect(ws_url, max_size=64 * 2**20) as ws:
            c = CDP(ws)
            await c("Page.enable")
            await c("Runtime.enable")
            await c("Emulation.setTimezoneOverride", timezoneId="Asia/Tokyo")   # hora de día en las capturas (misma fecha)
            await c("Emulation.setDeviceMetricsOverride", width=1280, height=800, deviceScaleFactor=1, mobile=False)
            await c("Page.navigate", url=BASE + "/login")
            await asyncio.sleep(3)
            if "/login" in (await c.js("location.pathname")):
                await c.js("(() => { const i = document.querySelectorAll('input'); "
                           "const set = (el, v) => { el.value = v; el.dispatchEvent(new Event('input', {bubbles: true})); }; "
                           f"set(i[0], 'demo'); set(i[1], {json.dumps(clave())}); document.querySelector('form').requestSubmit(); }})()")
                await asyncio.sleep(4)
            await c.js("try { localStorage.setItem('aria_ping_modo', 'nunca') } catch (_) {}")   # Ping no tapa las capturas
            for nombre in nombres:
                h, an, al, movil, previo, espera = CAPTURAS[nombre]
                await c("Emulation.setDeviceMetricsOverride", width=an, height=al, deviceScaleFactor=2 if movil else 1, mobile=movil)
                await c("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": "dark"}])
                await c("Page.navigate", url=f"{BASE}{h}" if h.startswith("/") else f"{BASE}/#{h}")
                await asyncio.sleep(2.5)
                await c.js("location.reload()")
                await asyncio.sleep(espera)
                if previo:
                    await c.js(previo)
                    await asyncio.sleep(2.5)
                png = base64.b64decode((await c("Page.captureScreenshot", format="png"))["data"])
                await c.js("clearInterval(window._t)")
                img = Image.open(io.BytesIO(png)).convert("RGB")
                img.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(salida / f"{nombre}.png", optimize=True)
                print(nombre, img.size, (salida / f"{nombre}.png").stat().st_size // 1024, "KB")
    finally:
        proc.terminate()


if __name__ == "__main__":
    salida = Path(sys.argv[1])
    salida.mkdir(parents=True, exist_ok=True)
    asyncio.run(main(salida, sys.argv[2:] or list(CAPTURAS)))
