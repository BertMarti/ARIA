"""Vulnerabilidades conocidas de las versiones que detecta `nmap -sV`, con APIs públicas y gratuitas.

- OSV.dev (`POST https://api.osv.dev/v1/query`, sin clave): cuando el banner indica un paquete de
  Debian con su revisión («OpenSSH 9.2p1 Debian 2+deb12u3») se consulta el ecosistema `Debian:<n>`.
- NVD 2.0 (`GET https://services.nvd.nist.gov/rest/json/cves/2.0?virtualMatchString=...`, sin clave):
  para el resto, con el CPE de nmap (producto + versión). Sin clave NVD permite ~5 peticiones/30 s:
  se espera 6 s entre peticiones y se limita el número por informe.
Los resultados se guardan 7 días en `seg_cve_cache` (data/aria.db). Solo se envían a esas APIs
nombres de producto y versiones, nunca IPs ni nada de la red.
"""
import asyncio
import json
import re
import time
from contextlib import closing

import httpx

from . import db

OSV_URL = "https://api.osv.dev/v1/query"
NVD_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
CACHE_S = 7 * 86400
ESPERA_NVD_S = 6.5

# producto de nmap -> (paquete Debian, epoch)
DEBIAN = {"openssh": ("openssh", "1:"), "apache httpd": ("apache2", ""), "nginx": ("nginx", ""),
          "lighttpd": ("lighttpd", ""), "samba smbd": ("samba", "2:"), "dnsmasq": ("dnsmasq", ""),
          "postfix smtpd": ("postfix", ""), "proftpd": ("proftpd-dfsg", ""), "vsftpd": ("vsftpd", ""),
          "dropbear sshd": ("dropbear", ""), "isc bind": ("bind9", "1:"), "exim smtpd": ("exim4", "")}

_ultimo_nvd = 0.0


def iniciar() -> None:
    with closing(db._con()) as con, con:
        con.execute("CREATE TABLE IF NOT EXISTS seg_cve_cache (clave TEXT PRIMARY KEY, ts REAL NOT NULL, datos TEXT NOT NULL)")


def consulta_para(servicio: dict) -> dict | None:
    """Servicio de nmap -> {"fuente": "osv"|"nvd", ...} o None si no hay versión fiable."""
    prod = (servicio.get("producto") or "").strip()
    ver = (servicio.get("version") or "").strip()
    if not prod or not ver:
        return None
    m = re.match(r"^(\S+)\s+Debian\s+(\S*deb(\d+)u\d+\S*)$", ver)
    pk = DEBIAN.get(prod.lower())
    if m and pk:
        return {"fuente": "osv", "ecosistema": f"Debian:{m.group(3)}", "paquete": pk[0],
                "version": f"{pk[1]}{m.group(1)}-{m.group(2)}", "clave": f"osv|Debian:{m.group(3)}|{pk[0]}|{m.group(1)}-{m.group(2)}"}
    for cpe in servicio.get("cpe") or []:
        p = cpe.removeprefix("cpe:/").split(":")
        if len(p) >= 4 and p[0] in ("a", "o", "h") and re.fullmatch(r"[\w.\-]+", p[3] or ""):
            c23 = f"cpe:2.3:{p[0]}:{p[1]}:{p[2]}:{p[3]}"
            return {"fuente": "nvd", "cpe": c23, "clave": f"nvd|{c23}"}
    return None


def _cache_leer(clave: str):
    with closing(db._con()) as con:
        r = con.execute("SELECT ts, datos FROM seg_cve_cache WHERE clave=?", (clave,)).fetchone()
    if r and time.time() - r["ts"] < CACHE_S:
        return json.loads(r["datos"])
    return None


def _cache_guardar(clave: str, datos: list) -> None:
    with closing(db._con()) as con, con:
        con.execute("INSERT OR REPLACE INTO seg_cve_cache (clave, ts, datos) VALUES (?,?,?)",
                    (clave, time.time(), json.dumps(datos)))


def _gravedad_cvss(v: float | None) -> str:
    if v is None:  # sin puntuación (p. ej. avisos de Debian ya mitigados o sin importancia)
        return "baja"
    return "alta" if v >= 7 else "media" if v >= 4 else "baja"


def parsear_osv(j: dict) -> list:
    out = []
    for v in (j or {}).get("vulns") or []:
        alias = [a for a in v.get("aliases") or [] if a.startswith("CVE-")]
        sev = None
        for s in v.get("severity") or []:
            m = re.search(r"(\d+(\.\d+)?)$", str(s.get("score", "")))
            if m and s.get("type", "").startswith("CVSS") and "/" not in m.group(1):
                sev = float(m.group(1))
        out.append({"id": (alias or [v.get("id")])[0], "osv": v.get("id"),
                    "resumen": (v.get("summary") or v.get("details") or "")[:200], "cvss": sev,
                    "gravedad": _gravedad_cvss(sev)})
    return out


def parsear_nvd(j: dict) -> list:
    out = []
    for item in (j or {}).get("vulnerabilities") or []:
        c = item.get("cve") or {}
        cvss = None
        for k in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
            ms = (c.get("metrics") or {}).get(k) or []
            if ms:
                cvss = ms[0].get("cvssData", {}).get("baseScore")
                break
        desc = next((d.get("value") for d in c.get("descriptions") or [] if d.get("lang") == "en"), "")
        out.append({"id": c.get("id"), "resumen": (desc or "")[:200], "cvss": cvss, "gravedad": _gravedad_cvss(cvss)})
    return out


async def _post_osv(cuerpo: dict) -> dict:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(OSV_URL, json=cuerpo)
        r.raise_for_status()
        return r.json()


async def _get_nvd(cpe: str) -> dict:
    global _ultimo_nvd
    espera = ESPERA_NVD_S - (time.time() - _ultimo_nvd)
    if espera > 0:
        await asyncio.sleep(espera)
    _ultimo_nvd = time.time()
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(NVD_URL, params={"virtualMatchString": cpe, "resultsPerPage": 50})
        r.raise_for_status()
        return r.json()


async def buscar(servicio: dict, permitir_red: bool = True) -> dict | None:
    """{"fuente", "vulns": [...]} desde la caché o la API. None si no se puede consultar."""
    q = consulta_para(servicio)
    if not q:
        return None
    en_cache = await asyncio.to_thread(_cache_leer, q["clave"])
    if en_cache is not None:
        return {"fuente": q["fuente"], "vulns": en_cache, "cache": True}
    if not permitir_red:
        return None
    try:
        if q["fuente"] == "osv":
            vulns = parsear_osv(await _post_osv({"package": {"name": q["paquete"], "ecosystem": q["ecosistema"]},
                                                 "version": q["version"]}))
        else:
            vulns = parsear_nvd(await _get_nvd(q["cpe"]))
    except (httpx.HTTPError, ValueError):
        return None
    vulns.sort(key=lambda v: -(v["cvss"] or 0))
    await asyncio.to_thread(_cache_guardar, q["clave"], vulns)
    return {"fuente": q["fuente"], "vulns": vulns, "cache": False}
