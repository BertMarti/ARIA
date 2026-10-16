import pytest

from aria import gasolineras


def fila(lat="40,0", lon="-3,0", precio="1,500"):
    return {"Latitud": lat, "Longitud (WGS84)": lon, "Rótulo": "Prueba", "Dirección": "Calle 1",
            "Municipio": "Madrid", "Precio Gasolina 95 E5": precio, "Precio Gasoleo A": "1,400"}


def test_parsea_comas_y_campos_utiles():
    r = gasolineras.parsear({"ListaEESSPrecio": [fila()]})
    assert r[0]["gasolina95"] == 1.5
    assert r[0]["direccion"] == "Calle 1 Madrid"


@pytest.mark.asyncio
async def test_cerca_radio_y_orden(monkeypatch):
    datos = gasolineras.parsear({"ListaEESSPrecio": [fila(precio="1,600"), fila(lat="40,05", precio="1,400")]})
    monkeypatch.setattr(gasolineras, "actualizar", lambda: datos)
    # La lambda no async es intencionada: el test verifica la API async mediante un wrapper real.
    async def datos_async():
        return datos
    monkeypatch.setattr(gasolineras, "actualizar", datos_async)
    r = await gasolineras.cerca(40, -3, radio_km=10)
    assert [x["precio"] for x in r] == [1.4, 1.6]
    assert all(x["distancia_km"] <= 10 for x in r)


@pytest.mark.asyncio
async def test_copia_anterior_si_falla(monkeypatch, tmp_path):
    monkeypatch.setattr(gasolineras.config, "DATA_DIR", tmp_path)
    gasolineras._cache = None
    (tmp_path / "gasolineras.json").write_text('{"estaciones": [{"lat": 1, "lon": 2, "gasolina95": 1.2}]}')
    async def falla(*args, **kwargs):
        raise gasolineras.httpx.ConnectError("sin red")
    monkeypatch.setattr(gasolineras.httpx.AsyncClient, "get", falla)
    assert (await gasolineras.actualizar())[0]["gasolina95"] == 1.2
