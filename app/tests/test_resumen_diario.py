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
    monkeypatch.setattr(red, "dispositivos", lambda: _async([]))
    resumen_diario._cache.clear()
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
    monkeypatch.setattr(resumen_diario, "_cierre", caido)
    resumen_diario._cache.clear()
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
    monkeypatch.setattr(resumen_diario, "construir_resumen_diario", lambda u, refrescar=False: _async({
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


def _datos(**extra):
    base = {"fecha": "2026-10-09", "saludo": "Buenos días, Ana", "fecha_texto": "viernes, 9 de octubre",
            "tiempo": {"ciudad": "Pueblo", "cielo": "despejado", "actual": 18, "min": 11, "max": 24, "lluvia": 10},
            "finanzas": {"mes_texto": "octubre", "gastos": 52340, "ingresos": 185000, "mes_anterior": 90000,
                         "mes_anterior_mismo_dia": 60000,
                         "presupuestos": [{"categoria": "Súper & más", "porcentaje": 64, "superado": False}]},
            "inversiones": {"valores": [{"nombre": "Fondo", "precio": 1234.5, "variacion_dia": -0.84}],
                            "total_posiciones": None},
            "agenda": {"eventos": [{"titulo": "Dentista", "inicio": "2026-10-09T17:30", "lugar": "Centro"}],
                       "cumpleanos": [{"nombre": "Lucía", "fecha": "2026-10-10", "edad": 32}]},
            "recordatorios": [{"texto": "Basura", "cuando": "2026-10-09T21:00"}]}
    base.update(extra)
    return base


def test_formato_espanol_y_secciones():
    texto = resumen_diario.telegram(_datos())
    assert "<b>Buenos días, Ana</b>" in texto and "<i>Viernes, 9 de octubre</i>" in texto
    assert "Gastado: 523,40 €" in texto and "▼ 13 %" in texto
    assert "Súper &amp; más 64 %" in texto
    assert "Fondo: 1.234,50 € 🔴 -0,84 %" in texto
    assert "• 17:30 Dentista — Centro" in texto and "⏰ 21:00 Basura" in texto
    assert "🎂 Lucía cumple 32: mañana" in texto


def test_texto_plano_sin_etiquetas():
    texto = resumen_diario.texto_plano(_datos(saludo="Hola <b>x</b>"))
    assert "<b>El tiempo" not in texto and "🌤️ El tiempo · Pueblo" in texto


def test_aplicaciones_con_problemas_y_red():
    d = _datos(aplicaciones={"ok": False, "veredicto": "Atención: SHIELD-DNS no responde", "problemas": ["SHIELD-DNS no responde"],
                             "raspberry": {"temperatura": 49.6, "ram": 43, "disco": 12, "encendida": "3 días"}},
               red={"total": 9, "nuevos": [{"nombre": "Tablet <x>"}], "n_desconocidos": 1,
                    "desconocidos": [{"nombre": "Espressif", "ip": "192.168.1.45"}]})
    texto = resumen_diario.telegram(d)
    assert "⚠️ 1 cosa que revisar:\n   · SHIELD-DNS no responde" in texto
    assert "🍓 Raspberry: 49,6 °C · RAM 43 % · disco 12 % · encendida 3 días" in texto
    assert "Tablet &lt;x&gt;" in texto and "Espressif (192.168.1.45)" in texto


@pytest.mark.asyncio
async def test_cache_y_refresco(monkeypatch):
    user = usuarios.crear("cache@example.invalid", "Cache", "usuario")
    resumen_diario._cache.clear()
    llamadas = []
    async def tiempo_():
        llamadas.append(1)
        return None
    monkeypatch.setattr(briefing, "_tiempo", tiempo_)
    monkeypatch.setattr(briefing, "prevision", lambda dias=2: _async(None))
    monkeypatch.setattr(resumen_diario.informacion, "mercados", lambda uid: _async({"valores": []}))
    monkeypatch.setattr(resumen_diario, "_cierre", lambda d: _async(None))
    await resumen_diario.construir_resumen_diario(user)
    await resumen_diario.construir_resumen_diario(user)
    assert len(llamadas) == 1
    await resumen_diario.construir_resumen_diario(user, refrescar=True)
    assert len(llamadas) == 2


@pytest.mark.asyncio
async def test_cerebros_configurados_cuentan_como_listos(monkeypatch):
    monkeypatch.setattr(resumen_diario.cerebros, "estado", lambda: [
        {"estado": "configurado", "activo": True}, {"estado": "espera", "activo": True},
        {"estado": "configurado", "activo": False}])
    monkeypatch.setattr(resumen_diario.estadisticas, "resumen", lambda horas=24: _async({"totales": {"consultas": 1}}))
    monkeypatch.setattr(resumen_diario.vpn, "listar", lambda: _async([]))
    a = await resumen_diario._aplicaciones()
    assert a["aria"] == {"listos": 1, "total": 2}
    assert "ningún cerebro de IA está disponible" not in a["problemas"]
