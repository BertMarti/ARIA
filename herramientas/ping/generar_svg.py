"""Genera a Ping en SVG animado (para el README y la documentación de GitHub, que no ejecutan JavaScript).

Misma geometría que `app/static/escaparate/ping.js`: esfera con remolino, dos anillos discontinuos que giran
en sentidos opuestos, marcas de mira, cuatro alas holográficas que baten y una estela de píxeles. Solo CSS
dentro del SVG (GitHub lo anima al mostrarlo como imagen) y se queda quieto con «reducir movimiento».

Uso: python3 herramientas/ping/generar_svg.py   → docs/img/ping/*.svg
"""
import math
from html import escape
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
SALIDA = RAIZ / "docs" / "img" / "ping"

COLORES = {"ok": "#38d6ff", "aviso": "#fbbf24", "alerta": "#fb7185", "pensando": "#7c8cff"}

# nombre: (estado, frase del bocadillo o None, voltear: Ping a la derecha y el bocadillo a la izquierda)
PINGS = {
    "ping-hola": ("ok", "¡Eh, mira! Esta es ARIA. Yo soy Ping.", False),
    "ping-instalar": ("ok", "¿Cinco minutos? Yo lo hago en dos.", True),
    "ping-modulos": ("pensando", "Más apps, más cosas que vigilar. ¡Me encanta!", False),
    "ping-cerebros": ("pensando", "Pensando… (ARIA piensa, yo cuento anuncios)", True),
    "ping-seguridad": ("ok", "Yo vigilo la red. Tú duerme tranquilo.", False),
    "ping-problemas": ("aviso", "¿Algo falla? Mira aquí antes de asustarte.", True),
    "ping-adios": ("ok", "¡Hasta luego! Y no toques mis anuncios.", False),
    "ping": ("ok", None, False),
}


def _ala(lado: int, arriba: bool) -> str:
    s = 1 if arriba else .68
    L, A = 40 * s, 16 * s
    rot = math.degrees(-.42 if arriba else .32)
    dy = -2 if arriba else 4
    puntos = f"6,0 {6 + L:.1f},{-A * .9:.1f} {6 + L * .86:.1f},{A * .15:.1f} 8,{A * .42:.1f}"
    vena = f"M10 2L{6 + L * .55:.1f} {-A * .42:.1f}L{6 + L * .78:.1f} {-A * .5:.1f}"
    nodo_x, nodo_y = 6 + L * .78 - 1.2, -A * .5 - 1.2
    retraso = "0s" if arriba else "-.05s"
    return (f'<g transform="translate(0 {dy}) scale({lado} 1) rotate({rot:.1f})">'
            f'<g class="bate" style="animation-delay:{retraso}">'
            f'<polygon points="{puntos}" fill="var(--c)" fill-opacity=".14" stroke="var(--c)" stroke-opacity=".9" stroke-width="1"/>'
            f'<path d="{vena}" fill="none" stroke="#fff" stroke-opacity=".5" stroke-width=".7"/>'
            f'<rect x="{nodo_x:.1f}" y="{nodo_y:.1f}" width="2.4" height="2.4" fill="var(--c)"/></g></g>')


def _ping(color: str, voltear: bool = False) -> str:
    alas = "".join(_ala(l, a) for a in (True, False) for l in (1, -1))
    marcas = "".join(
        f'<line x1="{math.cos(a) * 29:.1f}" y1="{math.sin(a) * 29:.1f}" x2="{math.cos(a) * 33:.1f}" y2="{math.sin(a) * 33:.1f}"/>'
        for a in (i * math.pi / 2 + math.pi / 4 for i in range(4)))
    estela = "".join(f'<rect class="pix" x="{-14 - i * 9:.0f}" y="{14 + (i % 3) * 3:.0f}" width="2.4" height="2.4" fill="var(--c)" '
                     f'style="animation-delay:-{i * .25:.2f}s"/>' for i in range(7))
    remolino = "".join(f'<ellipse rx="{11 * (.9 - i * .12):.1f}" ry="{11 * (.3 + i * .1):.1f}" transform="rotate({i * 45})" '
                       f'stroke="{"#fff" if i % 2 else "var(--c)"}" stroke-opacity=".35"/>' for i in range(4))
    escala = "-1.3 1.3" if voltear else "1.3"   # volteado: la estela queda detrás, lejos del bocadillo
    return f'''<g class="vuela"><g transform="scale({escala})">
  <circle r="50" fill="url(#halo)"/>
  {estela}
  <g class="cuerpo">
    <g style="mix-blend-mode:screen">{alas}</g>
    <circle r="11" fill="url(#nucleo)"/>
    <g clip-path="url(#esfera)" fill="none" stroke-width=".8"><g class="remolino">{remolino}</g></g>
    <circle class="anillo1" r="19" fill="none" stroke="var(--c)" stroke-opacity=".8" stroke-width="1.1" stroke-dasharray="8 5"/>
    <circle class="anillo2" r="25" fill="none" stroke="var(--c)" stroke-opacity=".55" stroke-width=".7" stroke-dasharray="2 6"/>
    <g class="mira" stroke="var(--c)" stroke-opacity=".6" stroke-width="1">{marcas}</g>
  </g>
</g></g>'''


