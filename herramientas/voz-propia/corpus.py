"""Frases en español (de España) para entrenar la voz propia de ARIA.

Mezcla frases escritas a mano (conversación cálida, todos los sonidos del español) con plantillas del día a día
de ARIA: tiempo, horas, fechas, dinero, avisos, agenda, la casa. Sale siempre igual (semilla fija).

Uso: python3 corpus.py [cantidad] > corpus.txt      (por defecto, 1400 frases; como mucho ~1400)
"""
import random
import sys

NUMEROS = ["cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez", "once", "doce",
           "trece", "catorce", "quince", "dieciséis", "diecisiete", "dieciocho", "diecinueve", "veinte", "veintiuno",
           "veintidós", "veintitrés", "veinticuatro", "veinticinco", "veintiséis", "veintisiete", "veintiocho",
           "veintinueve", "treinta", "treinta y uno", "treinta y dos", "treinta y cinco", "cuarenta"]
HORAS = ["la una", "las dos", "las tres", "las cuatro", "las cinco", "las seis", "las siete", "las ocho", "las nueve",
         "las diez", "las once", "las doce"]
MINUTOS = ["en punto", "y cinco", "y diez", "y cuarto", "y veinte", "y media", "menos veinte", "menos cuarto",
           "menos diez", "menos cinco"]
PARTE_DIA = ["de la mañana", "del mediodía", "de la tarde", "de la noche"]
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre"]
CIUDADES = ["Madrid", "Barcelona", "Valencia", "Sevilla", "Zaragoza", "Málaga", "Bilbao", "Granada", "Salamanca",
            "Toledo", "Córdoba", "Valladolid", "Santander", "Oviedo", "Cádiz", "Pamplona", "Alicante", "Murcia",
            "Palma", "Logroño", "León", "Cáceres", "Jaén", "Gijón"]
CIELOS = ["despejado", "con algunas nubes", "nublado", "con lluvia débil", "con chubascos", "con niebla por la mañana",
          "con viento del norte", "soleado", "cubierto", "con tormentas por la tarde"]
NOMBRES = ["Lucía", "Ana", "Carmen", "Pablo", "Javier", "Marta", "Sofía", "Hugo", "Elena", "Daniel", "Paula", "Álvaro",
           "Irene", "Jorge", "Nerea", "Raúl", "Celia", "Gonzalo", "Inés", "Rocío", "Diego", "Blanca", "Mateo", "Julia"]
LUGARES = ["el dentista", "la peluquería", "el gimnasio", "el colegio", "la oficina", "el médico", "casa de los abuelos",
           "el supermercado", "la farmacia", "el taller", "la biblioteca", "el ayuntamiento", "la estación"]
TAREAS = ["sacar la basura", "regar las plantas", "llamar a mamá", "comprar pan", "pagar el alquiler",
          "recoger a los niños", "poner la lavadora", "tender la ropa", "hacer la compra", "sacar al perro",
          "revisar el correo", "preparar la cena", "cambiar la bombilla del pasillo", "pedir cita en el médico",
          "devolver el libro", "renovar el carné", "comprar un regalo", "llevar el coche a la ITV"]
APARATOS = ["las luces del salón", "la calefacción", "el aire acondicionado", "la tele", "el router",
            "la luz de la cocina", "el ventilador", "la lámpara del dormitorio", "la cafetera", "el horno"]
CARINOS = ["cariño", "corazón", "tesoro", "guapa", "campeón", "bonita", "mi vida"]
CATEGORIAS = ["supermercado", "restaurantes", "transporte", "ocio", "ropa", "farmacia", "suscripciones", "regalos"]

