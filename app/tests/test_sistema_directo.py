import hashlib
import hmac
import json
import time

from aria import config, permisos, telemetria, telegram


def muestra(ts=None):
    return {"ts": time.time() if ts is None else ts,
            "sistema": {"cpu": 12.0, "carga": [1, 5, 15], "temperatura": 52.0,
                        "red_rx_bps": 10, "red_tx_bps": 20},
            "contenedores": [{"nombre": "ollama", "cpu": 8.0, "memoria": 1000,
                              "red_rx": 2, "red_tx": 3, "procesos": 4}]}


def test_telemetria_actual_vieja_y_ausente(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    ruta = tmp_path / "host"
    ruta.mkdir()
    telemetria.iniciar()
    (ruta / "telemetria.json").write_text(json.dumps(muestra()), encoding="utf-8")
    assert telemetria.leer()["sistema"]["cpu"] == 12.0
    (ruta / "telemetria.json").write_text(json.dumps(muestra(time.time() - 31)), encoding="utf-8")
    try:
        telemetria.leer()
        assert False
    except RuntimeError as e:
        assert "instalar-host-agente.sh" in str(e)
    (ruta / "telemetria.json").unlink()
    try:
        telemetria.leer()
        assert False
    except RuntimeError:
        pass


def test_historial_y_umbral(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    telemetria.iniciar()
    ahora = time.time()
    d = muestra(ahora)
    d["sistema"]["cpu"] = 95
    monkeypatch.setattr(telemetria, "_ultimo_minuto", None)
    telemetria.guardar_muestra(d)
    assert telemetria.historial(1)
    monkeypatch.setattr(telemetria, "_rachas", __import__("collections").defaultdict(int))
    assert not telemetria.estados(d)["cpu"]["activo"]
    assert telemetria.estados(d)["cpu"]["activo"]


def test_firma_reinicio_y_limite(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "SECRET", "s" * 40)
    monkeypatch.setattr(telemetria, "_ultima_peticion", 0.0)
    r = telemetria.solicitar_reinicio()
    datos = json.loads((tmp_path / "host/peticiones/reinicio.json").read_text())
    esperada = hmac.new(config.SECRET.encode(), f"reiniciar:{int(datos['ts'])}:{datos['nonce']}".encode(), hashlib.sha256).hexdigest()
    assert r == {"programado": True, "segundos": 15} and hmac.compare_digest(datos["firma"], esperada)
    try:
        telemetria.solicitar_reinicio()
        assert False
    except RuntimeError as e:
        assert "10 minutos" in str(e)


def test_permisos_y_ficha_un_solo_uso():
    assert not permisos.permitido("usuario", "GET", "/api/sistema/directo")
    assert not permisos.permitido("usuario", "POST", "/api/sistema/reiniciar")
    token = telegram.ficha(1, 1, "reiniciar")
    assert telegram.gastar_ficha(token, 2) is None
