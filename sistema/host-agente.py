#!/usr/bin/env python3
"""Agente mínimo de ARIA en el sistema (fuera de Docker). Lo instala `sistema/instalar-host-agente.sh`.

ARIA corre aislada en un contenedor, sin socket de Docker ni permisos sobre la Raspberry. Este agente le da
exactamente dos capacidades, a través de su carpeta de datos (`data/host/`), y nada más:

1. **Telemetría** (cada 5 s): CPU, memoria y red por contenedor, y CPU, carga, temperatura y red del sistema,
   en `data/host/telemetria.json`. La memoria por contenedor se suma desde los procesos de su cgroup, porque
   la Raspberry Pi no tiene activada la contabilidad de memoria de los cgroups.
2. **Reinicio bajo petición**: si ARIA escribe `data/host/peticiones/reinicio.json` con `{ts, nonce, firma}`,
   donde firma = HMAC-SHA256(ARIA_SECRET, f"reiniciar:{ts}:{nonce}"), con menos de 120 s de antigüedad y un
   nonce no usado, el agente reinicia el sistema 15 s después (para que ARIA pueda despedirse).
   Cualquier otra cosa en esa carpeta se borra y se ignora.

Solo usa la biblioteca estándar y la orden `docker`.
"""
import hashlib
import hmac
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ARIA = Path(os.environ.get("ARIA_DIR", Path(__file__).resolve().parent.parent))
HOST = ARIA / "data" / "host"
PETICIONES = HOST / "peticiones"
INTERVALO = 5
MAX_EDAD = 120


def log(msg: str) -> None:
    print(msg, flush=True)


def secreto() -> bytes:
    for linea in (ARIA / ".env").read_text(encoding="utf-8").splitlines():
        if linea.startswith("ARIA_SECRET="):
            return linea.split("=", 1)[1].strip().encode()
    raise SystemExit("Falta ARIA_SECRET en .env")


def escribir(ruta: Path, datos) -> None:
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos), encoding="utf-8")
    os.chmod(tmp, 0o644)
    tmp.replace(ruta)


# --- Telemetría ------------------------------------------------------------------------------------
def _cpu_total() -> tuple[int, int]:
    p = [int(x) for x in Path("/proc/stat").read_text().split("\n", 1)[0].split()[1:]]
    return sum(p), p[3] + p[4]


def _red_sistema() -> tuple[int, int]:
    rx = tx = 0
    for linea in Path("/proc/net/dev").read_text().splitlines()[2:]:
        nombre, datos = linea.split(":", 1)
        if nombre.strip() in ("eth0", "wlan0"):
            c = datos.split()
            rx += int(c[0]); tx += int(c[8])
    return rx, tx


def _temperatura() -> float | None:
    try:
        return round(int(Path("/sys/class/thermal/thermal_zone0/temp").read_text()) / 1000, 1)
    except (OSError, ValueError):
        return None


def _rss_cgroup(id_largo: str) -> int | None:
    for base in (f"/sys/fs/cgroup/system.slice/docker-{id_largo}.scope", f"/sys/fs/cgroup/docker/{id_largo}"):
        procs = Path(base) / "cgroup.procs"
        if procs.exists():
            total = 0
            for pid in procs.read_text().split():
                try:
                    for linea in Path(f"/proc/{pid}/status").read_text().splitlines():
                        if linea.startswith("VmRSS:"):
                            total += int(linea.split()[1]) * 1024
                            break
                except OSError:
                    continue
            return total
    return None


def _a_bytes(texto: str) -> int:
    texto = texto.strip()
    unidades = {"B": 1, "kB": 1000, "KB": 1000, "MB": 1000 ** 2, "GB": 1000 ** 3, "KiB": 1024, "MiB": 1024 ** 2,
                "GiB": 1024 ** 3}
    for u in sorted(unidades, key=len, reverse=True):
        if texto.endswith(u):
            try:
                return int(float(texto[: -len(u)]) * unidades[u])
            except ValueError:
                return 0
    return 0