# Escritas a mano: conversación natural y todos los sonidos (rr, ll, ñ, ch, j, z, c, g, x, diptongos…)
FIJAS = """Hola, ¿qué tal estás? Me alegra mucho oírte.
Buenos días. He preparado tu resumen de hoy, cuando quieras te lo cuento.
No pasa nada, todos tenemos días así. Mañana será mejor.
¡Qué ilusión! Cuéntame más, quiero saberlo todo.
Claro que sí, ahora mismo lo miro.
Dame un segundo, que lo estoy comprobando.
Listo. Ya está hecho.
Lo siento mucho, no he podido completar lo que me pedías.
¿Prefieres que te lo recuerde por la mañana o por la tarde?
Si necesitas algo más, aquí estaré.
El perro de San Roque no tiene rabo porque Ramón Rodríguez se lo ha robado.
Tres tristes tigres tragaban trigo en un trigal.
La niña añadió una pizca de canela al chocolate caliente.
El cigüeñal del vehículo hacía un ruido extraño.
Jorge recogió los girasoles del jardín junto a la verja.
El chiringuito de la playa abre a las once en julio y en agosto.
Llovía tanto que la calle parecía un río.
Ximena y Félix viajaron en taxi hasta el aeropuerto.
El pingüino del zoológico se zambulló en el agua helada.
Hay que reírse más y preocuparse menos.
A veces lo más bonito es lo más sencillo.
Tómate un descanso, te lo has ganado.
¿Te apetece que pongamos un poco de música tranquila?
Respira hondo y cuenta hasta cinco. Muy bien.
Me ha encantado hablar contigo.
Perdona, creo que no lo he entendido. ¿Me lo dices de otra forma?
Gracias por tener tanta paciencia conmigo.
Ya sé que es un lío, pero lo vamos a resolver juntos.
Uy, casi se me olvida: hoy hay partido a las nueve.
Venga, que ya queda poco para el fin de semana.
¿Sabías que hoy es el día más largo del año?
Esta noche se podrá ver la luna llena desde la terraza.
El tren de las ocho y media sale con diez minutos de retraso.
He apuntado la cita en tu agenda y te avisaré media hora antes.
¿Quieres que lo deje para mañana?
Hace un frío que pela, abrígate bien.
Qué calor hace hoy. Bebe mucha agua.
Ya puedes poner la lavadora: ahora la luz está más barata.
Hoy has caminado más de ocho mil pasos. ¡Enhorabuena!
Tienes un mensaje nuevo de Lucía.
La red funciona bien y todos los dispositivos están conectados.
He bloqueado más de mil anuncios esta mañana.
Hay un dispositivo nuevo en la red. ¿Lo conoces?
La copia de seguridad se ha hecho correctamente.
La Raspberry está un poco caliente, pero todo va bien.
Si quieres, te leo las noticias más importantes del día.
En resumen: un día tranquilo, sin sorpresas.
¿Te digo cuánto has gastado este mes en el supermercado?
Muy buena elección. A mí también me gusta mucho.
Me hace mucha gracia cuando me cuentas esas cosas.
Ojalá todos los días fueran como hoy.
Dulces sueños. Mañana te despierto con el café.
¡Sorpresa! Te he preparado una lista con tus canciones favoritas.
¿Me ayudas a elegir? Dudo entre las dos opciones.
Vale, lo apunto: comprar leche, huevos, fruta y pan.
Hoy hace exactamente un año que empezamos a hablar.
¿Te cuento un chiste? Bueno, mejor otro día.
Tranquilo, no se ha perdido nada.
Para eso estamos, para ayudarnos.
¡Feliz cumpleaños! Que cumplas muchos más.""".strip().split("\n")

