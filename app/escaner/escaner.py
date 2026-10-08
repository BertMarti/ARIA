"""aria-escaner: atiende peticiones de escaneo de ARIA (volumen compartido /escaner).

Seguridad:
- Solo escanea IPv4/CIDR dentro de ARIA_RED_PERMITIDA (192.168.0.0/24 por defecto); lo vuelve a
  comprobar aquí aunque la app ya lo haya hecho. Nombres de host, IPv6 y redes públicas se rechazan.
- Argumentos de nmap fijos por perfil (`escaneo_comun.PERFILES`); nada del usuario llega a la línea
  de órdenes salvo los objetivos validados, y nunca a través de un shell.
- Como mucho un escaneo bajo demanda cada 10 minutos, más uno programado a la semana.
- Solo descubrimiento y versiones (-sS -sV). Sin scripts NSE de intrusión, sin fuerza bruta, sin exploits.
"""
import ipaddress
import json
import os
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

from escaneo_comun import PERFILES, ObjetivoNoPermitido, parsear_nmap_xml, red_permitida, validar_objetivos

DIR = Path(os.environ.get("ESCANER_DIR", "/escaner"))
RED = os.environ.get("ARIA_RED_PERMITIDA", "192.168.0.0/24")
ROUTER = os.environ.get("ARIA_ROUTER_IP", "192.168.0.1")
DIA = int(os.environ.get("ESCANER_DIA", "6"))      # 0 = lunes ... 6 = domingo
HORA = int(os.environ.get("ESCANER_HORA", "4"))
PROGRAMADO = os.environ.get("ESCANER_PROGRAMADO", "1") == "1"
INTERVALO_MIN_S = 10 * 60
TIEMPO_MAX_S = 45 * 60
GUARDAR = 20

os.umask(0o027)


