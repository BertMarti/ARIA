"""Pruebas del agente del host (`sistema/host-agente.py`): peticiones firmadas, vigilancia del túnel
y volcado de las notas de mejora al plan privado. Sin red, sin hilos de verdad y sin reiniciar nada:
el módulo se carga con importlib contra un repo de mentira dentro de tmp_path."""
import hashlib
import hmac
import importlib.util
import json
import os
import time
from pathlib import Path

import pytest

RUTA_AGENTE = Path(__file__).resolve().parents[2] / "sistema" / "host-agente.py"
SECRETO = "x" * 20
CLAVE = SECRETO.encode()
MARCA_INI = "<!-- NOTAS-TELEGRAM:INICIO -->"
MARCA_FIN = "<!-- NOTAS-TELEGRAM:FIN -->"


def firmar(accion: str, ts: float, nonce: str) -> str:
    return hmac.new(CLAVE, f"{accion}:{int(ts)}:{nonce}".encode(), hashlib.sha256).hexdigest()


def escribir(ruta: Path, datos) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos), encoding="utf-8")


def estado(agente) -> dict:
    return json.loads((agente.HOST / "tunel.json").read_text(encoding="utf-8"))


def notas(agente, contenido: list, mtime: float) -> None:
    ruta = agente.HOST / "notas-mejoras.json"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(contenido), encoding="utf-8")
    os.utime(ruta, (mtime, mtime))


