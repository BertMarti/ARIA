"""Comprobación CSRF por Origin / Sec-Fetch-Site / Referer."""
from urllib.parse import urlparse


def origen_permitido(origin: str | None, host: str | None, sec_fetch_site: str | None, referer: str | None) -> bool:
    if sec_fetch_site == "cross-site":
        return False
    if origin is None:
        return True
    if origin == "null":
        # Algunos navegadores envían "null" en formularios same-origin si hay Referrer-Policy estricta.
        if sec_fetch_site == "same-origin":
            return True
        if sec_fetch_site is None and referer:
            return urlparse(referer).netloc == host
        return False
    return urlparse(origin).netloc == host