def escribir(ruta: Path, datos) -> None:
    tmp = ruta.with_name("." + ruta.name + ".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False))
    os.chmod(tmp, 0o640)
    tmp.replace(ruta)


def leer(ruta: Path, defecto=None):
    try:
        return json.loads(ruta.read_text())
    except (OSError, ValueError):
        return defecto


def proximo_programado(desde: datetime) -> float:
    d = desde.replace(hour=HORA, minute=0, second=0, microsecond=0) + timedelta(days=(DIA - desde.weekday()) % 7)
    if d <= desde:
        d += timedelta(days=7)
    return d.timestamp()


def nmap(args: list, timeout: int) -> str:
    r = subprocess.run(["nmap", "-oX", "-", *args], capture_output=True, text=True, timeout=timeout, check=False)
    if r.returncode != 0 and "<nmaprun" not in r.stdout:
        raise RuntimeError((r.stderr or "nmap falló").strip()[:300])
    return r.stdout


def escanear(pet: dict, estado: dict) -> dict:
    res = {"id": pet["id"], "perfil": pet.get("perfil"), "origen": pet.get("origen", "manual"),
           "objetivos": pet.get("objetivos"), "inicio": int(time.time()), "fin": None, "hosts": [], "error": None}
    try:
        objetivos = validar_objetivos(pet.get("objetivos") or [RED], RED)
        if pet.get("perfil") not in PERFILES:
            raise ObjetivoNoPermitido("Perfil desconocido.")
        if res["origen"] != "programado" and time.time() - estado.get("ultimo_bajo_demanda", 0) < INTERVALO_MIN_S:
            raise ObjetivoNoPermitido("Límite: un escaneo bajo demanda cada 10 minutos.")
        if res["origen"] != "programado":
            estado["ultimo_bajo_demanda"] = time.time()
        estado["en_curso"] = {"id": pet["id"], "desde": time.time()}
        escribir(DIR / "estado.json", estado)
        datos = parsear_nmap_xml(nmap([*PERFILES[pet["perfil"]], *objetivos], TIEMPO_MAX_S))
        res["hosts"] = datos["hosts"]
        res["resumen"] = datos["resumen"]
        # UPnP/NAT-PMP del router (UDP): solo si el router está dentro de lo pedido
        if any(ipaddress.ip_address(ROUTER) in ipaddress.ip_network(o) for o in objetivos):
            try:
                udp = parsear_nmap_xml(nmap(["-sU", "-p", "1900,5351", "--max-retries", "2", ROUTER], 120))
                res["udp_router"] = [{"puerto": p["puerto"], "estado": p["estado"]}
                                     for h in udp["hosts"] for p in h["puertos"]]
            except (RuntimeError, subprocess.TimeoutExpired, ValueError):
                res["udp_router"] = []
    except (ObjetivoNoPermitido, RuntimeError, subprocess.TimeoutExpired, ValueError) as e:
        res["error"] = str(e) if not isinstance(e, subprocess.TimeoutExpired) else "El escaneo superó el tiempo máximo."
        estado["ultimo_error"] = res["error"]
    res["fin"] = int(time.time())
    estado["en_curso"] = None
    return res


def vecinos() -> dict:
    """IP -> MAC de la tabla ARP del sistema (red de la casa, entradas completas). Pasivo: no envía nada."""
    red = ipaddress.ip_network(RED, strict=False)
    out = {}
    try:
        lineas = Path("/proc/net/arp").read_text().splitlines()[1:]
    except OSError:
        return out
    for linea in lineas:
        p = linea.split()
        if len(p) < 4 or p[2] != "0x2" or p[3] == "00:00:00:00:00:00":
            continue
        try:
            if ipaddress.ip_address(p[0]) in red:
                out[p[0]] = p[3].upper()
        except ValueError:
            continue
    return out


def limpiar() -> None:
    viejos = sorted((DIR / "resultados").glob("*.json"))[:-GUARDAR]
    for p in viejos:
        p.unlink(missing_ok=True)


def main() -> None:
    red_permitida(RED)  # falla al arrancar si la red configurada no es privada
    for d in ("peticiones", "resultados"):
        (DIR / d).mkdir(exist_ok=True)
        try:
            os.chmod(DIR / d, 0o2770)  # la app (mismo grupo) escribe peticiones y lee resultados
        except PermissionError:
            pass  # la creó la app y ya le dio estos permisos
    estado = leer(DIR / "estado.json", {}) or {}
    estado["en_curso"] = None
    if PROGRAMADO and not estado.get("siguiente_programado"):
        estado["siguiente_programado"] = proximo_programado(datetime.now())
    print(f"aria-escaner listo; red permitida {RED}", flush=True)
    ultimos_vecinos = 0.0
    while True:
        if time.time() - ultimos_vecinos >= 60:  # para que ARIA siga a los dispositivos aunque cambien de IP
            escribir(DIR / "vecinos.json", {"ts": time.time(), "vecinos": vecinos()})
            ultimos_vecinos = time.time()
        estado["latido"] = time.time()
        pet = None
        pendientes = sorted((DIR / "peticiones").glob("*.json"))
        if pendientes:
            ruta = pendientes[0]
            pet = leer(ruta)
            try:
                ruta.unlink(missing_ok=True)
            except OSError as e:
                print(f"no puedo borrar la petición: {e}", flush=True)
                estado["ultimo_error"] = "Permisos del volumen compartido incorrectos."
                pet = None
                time.sleep(30)
            if not isinstance(pet, dict) or not str(pet.get("id", "")).replace("-", "").isalnum():
                pet = None
        elif PROGRAMADO and time.time() >= estado.get("siguiente_programado", 0):
            pet = {"id": time.strftime("%Y%m%d-%H%M%S") + "-prog", "perfil": "rapido", "objetivos": [RED],
                   "origen": "programado"}
            estado["siguiente_programado"] = proximo_programado(datetime.now() + timedelta(minutes=1))
        if pet:
            print(f"escaneo {pet['id']} ({pet.get('origen')})", flush=True)
            res = escanear(pet, estado)
            escribir(DIR / "resultados" / f"{pet['id']}.json", res)
            print(f"fin {pet['id']}: {len(res['hosts'])} equipos, error={bool(res['error'])}", flush=True)
            limpiar()
        escribir(DIR / "estado.json", estado)
        time.sleep(5)


if __name__ == "__main__":
    main()