@pytest.fixture
def agente(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(f"ARIA_SECRET={SECRETO}\nARIA_URL_PUBLICA=https://aria.example.com\n",
                                   encoding="utf-8")
    monkeypatch.setenv("ARIA_DIR", str(tmp_path))
    assert RUTA_AGENTE.is_file(), f"No está el agente en {RUTA_AGENTE}"
    espec = importlib.util.spec_from_file_location("host_agente_prueba", RUTA_AGENTE)
    mod = importlib.util.module_from_spec(espec)
    espec.loader.exec_module(mod)
    mod.HOST = tmp_path / "data" / "host"
    mod.PETICIONES = mod.HOST / "peticiones"
    mod.RESULTADOS = mod.HOST / "resultados"
    mod.PLAN_PRIVADO = tmp_path / "PLAN-DE-TRABAJO.md"
    mod.PETICIONES.mkdir(parents=True)
    mod.RESULTADOS.mkdir(parents=True)
    return mod


@pytest.fixture(autouse=True)
def sin_reboot(agente, monkeypatch):
    """Ninguna prueba debe arrancar órdenes del sistema; «reboot» es un fallo seguro."""
    llamadas = []

    def run(args, **kwargs):
        orden = [str(a) for a in (args or [])]
        assert "reboot" not in orden, "el agente no debe llamar a systemctl reboot en las pruebas"
        llamadas.append(orden)
        raise AssertionError(f"orden inesperada en las pruebas: {orden}")

    monkeypatch.setattr(agente.subprocess, "run", run)
    return llamadas


# --- Peticiones firmadas ---------------------------------------------------------------------------------
def test_peticion_copia_firmada_llama_en_hilo(agente, monkeypatch, sin_reboot):
    llamadas = []
    monkeypatch.setattr(agente, "_en_hilo", lambda accion, fn: llamadas.append((accion, fn)))
    ts, nonce = time.time(), "n" * 32
    escribir(agente.PETICIONES / "copia.json", {"ts": ts, "nonce": nonce, "firma": firmar("copia", ts, nonce)})
    agente.revisar_peticiones(CLAVE)
    assert [a for a, _ in llamadas] == ["copia"]
    assert llamadas[0][1] == agente._copia
    assert not (agente.PETICIONES / "copia.json").exists()   # la consume al mirarla
    assert sin_reboot == []


def test_firma_de_otra_accion_se_ignora(agente, monkeypatch, sin_reboot):
    llamadas = []
    monkeypatch.setattr(agente, "_en_hilo", lambda accion, fn: llamadas.append(accion))
    ts, nonce = time.time(), "n" * 32
    escribir(agente.PETICIONES / "copia.json", {"ts": ts, "nonce": nonce, "firma": firmar("reiniciar", ts, nonce)})
    agente.revisar_peticiones(CLAVE)
    assert llamadas == [] and not (agente.PETICIONES / "copia.json").exists()
    assert sin_reboot == []


def test_nonce_repetido_se_ignora(agente, monkeypatch):
    llamadas = []
    monkeypatch.setattr(agente, "_en_hilo", lambda accion, fn: llamadas.append(accion))
    ts, nonce = time.time(), "n" * 32
    datos = {"ts": ts, "nonce": nonce, "firma": firmar("copia", ts, nonce)}
    escribir(agente.PETICIONES / "copia.json", datos)
    agente.revisar_peticiones(CLAVE)
    escribir(agente.PETICIONES / "copia.json", datos)   # la misma petición, otra vez
    agente.revisar_peticiones(CLAVE)
    assert llamadas == ["copia"]


def test_peticion_de_hace_diez_minutos_se_ignora(agente, monkeypatch, sin_reboot):
    llamadas = []
    monkeypatch.setattr(agente, "_en_hilo", lambda accion, fn: llamadas.append(accion))
    ts, nonce = time.time() - 600, "n" * 32
    escribir(agente.PETICIONES / "copia.json", {"ts": ts, "nonce": nonce, "firma": firmar("copia", ts, nonce)})
    agente.revisar_peticiones(CLAVE)
    assert llamadas == [] and not (agente.PETICIONES / "copia.json").exists()
    assert sin_reboot == []


def test_archivo_con_nombre_desconocido_se_borra(agente, monkeypatch, sin_reboot):
    llamadas = []
    monkeypatch.setattr(agente, "_en_hilo", lambda accion, fn: llamadas.append(accion))
    desconocido = agente.PETICIONES / "inventario.json"
    desconocido.write_text(json.dumps({"ts": time.time(), "nonce": "n" * 32}), encoding="utf-8")
    agente.revisar_peticiones(CLAVE)
    assert llamadas == [] and not desconocido.exists()
    assert sin_reboot == []


# --- Vigilante del túnel ----------------------------------------------------------------------------------
def test_vigilar_tunel_accisible_marca_ok(agente, monkeypatch):
    monkeypatch.setattr(agente, "_publica_ok", lambda: True)
    ahora = time.time()
    agente.vigilar_tunel(ahora)
    d = estado(agente)
    assert d["estado"] == "ok" and d["ts"] == ahora and d["reinicios"] == []


def test_vigilar_tunel_sin_internet_no_reinicia(agente, monkeypatch, sin_reboot):
    llamadas = []
    monkeypatch.setattr(agente, "_en_hilo", lambda accion, fn: llamadas.append(accion))
    monkeypatch.setattr(agente, "_publica_ok", lambda: False)
    monkeypatch.setattr(agente, "_http_ok", lambda url: False)   # ni la página pública ni Cloudflare
    agente.vigilar_tunel(time.time())
    d = estado(agente)
    assert d["estado"] == "sin_internet"
    assert llamadas == [] and sin_reboot == [] and agente._vigilancia["reinicios"] == []


def test_vigilar_tunel_dos_fallos_seguidos_reinicia_una_vez(agente, monkeypatch):
    llamadas = []
    monkeypatch.setattr(agente, "_en_hilo", lambda accion, fn: llamadas.append(accion))
    monkeypatch.setattr(agente, "_publica_ok", lambda: False)
    monkeypatch.setattr(agente, "_http_ok", lambda url: True)    # hay internet: Cloudflare responde
    t = time.time()
    agente.vigilar_tunel(t)
    assert estado(agente)["estado"] == "caido"
    agente._vigilancia["ultima"] = 0.0
    agente.vigilar_tunel(t + 1)
    d = estado(agente)
    assert d["estado"] == "reiniciando" and d["fallos"] == 2
    assert llamadas == ["tunel"] and len(agente._vigilancia["reinicios"]) == 1


def test_vigilar_tunel_como_maximo_tres_reinicios_por_hora(agente, monkeypatch, sin_reboot):
    llamadas = []
    monkeypatch.setattr(agente, "_en_hilo", lambda accion, fn: llamadas.append(accion))
    monkeypatch.setattr(agente, "_publica_ok", lambda: False)
    monkeypatch.setattr(agente, "_http_ok", lambda url: True)
    base, estados = time.time(), []
    for i in range(6):
        agente._vigilancia["ultima"] = 0.0
        agente.vigilar_tunel(base + i * 300)   # 6 caídas en 25 minutos, dentro de la misma hora
        estados.append(estado(agente)["estado"])
    assert llamadas == ["tunel", "tunel", "tunel"]
    assert estados.count("reiniciando") == 3 and estados[-1] == "caido"
    assert len(agente._vigilancia["reinicios"]) == 3
    assert sin_reboot == []


# --- Notas de mejora → plan privado ------------------------------------------------------------------------
def test_volcar_notas_aniade_la_seccion_al_final(agente):
    plan = agente.PLAN_PRIVADO
    plan.write_text("# Plan de trabajo\n\nCosas del día.\n", encoding="utf-8")
    notas(agente, [{"id": 1, "texto": "Mejorar el iPad", "creado": "2026-10-12T08:00:00", "origen": "telegram"}],
          1_760_000_000)
    agente.volcar_notas()
    texto = plan.read_text(encoding="utf-8")
    assert texto.startswith("# Plan de trabajo\n\nCosas del día.")
    assert "- [ ] Mejorar el iPad" in texto
    assert MARCA_INI in texto and MARCA_FIN in texto
    assert texto.index("- [ ] Mejorar el iPad") < texto.index(MARCA_FIN)


def test_volcar_notas_solo_reemplaza_lo_de_entre_las_marcas(agente):
    plan = agente.PLAN_PRIVADO
    plan.write_text("# Plan de trabajo\n\nCosas sueltas.\n", encoding="utf-8")
    notas(agente, [{"id": 1, "texto": "Mejorar el iPad", "creado": "2026-10-12T08:00:00", "origen": "telegram"}],
          1_760_000_000)
    agente.volcar_notas()
    assert "- [ ] Mejorar el iPad" in plan.read_text(encoding="utf-8")
    with plan.open("a", encoding="utf-8") as f:
        f.write("\nLínea escrita fuera de las marcas.\n")
    notas(agente, [{"id": 2, "texto": "Añadir informe semanal", "creado": "2026-10-13T09:00:00", "origen": "web"}],
          1_760_000_600)
    agente.volcar_notas()
    texto = plan.read_text(encoding="utf-8")
    assert "Mejorar el iPad" not in texto
    assert "- [ ] Añadir informe semanal" in texto
    assert "Línea escrita fuera de las marcas." in texto and "Cosas sueltas." in texto
    assert texto.count(MARCA_INI) == 1 and texto.count(MARCA_FIN) == 1


def test_volcar_notas_lista_vacia_agota_las_pendientes(agente):
    plan = agente.PLAN_PRIVADO
    plan.write_text("# Plan de trabajo\n", encoding="utf-8")
    notas(agente, [], 1_760_000_000)
    agente.volcar_notas()
    texto = plan.read_text(encoding="utf-8")
    assert texto.startswith("# Plan de trabajo\n\n") and MARCA_INI in texto and MARCA_FIN in texto
    assert "Ninguna pendiente" in texto and "- [ ]" not in texto
