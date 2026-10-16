#!/usr/bin/env python3
"""Agente mínimo de ARIA en el sistema (fuera de Docker). Lo instala `sistema/instalar-host-agente.sh`.

ARIA corre aislada en un contenedor, sin socket de Docker ni permisos sobre la Raspberry. Este agente le da
exactamente estas capacidades, a través de su carpeta de datos (`data/host/`), y nada más:

1. **Telemetría** (cada 5 s): CPU, memoria y red por contenedor, y CPU, carga, temperatura y red del sistema,
   en `data/host/telemetria.json`. La memoria por contenedor se suma desde los procesos de su cgroup, porque
   la Raspberry Pi no tiene activada la contabilidad de memoria de los cgroups.
2. **Reinicio bajo petición**: si ARIA escribe `data/host/peticiones/reinicio.json` con `{ts, nonce, firma}`,
   donde firma = HMAC-SHA256(ARIA_SECRET, f"reiniciar:{ts}:{nonce}"), con menos de 120 s de antigüedad y un
   nonce no usado, el agente reinicia el sistema 15 s después (para que ARIA pueda despedirse).
   Cualquier otra cosa en esa carpeta se borra y se ignora.
3. **Copia de seguridad y túnel bajo petición** (mismo esquema de firma, con su propio nombre de acción):
   `peticiones/copia.json` arranca el servicio `homelab-copias.service` (la copia cifrada de siempre) y
   `peticiones/tunel.json` reinicia el contenedor del túnel de Cloudflare. El resultado queda en
   `data/host/resultados/<accion>.json`.
4. **Vigilante del túnel** (cada 2 min): pide la página pública `/hola` desde fuera, a través de Cloudflare. Si falla
   dos veces seguidas y hay internet, reinicia el túnel (como mucho 3 veces por hora). Estado en `data/host/tunel.json`.
5. **Notas → plan privado**: copia las notas de mejora que ARIA deja en `data/host/notas-mejoras.json` a una sección
   entre marcas de `PLAN-DE-TRABAJO.md` (fuera del repositorio público).

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
# Peticiones firmadas: archivo -> nombre de la acción en la firma HMAC
ACCIONES = {"reinicio.json": "reiniciar", "copia.json": "copia", "tunel.json": "tunel"}
RESULTADOS = HOST / "resultados"
SERVICIO_COPIAS = os.environ.get("ARIA_SERVICIO_COPIAS", "homelab-copias.service")
CONTENEDOR_TUNEL = os.environ.get("ARIA_CONTENEDOR_TUNEL", "cloudflare-tunnel")
PLAN_PRIVADO = Path(os.environ.get("ARIA_PLAN_PRIVADO", ARIA.parent / "PLAN-DE-TRABAJO.md"))
VIGILANCIA_S = 120
MARCA_INI, MARCA_FIN = "<!-- NOTAS-TELEGRAM:INICIO -->", "<!-- NOTAS-TELEGRAM:FIN -->"


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


# --- Peticiones firmadas -----------------------------------------------------------------------------
_usados: dict = {}
_en_curso: set = set()


def _resultado(accion: str, estado: str, detalle: str = "") -> None:
    RESULTADOS.mkdir(exist_ok=True)
    escribir(RESULTADOS / f"{accion}.json", {"ts": time.time(), "estado": estado, "detalle": detalle[:300]})


def _en_hilo(accion: str, fn) -> None:
    """Las acciones largas (copia, túnel) van en su hilo: la telemetría y el vigilante siguen."""
    import threading
    if accion in _en_curso:
        return
    _en_curso.add(accion)

    def correr():
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            _resultado(accion, "error", f"Error inesperado: {type(e).__name__}")
        finally:
            _en_curso.discard(accion)
    threading.Thread(target=correr, daemon=True).start()


def _copia() -> None:
    _resultado("copia", "en_curso", "Haciendo la copia cifrada…")
    r = subprocess.run(["systemctl", "start", SERVICIO_COPIAS], capture_output=True, text=True, timeout=1800, check=False)
    estado = subprocess.run(["systemctl", "show", SERVICIO_COPIAS, "-p", "Result", "--value"],
                            capture_output=True, text=True, timeout=20, check=False).stdout.strip()
    if r.returncode == 0 and estado == "success":
        _resultado("copia", "ok", "Copia cifrada hecha y subida.")
        return
    ultimas = subprocess.run(["journalctl", "-u", SERVICIO_COPIAS, "-n", "3", "-o", "cat", "--no-pager"],
                             capture_output=True, text=True, timeout=20, check=False).stdout.strip().splitlines()
    _resultado("copia", "error", (ultimas[-1] if ultimas else "La copia ha fallado.") + " (journalctl -u " + SERVICIO_COPIAS + ")")


def _reiniciar_tunel(motivo: str = "petición de ARIA") -> bool:
    _resultado("tunel", "en_curso", "Reiniciando el túnel…")
    r = subprocess.run(["docker", "restart", CONTENEDOR_TUNEL], capture_output=True, text=True, timeout=120, check=False)
    if r.returncode != 0:
        _resultado("tunel", "error", "No se pudo reiniciar el contenedor del túnel.")
        return False
    time.sleep(20)
    ok = _publica_ok()
    _resultado("tunel", "ok" if ok else "error",
               "Túnel reiniciado y respondiendo." if ok else "Túnel reiniciado, pero aún no responde desde fuera.")
    log(f"Túnel reiniciado ({motivo}): {'responde' if ok else 'sin respuesta'}")
    return ok


def revisar_peticiones(clave: bytes) -> None:
    for p in PETICIONES.iterdir():
        if p.suffix == ".tmp" or p.name.startswith("."):
            continue   # ARIA aún lo está escribiendo (escribe en .tmp y renombra)
        accion = ACCIONES.get(p.name)
        try:
            datos = json.loads(p.read_text(encoding="utf-8")) if accion else None
        except (OSError, ValueError):
            datos = None
        p.unlink(missing_ok=True)
        if not isinstance(datos, dict):
            continue
        ts, nonce, firma = datos.get("ts"), str(datos.get("nonce", "")), str(datos.get("firma", ""))
        if not isinstance(ts, (int, float)) or abs(time.time() - ts) > MAX_EDAD or not (16 <= len(nonce) <= 64):
            log(f"Petición «{accion}» caducada o mal formada: ignorada")
            continue
        esperada = hmac.new(clave, f"{accion}:{int(ts)}:{nonce}".encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(esperada, firma) or nonce in _usados:
            log(f"Petición «{accion}» con firma no válida o repetida: ignorada")
            continue
        _usados[nonce] = time.time()
        if accion == "reiniciar":
            escribir(HOST / "reinicio.json", {"programado": time.time() + 15})
            log("Reinicio solicitado por ARIA: en 15 s")
            time.sleep(15)
            subprocess.run(["systemctl", "reboot"], check=False)
        elif accion == "copia":
            log("Copia de seguridad solicitada por ARIA")
            _en_hilo("copia", _copia)
        elif accion == "tunel":
            log("Reinicio del túnel solicitado por ARIA")
            _en_hilo("tunel", _reiniciar_tunel)


# --- Vigilante del túnel ------------------------------------------------------------------------------
_vigilancia = {"fallos": 0, "reinicios": [], "ultima": 0.0, "caido_desde": None}


def _url_publica() -> str:
    try:
        for linea in (ARIA / ".env").read_text(encoding="utf-8").splitlines():
            if linea.startswith("ARIA_URL_PUBLICA="):
                u = linea.split("=", 1)[1].strip().rstrip("/")
                return u if u.startswith("https://") else ""
    except OSError:
        pass
    return ""


def _http_ok(url: str) -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "aria-host-agente"}), timeout=15) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


def _publica_ok() -> bool:
    u = _url_publica()
    return bool(u) and _http_ok(u + "/hola")


def vigilar_tunel(ahora: float) -> None:
    v = _vigilancia
    if ahora - v["ultima"] < VIGILANCIA_S or not _url_publica() or "tunel" in _en_curso:
        return
    v["ultima"] = ahora
    if _publica_ok():
        if v["caido_desde"]:
            log("Túnel de nuevo accesible desde fuera")
        v["fallos"], v["caido_desde"] = 0, None
        escribir(HOST / "tunel.json", {"ts": ahora, "estado": "ok", "reinicios": v["reinicios"][-5:]})
        return
    if not _http_ok("https://www.cloudflare.com/cdn-cgi/trace"):
        escribir(HOST / "tunel.json", {"ts": ahora, "estado": "sin_internet", "reinicios": v["reinicios"][-5:]})
        return   # sin internet en casa: reiniciar el túnel no arreglaría nada
    v["fallos"] += 1
    v["caido_desde"] = v["caido_desde"] or ahora
    v["reinicios"] = [t for t in v["reinicios"] if ahora - t < 3600]
    estado = "caido"
    if v["fallos"] >= 2 and len(v["reinicios"]) < 3:
        v["reinicios"].append(ahora)
        estado = "reiniciando"
        _en_hilo("tunel", lambda: _reiniciar_tunel("el vigilante lo vio caído"))
    escribir(HOST / "tunel.json", {"ts": ahora, "estado": estado, "caido_desde": v["caido_desde"], "fallos": v["fallos"],
                                    "reinicios": v["reinicios"][-5:]})


# --- Notas de mejora → plan privado -------------------------------------------------------------------
_notas_mtime = 0.0


def volcar_notas() -> None:
    """Reescribe la sección entre marcas de PLAN-DE-TRABAJO.md con las notas de mejora abiertas (solo si cambian)."""
    global _notas_mtime
    origen = HOST / "notas-mejoras.json"
    try:
        mtime = origen.stat().st_mtime
    except OSError:
        return
    if mtime == _notas_mtime or not PLAN_PRIVADO.is_file():
        return
    try:
        notas = json.loads(origen.read_text(encoding="utf-8"))
        notas = notas if isinstance(notas, list) else []
    except (OSError, ValueError):
        return
    lineas = [MARCA_INI, "## Notas y mejoras desde Telegram", "",
              "_Las escribe ARIA sola (comando /mejora o «apunta una mejora» en Telegram o en la web); no edites entre las marcas._", ""]
    for n in notas[:200]:
        if isinstance(n, dict) and n.get("texto"):
            texto = " ".join(str(n["texto"]).split())[:500]
            lineas.append(f"- [ ] {texto} _(n.º {n.get('id')}, {str(n.get('creado', ''))[:10]}, desde {n.get('origen', '?')})_")
    if not notas:
        lineas.append("_(Ninguna pendiente.)_")
    lineas.append(MARCA_FIN)
    bloque = "\n".join(lineas)
    texto = PLAN_PRIVADO.read_text(encoding="utf-8")
    if MARCA_INI in texto and MARCA_FIN in texto:
        a, b = texto.index(MARCA_INI), texto.index(MARCA_FIN) + len(MARCA_FIN)
        nuevo = texto[:a] + bloque + texto[b:]
    else:
        nuevo = texto.rstrip("\n") + "\n\n" + bloque + "\n"
    if nuevo != texto:
        PLAN_PRIVADO.write_text(nuevo, encoding="utf-8")   # en el sitio: el servicio solo puede escribir este archivo
        log(f"Plan privado actualizado con {len(notas)} nota(s) de mejora")
    _notas_mtime = mtime


def main() -> None:
    HOST.mkdir(parents=True, exist_ok=True)
    PETICIONES.mkdir(exist_ok=True)
    uid, gid = ARIA.stat().st_uid, ARIA.stat().st_gid
    os.chown(HOST, uid, gid); os.chown(PETICIONES, uid, gid)   # ARIA (mismo usuario) escribe peticiones
    os.chmod(PETICIONES, 0o770)
    (HOST / "reinicio.json").unlink(missing_ok=True)
    RESULTADOS.mkdir(exist_ok=True)
    os.chown(RESULTADOS, uid, gid)
    clave = secreto()
    cpu_ant, red_ant, t_ant = _cpu_total(), _red_sistema(), time.monotonic()
    log(f"host-agente listo en {HOST}")
    while True:
        time.sleep(INTERVALO)
        try:
            revisar_peticiones(clave)
            vigilar_tunel(time.time())
            volcar_notas()
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
