"""Estructura de index.html: cada vista (<section id="v-...">) debe ser hija directa de <main> y estar cerrada.
Una fusión de ramas dejó secciones anidadas y Agenda y Mapa salían en blanco."""
from html.parser import HTMLParser
from pathlib import Path

HTML = Path(__file__).resolve().parent.parent / "static" / "index.html"
VACIAS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr", "path",
          "circle", "rect", "line", "polyline", "polygon", "ellipse"}


class Arbol(HTMLParser):
    def __init__(self):
        super().__init__()
        self.pila, self.vistas, self.errores = [], {}, []

    def handle_starttag(self, tag, attrs):
        if tag in VACIAS:
            return
        d = dict(attrs)
        if tag == "section" and (d.get("id") or "").startswith("v-"):
            padre = next((t for t, _ in reversed(self.pila) if t in ("main", "section")), None)
            self.vistas[d["id"]] = padre
        self.pila.append((tag, d.get("id")))

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_endtag(self, tag):
        if tag in VACIAS:
            return
        while self.pila:
            t, _ = self.pila.pop()
            if t == tag:
                return
        self.errores.append(tag)


def test_cada_vista_es_hija_de_main():
    a = Arbol()
    a.feed(HTML.read_text(encoding="utf-8"))
    assert a.vistas, "no se encontraron vistas"
    mal = {v: p for v, p in a.vistas.items() if p != "main"}
    assert not mal, f"vistas anidadas dentro de otra sección: {mal}"