def contenedores() -> list:
    r = subprocess.run(["docker", "stats", "--no-stream", "--no-trunc", "--format", "{{json .}}"],
                       capture_output=True, text=True, timeout=30)
    out = []
    for linea in r.stdout.splitlines():
        try:
            c = json.loads(linea)
        except ValueError:
            continue
        rx, _, tx = c.get("NetIO", "0B / 0B").partition("/")
        out.append({"nombre": c.get("Name"), "cpu": float(c.get("CPUPerc", "0%").rstrip("%") or 0),
                    "memoria": _rss_cgroup(c.get("Container") or c.get("ID", "")),
                    "red_rx": _a_bytes(rx), "red_tx": _a_bytes(tx), "procesos": int(c.get("PIDs") or 0)})
    return sorted(out, key=lambda x: x["nombre"] or "")


# --- Reinicio ----------------------------------------------------------------------------------------
_usados: dict = {}


def revisar_peticiones(clave: bytes) -> None:
    for p in PETICIONES.iterdir():
        if p.suffix == ".tmp" or p.name.startswith("."):
            continue   # ARIA aún lo está escribiendo (escribe en .tmp y renombra)
        try:
            datos = json.loads(p.read_text(encoding="utf-8")) if p.name == "reinicio.json" else None
        except (OSError, ValueError):
            datos = None
        p.unlink(missing_ok=True)
        if not isinstance(datos, dict):
            continue
        ts, nonce, firma = datos.get("ts"), str(datos.get("nonce", "")), str(datos.get("firma", ""))
        if not isinstance(ts, (int, float)) or abs(time.time() - ts) > MAX_EDAD or not (16 <= len(nonce) <= 64):
            log("Petición de reinicio caducada o mal formada: ignorada")
            continue
        esperada = hmac.new(clave, f"reiniciar:{int(ts)}:{nonce}".encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(esperada, firma) or nonce in _usados:
            log("Petición de reinicio con firma no válida o repetida: ignorada")
            continue
        _usados[nonce] = time.time()
        escribir(HOST / "reinicio.json", {"programado": time.time() + 15})
        log("Reinicio solicitado por ARIA: en 15 s")
        time.sleep(15)
        subprocess.run(["systemctl", "reboot"], check=False)


def main() -> None:
    HOST.mkdir(parents=True, exist_ok=True)
    PETICIONES.mkdir(exist_ok=True)
    uid, gid = ARIA.stat().st_uid, ARIA.stat().st_gid
    os.chown(HOST, uid, gid); os.chown(PETICIONES, uid, gid)   # ARIA (mismo usuario) escribe peticiones
    os.chmod(PETICIONES, 0o770)
    (HOST / "reinicio.json").unlink(missing_ok=True)
    clave = secreto()
    cpu_ant, red_ant, t_ant = _cpu_total(), _red_sistema(), time.monotonic()
    log(f"host-agente listo en {HOST}")
    while True:
        time.sleep(INTERVALO)
        try:
            revisar_peticiones(clave)
            for n, t in list(_usados.items()):
                if time.time() - t > 3600:
                    del _usados[n]
            cpu, red, ahora = _cpu_total(), _red_sistema(), time.monotonic()
            dt = max(ahora - t_ant, 0.1)
            total, ocio = cpu[0] - cpu_ant[0], cpu[1] - cpu_ant[1]
            escribir(HOST / "telemetria.json", {
                "ts": time.time(),
                "sistema": {"cpu": round(100 * (1 - ocio / total), 1) if total else 0.0,
                            "carga": os.getloadavg(), "temperatura": _temperatura(),
                            "red_rx_bps": int((red[0] - red_ant[0]) / dt), "red_tx_bps": int((red[1] - red_ant[1]) / dt)},
                "contenedores": contenedores()})
            cpu_ant, red_ant, t_ant = cpu, red, ahora
        except Exception as e:  # noqa: BLE001 - el agente no debe morir por un fallo puntual
            log(f"Error: {e}")


if __name__ == "__main__":
    sys.exit(main())