PLANTILLAS = [
    lambda r: f"Hoy en {r.choice(CIUDADES)} hace un día {r.choice(CIELOS)}, con {r.choice(NUMEROS[5:31])} grados.",
    lambda r: f"La mínima será de {r.choice(NUMEROS[0:16])} grados y la máxima de {r.choice(NUMEROS[16:])}.",
    lambda r: f"Mañana en {r.choice(CIUDADES)} estará {r.choice(CIELOS)}. La probabilidad de lluvia es del {r.choice(NUMEROS[10:31])} por ciento.",
    lambda r: f"Son {r.choice(HORAS)} {r.choice(MINUTOS)}.",
    lambda r: f"Te recuerdo que a {r.choice(HORAS)} {r.choice(MINUTOS)} tienes que ir a {r.choice(LUGARES)}.",
    lambda r: f"El {r.choice(DIAS)} a {r.choice(HORAS)} {r.choice(MINUTOS)} tienes cita en {r.choice(LUGARES)}.",
    lambda r: f"No te olvides de {r.choice(TAREAS)} antes de {r.choice(['comer', 'cenar', 'salir', 'acostarte', 'las diez'])}.",
    lambda r: f"He apuntado {r.choice(TAREAS)} para el {r.choice(DIAS)} por la {r.choice(['mañana', 'tarde', 'noche'])}.",
    lambda r: f"El cumpleaños de {r.choice(NOMBRES)} es el {r.choice(NUMEROS[1:31])} de {r.choice(MESES)}.",
    lambda r: f"¿Quieres que le escriba a {r.choice(NOMBRES)} para felicitarle?",
    lambda r: f"{r.choice(NOMBRES)} te ha dejado un mensaje: llegará a {r.choice(HORAS)} {r.choice(MINUTOS)}.",
    lambda r: f"Este mes llevas gastados {r.choice(NUMEROS[20:])} euros en {r.choice(CATEGORIAS)}.",
    lambda r: f"Te quedan {r.choice(NUMEROS[5:30])} euros del presupuesto de {r.choice(CATEGORIAS)}.",
    lambda r: f"El precio de la luz ahora es de {r.choice(NUMEROS[5:30])} céntimos el kilovatio hora.",
    lambda r: f"La hora más barata de la luz hoy es a {r.choice(HORAS)} {r.choice(PARTE_DIA)}.",
    lambda r: f"He {r.choice(['apagado', 'encendido'])} {r.choice(APARATOS)}.",
    lambda r: f"¿Quieres que {r.choice(['apague', 'encienda'])} {r.choice(APARATOS)}?",
    lambda r: f"Hay {r.choice(NUMEROS[2:30])} dispositivos conectados a la red de casa.",
    lambda r: f"El {r.choice(DIAS)} {r.choice(NUMEROS[1:31])} de {r.choice(MESES)} no tienes nada en la agenda.",
    lambda r: f"Buenos días, {r.choice(CARINOS)}. Hoy tienes {r.choice(NUMEROS[2:6])} cosas en la agenda.",
    lambda r: f"Buenas noches, {r.choice(CARINOS)}. Que descanses.",
    lambda r: f"Ánimo, {r.choice(CARINOS)}, que tú puedes con esto y con mucho más.",
    lambda r: f"El autobús llega en {r.choice(NUMEROS[2:20])} minutos a la parada de {r.choice(CIUDADES)}.",
    lambda r: f"La farmacia más cercana está a {r.choice(NUMEROS[2:20])} minutos andando.",
    lambda r: f"He encontrado {r.choice(NUMEROS[2:10])} {r.choice(['restaurantes', 'cafeterías', 'gasolineras', 'cajeros'])} cerca de aquí.",
    lambda r: f"Desde {r.choice(CIUDADES)} hasta {r.choice(CIUDADES)} se tarda unas {r.choice(NUMEROS[2:9])} horas en coche.",
    lambda r: f"En {r.choice(MESES)} solemos tener más días de {r.choice(['sol', 'lluvia', 'viento', 'frío', 'calor'])}.",
    lambda r: f"El partido empieza a {r.choice(HORAS)} {r.choice(MINUTOS)}.",
    lambda r: f"¿Te pongo un temporizador de {r.choice(NUMEROS[2:30])} minutos?",
    lambda r: f"Quedan {r.choice(NUMEROS[2:30])} días para {r.choice(['las vacaciones', 'Navidad', 'el verano', 'tu cumpleaños', 'el viaje'])}.",
]


MAX_POR_PLANTILLA = 45   # que ninguna estructura domine: la voz aprende mejor con variedad


def generar(cantidad: int = 1400, semilla: int = 7) -> list[str]:
    r = random.Random(semilla)
    frases, vistas = list(FIJAS), set(FIJAS)
    usos = [0] * len(PLANTILLAS)
    intentos = 0
    while len(frases) < cantidad and intentos < cantidad * 50:
        intentos += 1
        i = r.randrange(len(PLANTILLAS))
        if usos[i] >= MAX_POR_PLANTILLA:
            continue
        f = PLANTILLAS[i](r)
        f = f[0].upper() + f[1:]
        if f not in vistas:
            vistas.add(f)
            frases.append(f)
            usos[i] += 1
    r.shuffle(frases)
    return frases


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1400
    print("\n".join(generar(n)))
