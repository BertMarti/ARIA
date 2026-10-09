"""Datos INVENTADOS para la ARIA de demostración (capturas del README y pruebas visuales). Nada real.

Se ejecuta dentro del contenedor de la demo (lo hace `arrancar.sh --sembrar`)."""
import json
import time
from contextlib import closing
from datetime import datetime, timedelta

from aria import (agenda, automatizaciones, avisos, config, db, finanzas, informacion, memoria, proyectos,
                  recordatorios, red, rutinas, usuarios)

for m in (db, usuarios, finanzas, red, avisos, recordatorios, agenda):
    getattr(m, "iniciar", lambda: None)()
for m in (rutinas, automatizaciones, informacion, proyectos):
    getattr(m, "iniciar", lambda: None)()

ana = usuarios.por_identificador(config.USER)
uid = ana["id"]
ahora = datetime.now()
hoy = ahora.date()

# Red: dispositivos ficticios
dispositivos = [("02:1A:2B:00:00:01", "192.168.1.1", "Router", "Sagemcom", 1),
                ("02:1A:2B:00:00:20", "192.168.1.20", "Portátil de Ana", "Lenovo", 1),
                ("02:1A:2B:00:00:21", "192.168.1.21", "Móvil de Ana", "Apple", 1),
                ("02:1A:2B:00:00:22", "192.168.1.22", "Móvil de Lucía", "Samsung", 1),
                ("02:1A:2B:00:00:30", "192.168.1.30", "Tele del salón", "LG", 1),
                ("02:1A:2B:00:00:31", "192.168.1.31", "Impresora del estudio", "HP", 1),
                ("02:1A:2B:00:00:41", "192.168.1.41", "Tablet de Lucía", "Lenovo", 1),
                ("02:1A:2B:00:00:45", "192.168.1.45", None, "Espressif", 0),
                ("02:1A:2B:00:00:50", "192.168.1.50", "Servidor ARIA", "Raspberry Pi", 1)]
with closing(db._con()) as con, con:
    for mac, ip, alias, fab, conocido in dispositivos:
        con.execute("INSERT OR REPLACE INTO red_inventario (clave, mac, ip, nombre, fabricante, alias, conocido, primera_vez, "
                    "ultima_vez) VALUES (?,?,?,?,?,?,?,?,?)", (mac, mac, ip, None, fab, alias, conocido, time.time() - 86400 * 30,
                                                           time.time()))

# Agenda y cumpleaños
def f(d, h):
    return (ahora + timedelta(days=d)).strftime(f"%Y-%m-%dT{h}")


for t, d, h, fin, rep, lugar in [("Dentista", 0, "17:30", "18:15", "ninguna", "Clínica Centro"), ("Clase de inglés", 0, "20:00", "21:00", "semanal", "Online"),
                                 ("Recoger a Lucía", 1, "17:00", None, "ninguna", "Colegio"), ("Compra semanal", 2, "11:00", None, "semanal", "Mercado"),
                                 ("Vacaciones en Lisboa", 12, "00:00", None, "ninguna", "Lisboa"), ("ITV del coche", -3, "09:30", None, "ninguna", "Estación ITV"),
                                 ("Comida familiar", 6, "14:00", "17:00", "ninguna", "Casa de los abuelos"), ("Pagar el alquiler", -8, "09:00", None, "mensual", "")]:
    agenda.crear_evento(uid, {"titulo": t, "inicio": f(d, h), "fin": f(d, fin) if fin else None, "repeticion": rep, "lugar": lugar,
                              "aviso_min": 30, "todo_el_dia": t.startswith("Vacaciones")})

for nombre, delta, anio in [("Lucía", 3, 1994), ("Papá", 12, 1962), ("Carmen", 27, 1990)]:
    c = hoy + timedelta(days=delta)
    agenda.crear_cumple(uid, {"nombre": nombre, "dia": c.day, "mes": c.month, "anio": anio})

# Finanzas
for dias, concepto, importe, cat in [(1, "Supermercado del barrio", -64.20, "Supermercado"), (2, "Gasolinera", -48.00, "Transporte"),
                                     (3, "Nómina", 1850.00, "Ingresos"), (4, "Alquiler", -650.00, "Vivienda"),
                                     (5, "Luz", -41.30, "Suministros"), (6, "Restaurante", -42.50, "Restaurantes"),
                                     (8, "Plataforma de música", -10.99, "Suscripciones"), (9, "Farmacia", -12.80, "Salud")]:
    finanzas.registrar(uid, (hoy - timedelta(days=dias)).isoformat(), concepto, importe, cat)
for cat, imp in [("Supermercado", 300), ("Restaurantes", 120), ("Ocio", 60)]:
    finanzas.fijar_presupuesto(uid, cat, imp)

# Memoria, proyectos y decisiones
for t in ("Ana prefiere respuestas cortas", "Los viernes cena fuera", "Su equipo favorito es el de su ciudad"):
    memoria.anadir(uid, t)
p1 = proyectos.crear(uid, "Huerto en la terraza", "Tomates y aromáticas en macetas", "en_curso")
proyectos.registrar_decision(uid, p1["id"], "Riego por goteo automático", "Vacaciones de verano")
p2 = proyectos.crear(uid, "Viaje a Lisboa", "Puente de diciembre", "idea")
proyectos.registrar_decision(uid, p2["id"], "Ir en tren", "Más cómodo que conducir")

# Recordatorios, rutinas y automatizaciones
recordatorios.crear(uid, "Sacar la basura", (ahora + timedelta(hours=3)).isoformat(timespec="minutes"))
rutinas.crear(uid, "admin", {"nombre": "Resumen de la mañana", "prompt": "Dime el tiempo de hoy y tres titulares",
                             "agente": "aria", "canal": "ambos", "horario": "de lunes a viernes a las 8:00"})
for datos in automatizaciones.plantillas() if hasattr(automatizaciones, "plantillas") else []:
    try:
        automatizaciones.crear(uid, datos)
    except Exception:
        pass

# Inversiones (ficticias, sin cantidades reales)
for s, n in (("^IBEX", "IBEX 35"), ("^GSPC", "S&P 500"), ("bitcoin", "Bitcoin")):
    try:
        informacion.anadir_valor(uid, s, n)
    except Exception as e:
        print("valor", s, e)

# Avisos de ejemplo
for tipo, sev, texto in [("dispositivo_nuevo", "aviso", "Dispositivo desconocido en la red: 192.168.1.45 (Espressif)."),
                         ("vpn_conexion", "info", "VPN: «movil-ana» se ha conectado."),
                         ("agenda", "info", "En 30 minutos: Dentista (Clínica Centro).")]:
    avisos._insertar(uid, tipo, sev, texto, "")
print("sembrado")
