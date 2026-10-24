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
| 🧩 **Mosaico en Inicio** | Abre RUNA con su punto de salud: en casa, el RUNA de la LAN (`https://<IP-de-ARIA>:8485`, donde se crean secretos); por el dominio, el público. |
| 💬 **«Comparte la clave del wifi de invitados por RUNA, que caduque en 1 hora»** | Herramienta `runa_compartir`: devuelve el enlace para que lo envíes. Pensada para secretos **poco sensibles** (ver «Privacidad»). |
| 🎲 **«Genérame una contraseña nueva para el router y compártela»** | Herramienta `runa_generar`: crea una contraseña robusta **aquí** y te da dos **enlaces de ARIA de un solo uso**: uno para verla tú y otro para obtener el enlace que envías. Ni la contraseña ni los enlaces de RUNA pasan por el modelo ni quedan en el historial. |
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
   # Base de los enlaces que compartes: el nombre público del túnel (paso 4) o, si solo lo usas en casa,
   # https://<IP-de-ARIA>:8485. compose.ejemplo.yml la usa también como PUBLIC_URL de RUNA.
   RUNA_URL_PUBLICA=https://runa.example.com
   ```

3. `docker compose restart app` y comprueba en **Ajustes → Módulos** que RUNA aparece como «Activo».

4. **Para compartir con gente de fuera** (si usas el túnel de Cloudflare de ARIA), vuelve a ejecutar
   `./cloudflare/configurar.sh`: al ver el contenedor `aria-runa`, publica `runa.<tu-dominio>` → `http://runa:8080`
   con su nombre DNS y **sin Cloudflare Access**, porque quien recibe el enlace no tiene cuenta.

### Quién puede abrir los enlaces y quién puede crear

| | Abrir un enlace | Crear secretos |
|---|---|---|
| **Desde fuera, por `runa.<dominio>`** (túnel) | ✅ cualquiera con el enlace | ❌ la web lo explica (403) |
| **En casa, por `https://<IP-de-ARIA>:8485`** | ✅ | ✅ |
| **Con ARIA** (`runa_compartir`, `runa_generar`) | — | ✅ estés donde estés |

- **Crear solo desde casa o desde ARIA.** RUNA corre con `CREATE_FROM` (redes privadas). Así nadie de Internet
  puede usar tu dominio para alojar secretos o archivos.
  - Lo que llega por Cloudflare cuenta siempre como externo, aunque alguien falsifique `X-Forwarded-For`.
  - Los límites de lectura y de «destruir» van por la IP real de cada cliente.
- **Sin túnel**, los enlaces solo se abren en casa o con la VPN (el 8485 se publica solo en `ARIA_LAN_IP`), y el
  navegador avisa del certificado la primera vez (la CA interna de Caddy, como ARIA).
- **Bloqueos de Cloudflare.** Si tu operador bloquea IPs de Cloudflare (pasa en España algunos días de partido),
  los enlaces públicos no abrirán mientras dure el bloqueo. En casa siguen funcionando por el 8485.

## Privacidad: qué pasa por dónde

| | Servidor de RUNA | Modelo del chat (y su proveedor si es de la nube) | Historial de ARIA (`aria.db`) |
|---|---|---|---|
| **`runa_compartir`**: el texto | ❌ solo cifrado | ⚠️ sí: lo escribiste en el chat | ⚠️ sí, en claro, y puede acabar en el diario de la madrugada |
| **`runa_compartir`**: el enlace (llave tras `#`) | ❌ | ⚠️ sí | ⚠️ sí, hasta que se lee o caduca |
| **`runa_generar`**: la contraseña | ❌ solo cifrado | ✅ nunca | ✅ nunca |
| **`runa_generar`**: los enlaces de RUNA | ❌ | ✅ nunca: solo ve tickets de ARIA | ✅ solo tickets, de un solo uso y 30 min |

**`runa_compartir` es para secretos poco sensibles**, como la clave del wifi de invitados. Lo que escribes en el
chat pasa por el modelo y queda en el historial como cualquier mensaje. Con un cerebro en la nube, también pasa
por ese proveedor. Para un secreto de verdad:

- **contraseñas nuevas**: `runa_generar`;
- **un texto que ya tienes**: la web de RUNA directamente (mosaico de Inicio);
- y si lo has escrito en el chat, borra después la conversación.

**Cómo protege `runa_generar`.** La herramienta genera la contraseña, la cifra y la sube a RUNA sin devolvérsela
al modelo. Al chat solo llegan dos direcciones `https://<ARIA>/api/modulos/runa/recoger/<ticket>`:

- exigen **sesión iniciada en ARIA** (un proveedor de IA que las vea no puede usarlas);
- sirven **una sola vez** durante **30 minutos**;
- una redirige a tu navegador al enlace de RUNA para que veas la contraseña;
- la otra te muestra, en texto, el enlace que envías.

La llave viaja de ARIA a tu navegador por HTTPS, nunca al modelo. Los tickets viven en memoria: si ARIA se
reinicia, se pierden y basta con pedir otra contraseña.

Los tickets usan `ARIA_URL_PUBLICA` (el túnel) si existe y, si no, `https://ARIA_LAN_IP`. Desde Telegram, ábrelos
en un navegador donde tengas la sesión de ARIA iniciada.

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
