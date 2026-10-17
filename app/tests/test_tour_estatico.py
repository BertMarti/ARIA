from pathlib import Path


STATIC = Path(__file__).resolve().parent.parent / "static"


def test_tour_se_carga_despues_de_ping_y_no_usa_html_crudo():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    tour = (STATIC / "tour.js").read_text(encoding="utf-8")
    assert html.index("/static/ping-compa.js") < html.index("/static/tour.js") < html.index("/static/app.js")
    assert "innerHTML" not in tour


def test_tarjeta_nueve_presenta_el_tour_nuevo():
    inicio = (STATIC / "inicio.js").read_text(encoding="utf-8")
    assert "ARIA PRO 2" not in inicio
    assert "Tour de ARIA 3" in inicio
    assert "NOVEDADES" in inicio