def svg(estado: str, frase: str | None, voltear: bool) -> str:
    color = COLORES[estado]
    ping_w, alto = 150, 136
    texto_w = round(len(frase) * 7.9) if frase else 0
    burbuja_w = texto_w + 28 if frase else 0
    ancho = ping_w + (burbuja_w + 14 if frase else 0)
    px = ancho - ping_w / 2 if voltear else ping_w / 2
    bx = 8 if voltear else ping_w + 6
    burbuja = ""
    if frase:
        x0, y0, h, k = bx, 50, 34, 7
        forma = f"{x0 + k},{y0} {x0 + burbuja_w},{y0} {x0 + burbuja_w},{y0 + h - k} {x0 + burbuja_w - k},{y0 + h} {x0},{y0 + h} {x0},{y0 + k}"
        cola = (f"{x0 + burbuja_w},{y0 + 12} {x0 + burbuja_w + 9},{y0 + 17} {x0 + burbuja_w},{y0 + 22}" if voltear
                else f"{x0},{y0 + 12} {x0 - 9},{y0 + 17} {x0},{y0 + 22}")
        burbuja = (f'<g class="burbuja"><polygon points="{cola}" fill="#06111f" stroke="var(--c)" stroke-opacity=".6"/>'
                   f'<polygon class="borde" points="{forma}" fill="#06111f" fill-opacity=".92" stroke="var(--c)" stroke-opacity=".6"/>'
                   f'<text x="{x0 + 14}" y="{y0 + 22}" fill="#f2f6ff" font-family="JetBrains Mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" '
                   f'font-size="13">{escape(frase)}</text></g>')
    titulo = f"Ping: «{frase}»" if frase else "Ping, el hada de luz de ARIA"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{ancho}" height="{alto}" viewBox="0 0 {ancho} {alto}" role="img" aria-label="{escape(titulo)}">
<title>{escape(titulo)}</title>
<style>
  svg {{ --c: {color}; }}
  .vuela {{ animation: flota 4.8s ease-in-out infinite; }}
  .cuerpo {{ animation: balanceo 3.2s ease-in-out infinite; }}
  .bate {{ animation: bate .18s ease-in-out infinite alternate; }}
  .anillo1 {{ animation: gira 6s linear infinite; }}
  .anillo2 {{ animation: gira 9s linear infinite reverse; }}
  .mira {{ animation: gira 16s linear infinite; }}
  .remolino {{ animation: gira 2.6s linear infinite; }}
  .pix {{ animation: pix 1.75s linear infinite; }}
  .borde {{ animation: late 2.4s ease-in-out infinite; }}
  @keyframes flota {{ 0%, 100% {{ transform: translate({px}px, 70px); }} 25% {{ transform: translate({px + 5}px, 64px); }}
    50% {{ transform: translate({px - 2}px, 74px); }} 75% {{ transform: translate({px - 6}px, 67px); }} }}
  @keyframes balanceo {{ 0%, 100% {{ transform: rotate(-6deg); }} 50% {{ transform: rotate(6deg); }} }}
  @keyframes bate {{ from {{ transform: scaleX(1); }} to {{ transform: scaleX(.35); }} }}
  @keyframes gira {{ to {{ transform: rotate(360deg); }} }}
  @keyframes pix {{ 0% {{ opacity: .9; transform: translate(0, 0); }} 100% {{ opacity: 0; transform: translate(-6px, 10px); }} }}
  @keyframes late {{ 50% {{ stroke-opacity: 1; }} }}
  @media (prefers-reduced-motion: reduce) {{ * {{ animation: none !important; }} .vuela {{ transform: translate({px}px, 70px); }} }}
</style>
<defs>
  <radialGradient id="halo"><stop offset="0" stop-color="{color}" stop-opacity=".42"/><stop offset=".5" stop-color="{color}" stop-opacity=".08"/><stop offset="1" stop-color="{color}" stop-opacity="0"/></radialGradient>
  <radialGradient id="nucleo" cx=".36" cy=".32" r=".75"><stop offset="0" stop-color="#fff" stop-opacity=".95"/><stop offset=".35" stop-color="{color}" stop-opacity=".9"/><stop offset="1" stop-color="#06111f"/></radialGradient>
  <clipPath id="esfera"><circle r="11"/></clipPath>
</defs>
{burbuja}
{_ping(color, voltear)}
</svg>
'''


def main():
    SALIDA.mkdir(parents=True, exist_ok=True)
    for nombre, (estado, frase, voltear) in PINGS.items():
        (SALIDA / f"{nombre}.svg").write_text(svg(estado, frase, voltear), encoding="utf-8")
        print(nombre)


if __name__ == "__main__":
    main()
