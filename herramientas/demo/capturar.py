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
CAPTURAS = {
    "captura-inicio": ("inicio", 1280, 1400, False, "", 6),
    "captura-hud": ("hud", 1440, 900, False, HABLAR, 6),
    "captura-hud-opciones": ("hud", 1440, 900, False, "document.getElementById('hud-opciones').click()", 4),
    "captura-agenda": ("agenda", 1280, 900, False, "document.querySelector('.agenda-tab[data-modo=mes]').click()", 4),
    "captura-agenda-semana": ("agenda", 1280, 760, False, "document.querySelector('.agenda-tab[data-modo=semana]').click()", 4),
    "captura-informacion": ("informacion", 1280, 900, False, "", 6),
    "captura-mapa": ("mapa", 1280, 800, False, "", 8),
    "captura-red": ("red", 1280, 1000, False, "", 5),
    "captura-centro-control": ("control", 1280, 1100, False, "", 6),
    "captura-ajustes": ("ajustes", 1280, 900, False, "localStorage.setItem('aria_ajustes_seccion','ia'); location.reload()", 5),
    "captura-avisos": ("inicio", 1280, 800, False, "document.querySelector('#campana, .campana, [aria-label*=Avisos]')?.click()", 4),
    "captura-movil-inicio": ("inicio", 390, 844, True, "", 5),
    "captura-movil-hud": ("hud", 390, 844, True, HABLAR, 4),
    "captura-movil-agenda": ("agenda", 390, 844, True, "document.querySelector('.agenda-tab[data-modo=lista]').click()", 4),
    "captura-movil-red": ("red", 390, 844, True, "document.getElementById('red-tabla').scrollIntoView()", 4),
    "captura-movil-ajustes": ("ajustes", 390, 844, True, "localStorage.setItem('aria_ajustes_seccion','general'); location.reload()", 5),
    # Escaparate público (/hola): rutas que empiezan por «/» se abren tal cual, sin #vista
    "captura-escaparate": ("/hola", 1440, 900, False, ESCUCHANDO, 4),
    "captura-escaparate-menu": ("/hola", 1440, 900, False, "document.getElementById('menu').scrollIntoView()", 4),
    "captura-ping": ("/hola", 1280, 820, False, "document.querySelector('[data-demo=demo-casa]').click()", 5),
    "captura-movil-escaparate": ("/hola", 390, 844, True, "", 4),
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
        r = await self("Runtime.evaluate", expression=codigo, awaitPromise=True, returnByValue=True)
        return r.get("result", {}).get("value")


async def main(salida: Path, nombres):
    perfil = DATOS / "perfil-chromium"
    proc = subprocess.Popen(["chromium", "--headless=new", f"--remote-debugging-port={PUERTO}", "--no-first-run",
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
