# Módulos de ARIA: guía para desarrolladores

Un **módulo** es una carpeta dentro de `modulos/` que enchufa a ARIA una aplicación tuya o una función nueva
sin tocar el núcleo. Con un módulo puedes:

- poner un **mosaico en Inicio** que abre tu aplicación, con un punto verde/rojo según su **salud**;
- añadir **herramientas al chat** («¿responde example.org?»), también en Telegram y en las rutinas;
- añadir **avisos** periódicos que llegan por Telegram y notificaciones push;
- añadir **endpoints** propios bajo `/api/modulos/<id>/`.

Todo aparece en **Ajustes → Módulos** (solo administradores), con su versión, su estado, sus herramientas y las
variables de entorno que necesita.

> **Seguridad: instala solo módulos de confianza.** Un módulo con `modulo.py` es código Python que se ejecuta
> **dentro de ARIA**, con sus mismos permisos: puede leer la base de datos, las variables de `.env` (claves
> incluidas) y hablar con la red. El SDK te pone barandillas (permisos de las rutas, validación, aislamiento de
> errores), pero no es un sandbox. Lee el código de cualquier módulo antes de copiarlo a `modulos/`.

## Índice

1. [Cómo funciona](#cómo-funciona)
2. [Crear un módulo paso a paso](#crear-un-módulo-paso-a-paso)
3. [Referencia del manifiesto `modulo.json`](#referencia-del-manifiesto-modulojson)
4. [Referencia del SDK (`registrar(aria)`)](#referencia-del-sdk-registrararia)
5. [Activar, desactivar y configurar](#activar-desactivar-y-configurar)
6. [Si tu módulo necesita su propio contenedor](#si-tu-módulo-necesita-su-propio-contenedor)
7. [Recorrido por la plantilla](#recorrido-por-la-plantilla)
8. [El ejemplo `uptime`](#el-ejemplo-uptime)
9. [Aplicaciones integradas](#aplicaciones-integradas)
10. [Seguridad](#seguridad)
11. [Pruebas](#pruebas)
12. [Solución de problemas](#solución-de-problemas)

## Cómo funciona

```
modulos/
├── _plantilla/        ← plantilla para copiar (el cargador ignora lo que empieza por «_» o «.»)
│   ├── modulo.json
│   ├── modulo.py
│   └── compose.ejemplo.yml
├── uptime/            ← módulo de ejemplo, activo por defecto (no necesita configuración)
│   ├── modulo.json
│   └── modulo.py
└── mi-app/            ← el tuyo
    ├── modulo.json    ← obligatorio
    ├── modulo.py      ← opcional: herramientas, avisos y endpoints
    └── otro.py        ← opcional: más código (from . import otro)
```

- La carpeta `modulos/` del repositorio se monta **de solo lectura** en el contenedor `aria-app`
  (`./modulos:/srv/modulos:ro` en `docker-compose.yml`). Otra ruta: `ARIA_MODULOS_DIR`.
- Los módulos se cargan **al arrancar** ARIA. Tras añadir o cambiar uno: `docker compose restart app`.
- Para cada carpeta, el cargador (`app/aria/modulos.py`):
  1. lee y **valida** `modulo.json` (si no es válido → estado «error» con el motivo);
  2. si no está en `ARIA_MODULOS` → «desactivado» (su código no se ejecuta);
  3. si falta alguna variable de `env` → «sin configurar» (su código no se ejecuta);
  4. si hay `modulo.py`, lo importa y llama a `registrar(aria)`. Lo que registres se **valida y se aplica de
     golpe** solo si `registrar` termina sin errores. Si algo falla (excepción, error de sintaxis, nombre
     repetido...), el módulo queda en «error» con el mensaje, **se deshace lo que hubiera registrado a medias**
     y ARIA arranca igual.

Estados que verás en Ajustes → Módulos: **Activo**, **Sin configurar**, **Desactivado** y **Error** (con el
mensaje). El punto de color indica la salud (si el manifiesto tiene `salud`).

## Crear un módulo paso a paso

Ejemplo: tienes una aplicación «Recetas» en la Raspberry, en el puerto 8099, con una API
`GET /api/hoy` que devuelve la receta del día, y quieres verla en Inicio y preguntarle a ARIA por ella.

### 1. Copia la plantilla

```bash
cd ~/ARIA            # donde clonaste el repositorio
cp -r modulos/_plantilla modulos/recetas
```

### 2. Rellena el manifiesto

`modulos/recetas/modulo.json` (las claves que empiezan por `_` son comentarios; bórralas o déjalas):

```json
{
  "id": "recetas",
  "nombre": "Recetas",
  "descripcion": "Recetario de casa.",
  "version": "1.0.0",
  "icono": "casa",
  "url": "http://{host}:8099/",
  "salud": {"tipo": "http", "host": "host.docker.internal", "puerto": 8099, "ruta": "/"},
  "env_opcional": ["RECETAS_URL"],
  "roles": ["admin", "usuario"]
}
```

- `id` debe ser **igual que el nombre de la carpeta**.
- `{host}` en `url` se cambia en el navegador por el nombre con el que entras en ARIA (la IP de casa,
  `aria.local`...), así el enlace sirve en todos los dispositivos.
- Desde el contenedor de ARIA, la Raspberry es `host.docker.internal`.

Con esto ya tienes un mosaico en Inicio con su punto de salud. Si no necesitas nada más, **borra `modulo.py`**.

### 3. Añade una herramienta al chat (opcional)

`modulos/recetas/modulo.py`:

```python
import httpx


def registrar(aria):
    base = aria.config("RECETAS_URL", "http://host.docker.internal:8099")

    @aria.herramienta(
        "receta_del_dia",
        "Dice cuál es la receta del día del recetario de casa.",
        solo_lectura=True,                       # solo consulta: también vale para las rutinas
        roles=("admin", "usuario"),
        intenciones=[r"\breceta"],               # el modelo local solo la ve si el mensaje dice «receta»
    )
    async def receta_del_dia() -> str:
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.get(f"{base}/api/hoy")
                r.raise_for_status()
        except httpx.HTTPError:
            raise aria.Error("El recetario no responde ahora mismo.")
        return f"Hoy toca: {r.json()['titulo']}"
```

### 4. Reinicia y prueba

```bash
docker compose restart app
docker compose logs app | grep -i módulo     # «Módulo recetas 1.0.0 cargado (1 herramientas, ...)»
```

Abre **Ajustes → Módulos**: debe salir «Recetas · 1.0.0 — Activo» con la herramienta `receta_del_dia`.
Pregunta en el chat «¿qué receta toca hoy?».

### 5. Escribe pruebas (recomendado)

Mira `app/tests/test_modulos.py`: carga tu carpeta en una app de FastAPI nueva con `modulos.cargar(app,
carpeta, {"recetas"})` y llama a tus herramientas con `tools.ejecutar(...)`. Sin red: simula tu aplicación.

## Referencia del manifiesto `modulo.json`

La validación es **estricta**: una clave desconocida es un error (salvo las que empiezan por `_`, que son
comentarios). Tamaño máximo 64 KB.

| Clave | Obligatoria | Formato | Para qué |
|---|---|---|---|
| `id` | sí | 2-32 caracteres `a-z`, `0-9`, `-`; igual que la carpeta | Identificador. No puede ser `shield-dns` ni `heimdall`. |
| `nombre` | sí | 1-40 caracteres | Lo que se ve en Inicio y Ajustes. |
| `version` | sí | 1-20 caracteres `0-9A-Za-z.+-` | Tu versión, p. ej. `1.0.0`. |
| `descripcion` | no | ≤ 300 caracteres | Una frase. |
| `icono` | no (`app`) | `app`, `web`, `escudo`, `candado`, `servidor`, `grafica`, `casa`, `musica`, `nube`, `reloj`, `herramienta`, `red`, `camara`, `documento` | Icono del mosaico. |
| `url` | no | `http://` o `https://`, ≤ 300; admite `{host}`; sin usuario ni contraseña | Si existe, hay mosaico en Inicio que abre esa dirección en otra pestaña. |
| `salud` | no | `{"tipo", "host", "puerto", "ruta", "tls"}` | Punto verde/rojo del mosaico (ver abajo). |
| `env` | no | lista de nombres en MAYÚSCULAS (máx. 20) | Variables **obligatorias** de `.env`. Si falta una → «sin configurar» y `modulo.py` no se ejecuta. |
| `env_opcional` | no | igual | Variables que el módulo puede leer pero no necesita. |
| `roles` | no (`["admin"]`) | `["admin"]` o `["admin", "usuario"]` | Quién ve el mosaico en Inicio (admin siempre). Las herramientas y rutas tienen sus propios roles en el SDK. |

**`salud`**: ARIA lo comprueba como mucho cada 20 s (con 3 s de límite) cuando alguien mira Inicio o Ajustes.

| `tipo` | Comprueba | Valores por defecto |
|---|---|---|
| `http` | `GET http(s)://host:puerto/ruta` responde con un código < 500 (sin seguir redirecciones; con `tls: true` usa https y acepta certificados propios) | puerto 80, ruta `/` |
| `tcp` | el puerto acepta conexiones | (puerto obligatorio) |
| `dns` | el servidor resuelve `example.com` (registro A, UDP) | puerto 53 |

`host` es un nombre o IP (sin esquema). La salud es configuración del administrador, así que puede apuntar a
la red de casa (a diferencia de `aria.comprobar_url`).

## Referencia del SDK (`registrar(aria)`)

`modulo.py` debe definir una función **normal** (no `async`) `registrar(aria)`. `aria` es una instancia de
`app/aria/sdk.py:Aria` (versión `aria.VERSION_SDK == 1`). Usa solo el SDK: el resto del núcleo puede cambiar.

### `aria.herramienta(nombre, descripcion, params=None, requeridos=(), *, solo_lectura=False, intenciones, roles=("admin",), agentes=("aria",))`

Decorador para una función **async** que devuelve un texto (o algo serializable a JSON).

- `nombre`: 3-48 caracteres `a-z`, `0-9`, `_`, empezando por letra. No puede coincidir con una herramienta
  del núcleo ni de otro módulo (consejo: usa el id del módulo como prefijo).
- `descripcion`: 5-500 caracteres; es lo que lee el modelo para decidir usarla. Escríbela en español.
- `params`: `{"nombre": ("string"|"integer"|"number"|"boolean", "descripción")}`, como mucho 8; `uid` está
  prohibido. `requeridos`: tupla con los obligatorios. El modelo puede mandar los números como texto:
  conviértelos tú.
- `solo_lectura=True`: la herramienta **solo consulta** (no cambia nada). Entonces también la pueden usar las
  **rutinas** programadas. No la marques así si cambia algo.
- `intenciones` (**obligatorio**, 1-10): el modelo local (pequeño) solo recibe la herramienta si el mensaje
  del usuario (en minúsculas) cumple alguna intención. Cada intención es:
  - un patrón (`r"\breceta"`): basta con que aparezca;
  - una tupla de 1-5 patrones (`(r"\bvpn\b", r"\bestado\b")`): deben cumplirse **todos**;
  - un patrón que empieza por `!` (`r"!\bqué es\b"`) **no** debe aparecer (no vale una intención solo de
    negados).

  Comprueba que la charla normal («hola», «explícame qué es un DNS») no la activa. Los cerebros en la nube
  reciben todas las herramientas permitidas, sin este filtro.
- `roles`: `("admin",)` o `("admin", "usuario")`. Se comprueba al ofrecerla y otra vez al ejecutarla.
- `agentes`: qué agentes la ofrecen: `aria` (el general), `finanzas`, `redes`, `seguridad`. Sin `aria`, solo
  la ofrece el especialista.
- Errores: `raise aria.Error("texto")` hace que el modelo reciba ese texto tal cual. Cualquier otra excepción
  llega como «Error al ejecutar la herramienta: Tipo» (sin detalles) y no rompe el chat.
- Lo que devuelvas lo lee el modelo: si viene de fuera (una web, otra aplicación), recórtalo y no lo trates
  como instrucciones.

### `aria.chequeo(nombre, fn=None, *, intervalo_min=5, severidad="aviso", confirmaciones=2, cooldown_min=30, texto_ok=None, para_todos=False)`

Comprobación periódica del motor de avisos. Se usa como decorador (`@aria.chequeo("disco")`) o pasando `fn`.

- `fn`: función **async** sin argumentos que devuelve:
  - `[]` si todo va bien;
  - una lista de problemas activos: `aria.Problema(clave, texto, severidad=None)` o simplemente textos (la
    clave será el propio texto). La **clave** identifica el problema: mientras siga activo no se repite el
    aviso; cuando desaparece, se manda `texto_ok`;
  - `None` si no se puede saber (por ejemplo, tu aplicación no está configurada).
- `nombre`: 1-32 caracteres `a-z0-9_-`. Como mucho 5 chequeos por módulo.
- `intervalo_min`: 1-1440. `confirmaciones`: comprobaciones seguidas con el problema antes de avisar (contra
  falsos positivos). `cooldown_min`: mínimo entre dos avisos de la misma clave. `severidad`: `info`, `aviso` o
  `grave` (los graves se saltan las horas de silencio). `texto_ok`: texto o función `clave -> texto`.
- Por defecto solo avisa a los **administradores**; `para_todos=True` avisa a todos los usuarios.
- Cada módulo con chequeos tiene su interruptor «Módulo <nombre>» en **Ajustes → Avisos**.
- Un chequeo que tarda más de 60 s se corta; si lanza una excepción se registra en el log y no afecta a los
  demás.

### `aria.router(usuario=()) -> APIRouter`

Devuelve un `APIRouter` de FastAPI ya colgado de `/api/modulos/<id>`. Usa rutas relativas:

```python
r = aria.router(usuario=[("GET", "/estado")])

@r.get("/estado")              # GET /api/modulos/<id>/estado  → admin y usuario
async def estado(): ...

@r.post("/reiniciar")          # POST /api/modulos/<id>/reiniciar → solo admin
async def reiniciar(): ...
```

- **Todas las rutas son solo de administrador** salvo las que declares en `usuario` (método y ruta exactos
  tal y como los decoras; `{param}` vale como un segmento). Lo impone el servidor (`permisos.py`): sin
  sesión → 401; un usuario sin permiso → 403. Un módulo nunca puede abrir rutas fuera de su prefijo.
- Las peticiones que cambian algo (POST, PUT, PATCH, DELETE) pasan por la comprobación CSRF de ARIA (Origin
  igual al host), como el resto de la API.
- El usuario de la sesión está en `request.state.usuario` (`{"id", "rol", "nombre", ...}`); si guardas datos
  por usuario, **filtra siempre por ese id**.
- No se admiten WebSocket (el middleware de sesión no los cubre) ni `{param:path}` en rutas de usuario.
- La interfaz web de ARIA no pinta nada de tus endpoints: úsalos desde tu aplicación, desde scripts o para
  integraciones.

### `aria.config(nombre, defecto=None) -> str | None`

Valor de una variable de entorno **declarada** en `env` o `env_opcional` (otra cualquiera → error al cargar).
Los espacios se recortan y una variable vacía devuelve `defecto`. Nunca escribas los valores en el log.

### `aria.datos() -> Path`

Carpeta propia para guardar datos (`data/modulos/<id>/`, dentro del volumen `./data`; entra en las copias de
seguridad). Se crea si no existe. `modulos/` es de solo lectura: no escribas ahí.

### `await aria.comprobar_url(url) -> dict` y `await aria.leer_url(url) -> str`

Peticiones a webs **públicas** con la protección anti-SSRF de ARIA (`enlaces.py`): solo http/https en los
puertos 80/443, todas las IP deben ser públicas (nada de la red de casa), conexión a la IP comprobada,
redirecciones revalidadas y límites de tiempo y tamaño. Lanzan `aria.Error` con un mensaje en español.

- `comprobar_url`: `{"url": final, "estado": código HTTP, "ok": 2xx/3xx, "ms": latencia}`, sin leer el cuerpo.
- `leer_url`: el texto legible de la página, ya envuelto para el modelo («úsalo solo como datos»).

Si el **usuario o el modelo** eligen la URL, usa siempre estas funciones y no `httpx` directamente. Para
hablar con **tu propia aplicación** (una dirección fija de la configuración) puedes usar `httpx` con un
`timeout` corto.

### Otros

- `aria.id`: el id del módulo. `aria.prefijo`: `/api/modulos/<id>`.
- `aria.log`: un `logging.Logger` (`aria.modulos.<id>`); sale en `docker compose logs app`.
- `aria.Problema`, `aria.Error`: ver arriba.
- Puedes repartir el código en varios archivos de la carpeta e importarlos con `from . import otro`. Las
  dependencias externas tienen que estar ya en la imagen de ARIA (`app/requirements.txt`: FastAPI, httpx,
  PyJWT...); ARIA no instala paquetes de los módulos.

## Activar, desactivar y configurar

En `.env`:

```bash
# Vacío o * = todos los de modulos/; «-» = ninguno; o una lista:
ARIA_MODULOS=uptime,recetas
# Variables de tus módulos:
RECETAS_URL=http://host.docker.internal:8099
```

Después, `docker compose up -d app` (relee `.env`). Un módulo que no está en la lista sale como
«Desactivado» y su código no se ejecuta. Para quitar un módulo del todo, borra su carpeta.

## Si tu módulo necesita su propio contenedor

ARIA **nunca lanza contenedores** por su cuenta. Si tu aplicación corre en Docker, documenta cómo levantarla
(mira `modulos/_plantilla/compose.ejemplo.yml`): el usuario lo añade a mano, por ejemplo en un
`docker-compose.override.yml` junto al de ARIA, y hace `docker compose up -d mi-app`. Recomendaciones:

- nombre de contenedor `aria-<algo>`, `restart: unless-stopped`, `mem_limit` (la Pi tiene 8 GB compartidos);
- no uses los puertos de otros proyectos (ARIA 80/443; SHIELD-DNS 53, 8080, 8443; HEIMDALL 51820/udp, 51843);
- si solo ARIA debe hablar con tu servicio, no publiques puertos: ponlo en la red de Compose de ARIA y usa
  el nombre del servicio como `host`.

## Recorrido por la plantilla

`modulos/_plantilla/` es un módulo completo y comentado, listo para copiar:

- **`modulo.json`**: todas las claves, cada una con su comentario `_clave`. Declara `url` y `salud` (http al
  puerto 8099), una variable obligatoria (`PLANTILLA_TOKEN`) y una opcional (`PLANTILLA_SALUDO`), y abre el
  mosaico a los usuarios.
- **`modulo.py`**:
  1. lee la configuración con `aria.config` (la obligatoria siempre existe: si faltase, el archivo ni se
     ejecutaría);
  2. registra la herramienta de solo lectura `plantilla_saludo` con dos intenciones: «plantilla» o
     «saluda» + «módulo»;
  3. registra el chequeo `disco-lleno` (cada 10 min, dos confirmaciones, con `texto_ok`);
  4. crea el router con `GET /estado` (admin y usuario) y `POST /reiniciar` (solo admin).
- **`compose.ejemplo.yml`**: cómo documentar un contenedor propio (comentado; no se ejecuta).

Al copiarla: cambia `id` (igual que la carpeta), el nombre de la herramienta (debe ser único) y lo que
necesites. Hay una prueba (`test_plantilla_copiada_funciona`) que copia la plantilla y comprueba que carga.

## El ejemplo `uptime`

`modulos/uptime/` es un módulo real, útil e inofensivo (solo lectura), **activo por defecto** porque no
necesita configuración:

- Herramienta `comprobar_web(url)` (todos los roles, ARIA general y agente Redes): «¿responde
  https://example.org?», «¿está caída github.com?» → código HTTP y latencia. Usa `aria.comprobar_url`, así
  que solo comprueba webs públicas.
- Con `UPTIME_URLS=https://example.org,https://tu-dominio.com` (máx. 10) registra el chequeo `webs`: cada
  `UPTIME_INTERVALO_MIN` minutos (5 por defecto) revisa esas webs y avisa al administrador si una falla dos
  veces seguidas, y cuando vuelve.
- `GET /api/modulos/uptime/estado` (solo admin): el último resultado de cada URL vigilada.

Para vigilar un servicio **de casa** no uses `uptime` (la protección anti-SSRF lo impide a propósito): crea un
módulo con `salud` en su `modulo.json`.

## Aplicaciones integradas

SHIELD-DNS (Pi-hole) y HEIMDALL (wg-easy) llevan integrados en ARIA desde el principio: su código está en el
núcleo (`shield.py`, `vpn.py`, `services.py`, sus herramientas en `tools.py` y sus mosaicos en
`index.html`). En Ajustes → Módulos aparecen como **aplicaciones integradas** para que se vea el modelo:
mismo tipo de ficha (estado, salud, herramientas y variables de `.env` que usan), pero no se pueden
desactivar con `ARIA_MODULOS` ni sustituir por un módulo con el mismo id.

## Seguridad

- **Confianza**: un módulo es código que corre dentro de ARIA con sus permisos (base de datos, `.env`, red).
  No hay sandbox. Instala solo módulos que hayas leído o de alguien de quien te fíes, y revisa los cambios al
  actualizarlos.
- **Solo lectura**: `modulos/` se monta `:ro`; un módulo no puede modificarse a sí mismo ni a otros.
- **Permisos**: rutas solo de admin salvo declaración explícita; herramientas solo de admin salvo
  `roles=("admin", "usuario")`; ambas cosas se comprueban en el servidor. Un módulo no puede abrir rutas fuera
  de `/api/modulos/<id>/` ni reutilizar nombres de herramientas del núcleo.
- **Secretos**: la API y Ajustes solo enseñan el **nombre** de las variables y si están definidas, nunca su
  valor. No los escribas en el log ni los devuelvas en herramientas o endpoints.
- **Datos por usuario**: si guardas algo por usuario, fíltralo siempre por `request.state.usuario["id"]`
  (nunca por un id que venga en la petición).
- **Red**: con URL elegidas por usuarios o por el modelo, usa `aria.comprobar_url` / `aria.leer_url`.
- **Interfaz**: el nombre, la descripción y los errores de tu módulo se pintan como texto (nunca como HTML),
  y el enlace del mosaico solo puede ser http/https.
- **Modelo**: lo que devuelven tus herramientas lo lee el modelo; si incluye texto de terceros, avisa de que
  son datos y no instrucciones (como hace `leer_url`). No expongas al modelo acciones destructivas.

## Pruebas

Las pruebas de ARIA (`app/tests/`, sin red) cargan dos módulos de prueba de `app/tests/modulos_prueba/` (uno
bueno y uno que explota a propósito) y comprueban el cargador, el SDK, los permisos de las rutas, los avisos,
la plantilla y el ejemplo `uptime` (`test_modulos.py`). Para lanzarlas con la carpeta `modulos/` incluida,
monta el repositorio entero:

```bash
docker run --rm -v "$PWD:/repo" -w /repo/app python:3.12-slim \
  sh -c "pip install -q -r requirements.txt pytest && python -m pytest -q -p no:cacheprovider"
```

(Con solo `app/` montado, las pruebas de la plantilla y de `uptime` se saltan.)

## Solución de problemas

| Síntoma | Causa probable |
|---|---|
| No aparece en Ajustes → Módulos | La carpeta empieza por `_` o `.`, o no reiniciaste la app. |
| «Error: «id» (...) debe coincidir con el nombre de la carpeta» | Cambia `id` o renombra la carpeta. |
| «Sin configurar» | Falta una variable de `env` en `.env` (o está vacía). Tras añadirla: `docker compose up -d app`. |
| «Desactivado» | `ARIA_MODULOS` tiene una lista que no lo incluye. |
| «Error: la herramienta «x» choca con una del núcleo» | Cambia el nombre (usa el id del módulo como prefijo). |
| La herramienta no se usa con el cerebro local | Sus `intenciones` no coinciden con el mensaje (recuerda que va en minúsculas). |
| 403 en un endpoint | Es solo de admin: decláralo en `aria.router(usuario=[...])` si es para todos. |
| Punto rojo en el mosaico | `salud` no responde desde el contenedor: usa `host.docker.internal` para la Raspberry. |

Los detalles de cada error (con la traza) están en `docker compose logs app`.
