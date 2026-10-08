"""Informe de arranque: solo tras un reinicio real de la Raspberry (cambia el btime), nunca por reiniciar ARIA."""
import asyncio

from aria import arranque, avisos


def correr(c):
    return asyncio.run(c)


def montar(monkeypatch, btime, estados=None):
    enviados = []

    async def emitir(tipo, severidad, texto, **k):
        enviados.append((tipo, severidad, texto))
        return []

    cola = list(estados or [{"Internet": True, "SHIELD-DNS (bloqueador)": True, "HEIMDALL (VPN)": True,
                             "Acceso desde fuera (túnel)": None}])

    async def comprobar():
        return cola.pop(0) if len(cola) > 1 else cola[0]

    async def dormir(_s):
        return None

    monkeypatch.setattr(arranque, "arranque_kernel", lambda: btime)
    monkeypatch.setattr(arranque, "comprobar", comprobar)
    monkeypatch.setattr(arranque.asyncio, "sleep", dormir)
    monkeypatch.setattr(avisos, "emitir", emitir)
    monkeypatch.setattr(arranque.sistema, "temperatura", lambda: 48.5)
    return enviados


def test_primera_vez_solo_apunta(monkeypatch):
    enviados = montar(monkeypatch, 1000.0)
    assert correr(arranque.revisar(None)) is None and enviados == []
    assert arranque._leer("arranque.json") == {"btime": 1000.0}


def test_reinicio_de_aria_sin_reinicio_del_sistema_no_avisa(monkeypatch):
    arranque._escribir("arranque.json", {"btime": 1000.0})
    enviados = montar(monkeypatch, 1001.0)  # mismo arranque (diferencias de redondeo)
    assert correr(arranque.revisar(900.0)) is None and enviados == []


def test_reinicio_real_envia_informe_con_tiempo_sin_servicio(monkeypatch):
    arranque._escribir("arranque.json", {"btime": 1000.0})
    enviados = montar(monkeypatch, 1_800_000_000.0)
    texto = correr(arranque.revisar(1_800_000_000.0 - 600))  # último latido 10 min antes del arranque
    assert enviados and enviados[0][:2] == ("sistema", "info") and enviados[0][2] == texto
    assert "se ha reiniciado" in texto and "unos 10 min" in texto and "DNS de respaldo" in texto
    assert "✅ SHIELD-DNS (bloqueador)" in texto and "túnel" not in texto  # None = sin configurar: no se lista
    assert "48,5 °C" in texto
    assert arranque._leer("arranque.json") == {"btime": 1_800_000_000.0}
    # Un segundo reinicio de ARIA en el mismo arranque ya no repite el informe
    assert correr(arranque.revisar(None)) is None and len(enviados) == 1


def test_espera_a_que_vuelvan_los_servicios(monkeypatch):
    arranque._escribir("arranque.json", {"btime": 1000.0})
    caido = {"Internet": True, "SHIELD-DNS (bloqueador)": False, "HEIMDALL (VPN)": True, "Acceso desde fuera (túnel)": True}
    bien = dict(caido, **{"SHIELD-DNS (bloqueador)": True})
    enviados = montar(monkeypatch, 2000.0, [caido, caido, bien])
    texto = correr(arranque.revisar(None))
    assert "❌" not in texto and "Algo no ha vuelto" not in texto and len(enviados) == 1


def test_si_algo_no_vuelve_lo_dice(monkeypatch):
    arranque._escribir("arranque.json", {"btime": 1000.0})
    caido = {"Internet": True, "SHIELD-DNS (bloqueador)": True, "HEIMDALL (VPN)": False, "Acceso desde fuera (túnel)": True}
    montar(monkeypatch, 2000.0, [caido])
    texto = correr(arranque.revisar(None, espera_max=0))
    assert "❌ HEIMDALL (VPN)" in texto and "Algo no ha vuelto" in texto


def test_fallo_al_enviar_no_repite_en_bucle(monkeypatch):
    arranque._escribir("arranque.json", {"btime": 1000.0})
    montar(monkeypatch, 3000.0)

    async def roto(*a, **k):
        raise RuntimeError("telegram caído")
    monkeypatch.setattr(avisos, "emitir", roto)
    try:
        correr(arranque.revisar(None))
    except RuntimeError:
        pass
    assert arranque._leer("arranque.json") == {"btime": 3000.0}


def test_duracion_legible():
    assert arranque.duracion(42) == "42 s" and arranque.duracion(600) == "10 min"
    assert arranque.duracion(3600 + 20 * 60) == "1 h 20 min" and arranque.duracion(3 * 86400) == "3 días"


def test_kernel_lee_btime():
    assert arranque.arranque_kernel() is None or arranque.arranque_kernel() > 0
