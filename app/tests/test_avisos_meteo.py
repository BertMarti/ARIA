import pytest

from aria import avisos_meteo

ATOM = """<feed xmlns:cap="urn:oasis:names:tc:emergency:cap:1.2"><entry>
<id>aviso-1</id><cap:areaDesc>Madrid</cap:areaDesc><cap:severity>Severe</cap:severity>
<cap:event>Viento</cap:event><cap:onset>2099-01-01T12:00:00+01:00</cap:onset>
<cap:expires>2099-01-01T18:00:00+01:00</cap:expires></entry><entry>
<id>aviso-2</id><cap:areaDesc>Madrid</cap:areaDesc><cap:severity>Minor</cap:severity>
<cap:event>Lluvia</cap:event></entry></feed>"""


def test_parsea_zona_y_nivel():
    r = avisos_meteo.parsear(ATOM, "Madrid")
    assert [x["clave"] for x in r] == ["aviso-1"]
    assert avisos_meteo.parsear(ATOM, "Toledo") == []


@pytest.mark.asyncio
async def test_propuesta_para_aviso_naranja_o_rojo(monkeypatch):
    monkeypatch.setattr(avisos_meteo, "avisos", lambda: _avisos())
    r = await avisos_meteo.propuestas(__import__("datetime").datetime(2099, 1, 1, 9,
                                                                        tzinfo=__import__("datetime").timezone.utc))
    assert r[0]["args"]["texto"] == "Recoger la ropa / cerrar ventanas"


async def _avisos():
    return avisos_meteo.parsear(ATOM, "Madrid")
