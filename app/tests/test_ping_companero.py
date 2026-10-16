from pathlib import Path


STATIC = Path(__file__).resolve().parent.parent / "static"


def test_ping_companero_se_carga_antes_de_app_y_no_inserta_html_crudo():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    ping = (STATIC / "ping-compa.js").read_text(encoding="utf-8")
    assert "/static/escaparate/ping.js" in html
    assert "/static/ping-compa.js" in html
    assert html.index("/static/ping-compa.js") < html.index("/static/app.js")
    assert "innerHTML" not in ping
