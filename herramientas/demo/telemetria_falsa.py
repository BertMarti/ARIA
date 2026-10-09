"""Escribe cada 4 s una telemetría inventada en /data/host/telemetria.json (como el agente real del host)."""
import json
import math
import random
import time
from pathlib import Path

h = Path("/data/host"); h.mkdir(parents=True, exist_ok=True)
esc = Path("/data/escaner"); esc.mkdir(parents=True, exist_ok=True)
VECINOS = {f"192.168.1.{n}": f"02:1A:2B:00:00:{n:02d}" for n in (1, 20, 21, 22, 30, 31, 41, 45)}
nombres = ["aria-app", "aria-caddy", "aria-ollama", "aria-searxng", "aria-voz", "aria-escaner", "shield-pihole",
           "shield-unbound", "heimdall-wg", "heimdall-caddy", "cloudflare-tunnel"]
base = {n: (random.uniform(0.2, 6), random.uniform(20, 160) * 2**20) for n in nombres}
t0 = time.time()
while True:
    t = time.time() - t0
    cs = [{"nombre": n, "cpu": round(max(0.0, c + math.sin(t / 7 + i) * c * 0.6), 2), "memoria": int(m * (1 + 0.05 * math.sin(t / 11 + i))),
           "red_rx": int(1e6 * (i + 1) + t * 900), "red_tx": int(5e5 * (i + 1) + t * 400), "procesos": 3 + i}
          for i, (n, (c, m)) in enumerate(base.items())]
    d = {"ts": time.time(), "sistema": {"cpu": round(18 + 9 * math.sin(t / 9), 1), "carga": [0.9, 0.8, 0.7],
                                        "temperatura": round(49 + 3 * math.sin(t / 13), 1), "red_rx_bps": 42000, "red_tx_bps": 18000},
         "contenedores": cs}
    tmp = h / "telemetria.tmp"; tmp.write_text(json.dumps(d)); tmp.replace(h / "telemetria.json")
    t2 = esc / "vecinos.tmp"; t2.write_text(json.dumps({"ts": time.time(), "vecinos": VECINOS})); t2.replace(esc / "vecinos.json")
    time.sleep(4)
