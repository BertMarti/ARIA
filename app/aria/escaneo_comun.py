"""Código común de la app y del contenedor `aria-escaner` (solo biblioteca estándar, sin imports de aria).

- `validar_objetivos`: guardia de red. Solo se aceptan IPv4 o CIDR DENTRO de la red permitida
  (por defecto 192.168.0.0/24, fijada en la configuración). Nada de nombres de host, IPv6,
  rangos con guion ni redes públicas.
- `parsear_nmap_xml`: salida `nmap -oX -` -> lista de hosts con puertos abiertos.
"""
import ipaddress
import re
import xml.etree.ElementTree as ET

RED_DEFECTO = "192.168.0.0/24"
PERFILES = {
    # nombre -> argumentos de nmap (fijos; nunca se concatenan cadenas del usuario)
    "rapido": ["-sS", "-sV", "--version-light", "--top-ports", "100", "-T4", "--max-retries", "2",
               "--host-timeout", "120s"],
    "completo": ["-sS", "-sV", "--top-ports", "1000", "-T4", "--max-retries", "2", "--host-timeout", "300s"],
}


class ObjetivoNoPermitido(ValueError):
    """Objetivo fuera de la red permitida."""


def red_permitida(texto: str | None) -> ipaddress.IPv4Network:
    """La red permitida debe ser IPv4 privada y no más grande que /16."""
    try:
        red = ipaddress.ip_network((texto or RED_DEFECTO).strip(), strict=True)
    except ValueError:
        raise ObjetivoNoPermitido("La red permitida configurada no es válida.") from None
    if red.version != 4 or not red.is_private or red.prefixlen < 16 or red.is_loopback:
        raise ObjetivoNoPermitido("La red permitida debe ser una red IPv4 privada de /16 o menor.")
    return red


def validar_objetivos(objetivos, permitida: str | None = None) -> list:
    """Devuelve los objetivos normalizados ('192.168.0.0/24', '192.168.0.10') o lanza ObjetivoNoPermitido."""
    red = red_permitida(permitida)
    if isinstance(objetivos, str):
        objetivos = [objetivos]
    if not isinstance(objetivos, (list, tuple)) or not objetivos or len(objetivos) > 32:
        raise ObjetivoNoPermitido("Indica entre 1 y 32 objetivos.")
    out = []
    for o in objetivos:
        s = str(o).strip()
        # solo dígitos, puntos y una barra: descarta nombres de host, IPv6, guiones y opciones de nmap
        if not re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}(/\d{1,2})?", s):
            raise ObjetivoNoPermitido(f"Objetivo no permitido: «{s[:40]}» (solo IPv4 o CIDR de {red}).")
        try:
            n = ipaddress.ip_network(s, strict=False)
        except ValueError:
            raise ObjetivoNoPermitido(f"Objetivo no válido: «{s[:40]}».") from None
        if n.version != 4 or not n.subnet_of(red):
            raise ObjetivoNoPermitido(f"Objetivo fuera de la red permitida ({red}): «{s}».")
        out.append(str(n.network_address) if n.prefixlen == 32 else str(n))
    return out


def parsear_nmap_xml(xml: str) -> dict:
    """XML de nmap -> {"hosts": [...], "inicio": ts, "fin": ts, "resumen": str}."""
    if "<!ENTITY" in xml:  # nmap nunca emite entidades; se rechazan por seguridad
        raise ValueError("XML no permitido")
    raiz = ET.fromstring(xml)
    hosts = []
    for h in raiz.findall("host"):
        estado = h.find("status")
        if estado is not None and estado.get("state") != "up":
            continue
        ip = mac = vendor = None
        for a in h.findall("address"):
            if a.get("addrtype") == "ipv4":
                ip = a.get("addr")
            elif a.get("addrtype") == "mac":
                mac, vendor = (a.get("addr") or "").upper() or None, a.get("vendor")
        if not ip:
            continue
        nombre = next((hn.get("name") for hn in h.findall("hostnames/hostname") if hn.get("name")), None)
        puertos = []
        for p in h.findall("ports/port"):
            st = p.find("state")
            if st is None or st.get("state") not in ("open", "open|filtered"):
                continue
            sv = p.find("service")
            cpes = [c.text for c in (sv.findall("cpe") if sv is not None else []) if c.text]
            puertos.append({
                "puerto": int(p.get("portid")), "proto": p.get("protocol"), "estado": st.get("state"),
                "servicio": sv.get("name") if sv is not None else None,
                "producto": sv.get("product") if sv is not None else None,
                "version": sv.get("version") if sv is not None else None,
                "extra": sv.get("extrainfo") if sv is not None else None,
                "cpe": cpes,
            })
        hosts.append({"ip": ip, "mac": mac, "fabricante": vendor, "nombre": nombre,
                      "puertos": sorted(puertos, key=lambda x: (x["proto"] or "", x["puerto"]))})
    fin = raiz.find("runstats/finished")
    return {"hosts": sorted(hosts, key=lambda x: tuple(int(p) for p in x["ip"].split("."))),
            "inicio": int(raiz.get("start") or 0), "fin": int(fin.get("time") or 0) if fin is not None else 0,
            "resumen": fin.get("summary") if fin is not None else ""}
