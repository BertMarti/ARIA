import asyncio

import pytest

from aria import briefing, config, tools


@pytest.mark.parametrize("texto", ["¿Lloverá el fin de semana en Ronda?", "¿Qué tiempo hará mañana?",
                                    "¿Va a hacer calor el sábado?", "Previsión para Jaén"])
def test_tiempo_se_ofrece(texto):
    assert "tiempo" in tools.relevantes(texto)


@pytest.mark.parametrize("texto", ["¿Qué temperatura tiene la Raspberry?", "¿Cuánto tiempo lleva encendida?",
                                    "Hola", "Explícame qué es un DNS"])
def test_tiempo_no_se_ofrece(texto):
    assert "tiempo" not in tools.relevantes(texto)


class _Resp:
    def __init__(self, d):
        self._d = d

    def json(self):
        return self._d


class _Cliente:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None):
        assert "forecast" in url and params["forecast_days"] == 7
        return _Resp({"daily": {"time": ["2026-10-10", "2026-10-11"], "weather_code": [0, 95],
                                "temperature_2m_max": [24.4, 19.6], "temperature_2m_min": [12.2, 11.0],
                                "precipitation_probability_max": [5, 80]}})


def test_prevision_formatea_dias(monkeypatch):
    monkeypatch.setattr(config, "CIUDAD", "Ronda, Málaga")
    monkeypatch.setattr(config, "LAT", 37.97)
    monkeypatch.setattr(config, "LON", -4.1)
    monkeypatch.setattr(briefing.httpx, "AsyncClient", _Cliente)
    texto = asyncio.run(tools.ejecutar("tiempo", {"dias": 2}))  # el rango pedido se ignora: siempre 7
    assert "Previsión para Ronda" in texto
    assert "HOY sábado 10/10 (FIN DE SEMANA)" in texto and "MAÑANA domingo 11/10 (FIN DE SEMANA)" in texto
    assert "mínima 12 °C, máxima 24 °C" in texto and "lluvia 80 %" in texto


def test_prompt_dice_dia_y_fin_de_semana(monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    class _F(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 7, 21, 0, tzinfo=ZoneInfo("Europe/Madrid"))
    monkeypatch.setattr(config, "datetime", _F)
    p = config.system_prompt(True, "Lucía", True)
    assert "Hoy es miércoles 07/10/2026" in p
    assert "sábado 10/10 y el domingo 11/10" in p
