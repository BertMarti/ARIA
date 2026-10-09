import pytest

from aria import briefing, red, resumen_diario, telegram, usuarios


@pytest.mark.asyncio
async def test_construye_todos_los_bloques_y_filtra_el_rol(monkeypatch):
    admin = usuarios.crear("admin@example.invalid", "Administrador", "admin")
    user = usuarios.crear("user@example.invalid", "Usuario", "usuario")
    monkeypatch.setattr(briefing, "_tiempo", lambda: _async({"ciudad": "Pueblo", "cielo": "despejado", "actual": 20, "min": 10, "max": 25, "lluvia": 5}))
    monkeypatch.setattr(briefing, "prevision", lambda dias=2: _async(None))
    monkeypatch.setattr(resumen_diario.informacion, "mercados", lambda uid: _async({"valores": [{"nombre": "Fondo", "precio": 12.5}]}))
    monkeypatch.setattr(resumen_diario.estadisticas, "resumen", lambda horas=24: _async({"totales": {"consultas": 100, "bloqueadas": 20, "porcentaje": 20}}))
    monkeypatch.setattr(resumen_diario.vpn, "listar", lambda: _async([]))
    monkeypatch.setattr(resumen_diario.modulos, "listar", lambda rol: _async([]))
    monkeypatch.setattr(red, "dispositivos", lambda: _async([]))
    todos = await resumen_diario.construir_resumen_diario(admin)
    solo = await resumen_diario.construir_resumen_diario(user)
    assert todos["tiempo"] and todos["finanzas"] and todos["inversiones"]
    assert "aplicaciones" in todos and "aplicaciones" not in solo
    assert "red" in todos and "red" not in solo


def test_presentador_escapa_variables_y_no_supera_telegram():
    datos = {"saludo": "Buenos días <b>intruso</b>", "fecha_texto": "jueves, 8 de octubre",
             "tiempo": None, "aplicaciones": None, "red": {"nuevos": [], "desconocidos": []},
             "finanzas": None, "inversiones": {"valores": [{"nombre": "<b>fondo</b>", "precio": 1}]},
             "agenda": {"eventos": [], "cumpleanos": []}, "recordatorios": []}
    texto = resumen_diario.telegram(datos)
    assert "&lt;b&gt;intruso&lt;/b&gt;" in texto
    assert len(texto) <= 4096
    assert "<b>El tiempo" not in texto


async def _async(valor):
    return valor


@pytest.mark.asyncio
async def test_servicios_caidos_se_omiten(monkeypatch):
    user = usuarios.por_identificador("admin")
    async def caido(*args, **kwargs):
        raise RuntimeError("caído")
    monkeypatch.setattr(briefing, "_tiempo", caido)
    monkeypatch.setattr(briefing, "prevision", caido)
    monkeypatch.setattr(resumen_diario.informacion, "mercados", caido)
    monkeypatch.setattr(resumen_diario.estadisticas, "resumen", caido)
    monkeypatch.setattr(resumen_diario.vpn, "listar", caido)
    monkeypatch.setattr(resumen_diario.red, "dispositivos", caido)
    monkeypatch.setattr(resumen_diario.modulos, "listar", caido)
    monkeypatch.setattr(resumen_diario, "_cierre", caido)
    resultado = await resumen_diario.construir_resumen_diario(user)
    assert resultado["tiempo"] is None and resultado["inversiones"] is None
    assert "aplicaciones" in resultado


@pytest.mark.asyncio
async def test_comando_resumen_manda_html_por_bot_falso(monkeypatch):
    user = usuarios.por_identificador("admin")
    telegram.crear_codigo(user["id"])
    codigo = telegram.crear_codigo(user["id"])["codigo"]
    class Bot:
        def __init__(self): self.llamadas = []
        async def llamar(self, metodo, **datos):
            self.llamadas.append((metodo, datos)); return {}
    bot = Bot()
    monkeypatch.setattr(resumen_diario, "construir_resumen_diario", lambda u: _async({
        "saludo": "Buenos días", "fecha_texto": "hoy", "tiempo": None,
        "aplicaciones": None, "red": None, "finanzas": None, "inversiones": None,
        "agenda": {"eventos": [], "cumpleanos": []}, "recordatorios": []}))
    # Vinculación con un código nuevo y petición bajo demanda.
    await telegram.procesar({"message": {"chat": {"id": 77, "type": "private"}, "from": {"id": 77},
                                         "text": "/start " + codigo}}, bot)
    await telegram.procesar({"message": {"chat": {"id": 77, "type": "private"}, "from": {"id": 77},
                                         "text": "/resumen"}}, bot)
    envios = [d for m, d in bot.llamadas if m == "sendMessage" and d.get("parse_mode") == "HTML"]
    assert envios and "<b>" in envios[-1]["text"]
