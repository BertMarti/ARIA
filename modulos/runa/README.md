# Módulo RUNA

Comparte contraseñas, claves y notas privadas con un **enlace de un solo uso** que se autodestruye al leerse,
directamente desde el chat de ARIA o desde Telegram.

[RUNA](https://github.com/BertMarti/runa) cifra de extremo a extremo: el servidor solo guarda ruido cifrado y la
llave viaja dentro del enlace, en la parte que hay tras `#`, que los navegadores nunca envían. Este módulo cifra
**dentro de ARIA** con el mismo protocolo que la web de RUNA (`protocolo.py`), así que tampoco el contenedor de
RUNA ve nunca el contenido.

## Qué añade

| | |
|---|---|
| 🧩 **Mosaico en Inicio** | Abre RUNA (`https://<tu-ARIA>:8485`), con su punto de salud. |
| 💬 **«Comparte la clave del wifi por RUNA, que caduque en 1 hora»** | Herramienta `runa_compartir`: devuelve el enlace para que lo envíes. |
| 🎲 **«Genérame una contraseña nueva para el router y compártela»** | Herramienta `runa_generar`: crea una contraseña robusta **aquí** y te da dos enlaces, uno para ti y otro para compartir. La contraseña nunca pasa por el modelo ni queda en la conversación. |
| 🔔 **Aviso si RUNA se cae** | Chequeo cada 5 minutos, solo para administradores. |

Las dos herramientas valen para administradores y usuarios. No están en las rutinas porque crean cosas.

## Instalación

1. **Arranca RUNA junto a ARIA.** Copia el contenido de `compose.ejemplo.yml` a un `docker-compose.override.yml`
   en la carpeta de ARIA (o añádelo al que ya tengas) y ejecuta:

   ```bash
   docker compose up -d runa runa-tls
   ```

   Se crean dos contenedores: `aria-runa` (la aplicación, sin puertos publicados y endurecido: solo lectura, sin
   capacidades, distroless y sin root) y `aria-runa-tls` (un Caddy que la sirve por HTTPS en el puerto **8485**,
   con la misma CA interna y los mismos nombres autorizados que ARIA).

2. **Configura `.env`:**

   ```ini
   ARIA_MODULOS=runa            # añádelo a la lista si ya tienes otros
   RUNA_URL=http://runa:8080
   # Base de los enlaces que compartes. En casa: la de tu ARIA en el puerto 8485.
   RUNA_URL_PUBLICA=https://192.168.1.50:8485
   ```

3. `docker compose restart app` y comprueba en **Ajustes → Módulos** que RUNA aparece como «Activo».

### Enlaces que funcionen fuera de casa

Quien recibe el enlace tiene que llegar a RUNA **por HTTPS**, porque el cifrado del navegador solo funciona en
páginas seguras. Dentro de casa sirve `https://<IP-de-ARIA>:8485`, aceptando una vez el certificado propio.
Para compartir con alguien de fuera:

- **Túnel de Cloudflare** (el de ARIA): añade un nombre público, p. ej. `secretos.tudominio`, que apunte a
  `http://runa:8080`, y pon `RUNA_URL_PUBLICA=https://secretos.tudominio`. **No** lo pongas detrás de Cloudflare
  Access: quien recibe el enlace no tiene cuenta.
- **VPN HEIMDALL**: solo para personas con acceso a tu VPN.

## Privacidad: qué pasa por dónde

| Dato | Servidor de RUNA | ARIA | Modelo del chat |
|---|---|---|---|
| Texto de `runa_compartir` | ❌ solo cifrado | ✅ (lo escribiste en el chat) | ✅ |
| Contraseña de `runa_generar` | ❌ solo cifrado | ✅ un instante, en memoria | ❌ nunca |
| Enlace (con la llave tras `#`) | ❌ | ✅ | ✅ |

- Con el **cerebro local (Ollama)** nada sale de casa.
- Con un **cerebro en la nube**, el texto de `runa_compartir` y los enlaces pasan por ese proveedor.
  - Para secretos críticos, usa `runa_generar` o la web de RUNA directamente.
  - Si alguien abriera un enlace antes que tu destinatario, este vería «Este secreto ya no existe» y lo sabrías.
- Los mensajes del chat se guardan en el historial de ARIA, como cualquier conversación. Los enlaces dejan de
  servir en cuanto se leen o caducan.

## Opciones

- **Caducidad**: 5 minutos, 1 hora, 1 día (por defecto) o 7 días. Se entiende lenguaje natural («media hora»,
  «un día», «una semana»); se elige la más corta que cubra lo pedido, con un máximo de 7 días.
- **Lecturas**: de 1 (por defecto) a 10.
- **Longitud** (`runa_generar`): de 12 a 64 caracteres (20 por defecto), sin caracteres que se confunden
  (0/O, 1/l/I).

## Pruebas

`app/tests/test_modulo_runa.py` (sin red; RUNA falso con `httpx.MockTransport`) comprueba:

- que se abren secretos **cifrados por la web real de RUNA** (vectores generados con su implementación);
- el relleno a bloques y la detección de alteraciones;
- las dos herramientas, extremo a extremo contra el RUNA falso, que valida lo que recibe como el real;
- que la contraseña generada no aparece en la respuesta;
- las intenciones del modelo local y el chequeo.
