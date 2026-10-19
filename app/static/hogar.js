"use strict";
// Hogar: cámaras Tapo, luces Govee, vigilancia y router. Cada sección se carga por su cuenta (el servidor responde con
// lo último conocido y refresca detrás), así la pantalla aparece al momento. Los cambios se ven al instante y se deshacen si fallan.
const Hogar = (() => {
  let activo = false, generacion = 0;
  const estado = {};   // lo último recibido de cada sección (para la franja de resumen)
  const COLORES = ["#ffffff", "#ffb35c", "#ff4d4d", "#ffd84d", "#4ddb7e", "#4da6ff", "#a64dff"];
  const nota = (texto) => el("p", { class: "muted" }, texto);
  function tarjeta(titulo, ...cuerpo) {
    return el("article", { class: "tarjeta hogar-tarjeta" }, el("div", { class: "tarjeta-cab" }, el("h2", null, titulo)), ...cuerpo);
  }
  function sinConfigurar(titulo, variables) {
    return tarjeta(titulo, nota("Sin configurar. Añade en el archivo .env de ARIA:"),
      el("ul", { class: "hogar-variables" }, ...variables.map((v) => el("li", null, el("code", null, v)))),
      nota("Después reinicia ARIA (docker compose up -d)."));
  }
  function interruptor(texto, encendido, alCambiar, deshabilitado) {
    const c = el("input", { type: "checkbox", checked: !!encendido, disabled: !!deshabilitado });
    c.addEventListener("change", async () => {
      c.disabled = true;
      const ok = await alCambiar(c.checked);
      if (!ok) c.checked = !c.checked;
      c.disabled = false;
    });
    return el("label", { class: "interruptor hogar-interruptor" }, c, el("span", null, texto));
  }
  async function enviarLuz(id, json) {
    const r = await api("/api/hogar/luces/" + encodeURIComponent(id), { method: "POST", json });
    if (!r.ok) toast(r.data.error || "No se pudo cambiar la luz.", "mal");
    return r.ok;
  }

  function filaLuz(luz) {
    const muestra = el("span", { class: "hogar-muestra", ariaHidden: "true" });
    const pintarMuestra = (c, encendida) => { muestra.style.setProperty("--color", c || "#ffffff"); muestra.classList.toggle("apagada", !encendida); };
    let encendida = !!luz.encendida, color = luz.color || "#ffffff";
    pintarMuestra(color, encendida);
    const brillo = el("input", { type: "range", min: 1, max: 100, value: luz.brillo || 100, ariaLabel: "Brillo de " + luz.nombre, disabled: !luz.en_linea });
    const valor = el("span", { class: "muted hogar-brillo-valor" }, (luz.brillo || 100) + " %");
    brillo.addEventListener("input", () => { valor.textContent = brillo.value + " %"; });
    brillo.addEventListener("change", () => enviarLuz(luz.id, { brillo: Number(brillo.value) }));   // al soltar, no en cada paso
    const selector = el("input", { type: "color", value: color, ariaLabel: "Otro color para " + luz.nombre, disabled: !luz.en_linea });
    const ponerColor = async (c) => {
      const antes = color; color = c; pintarMuestra(c, encendida);
      if (!await enviarLuz(luz.id, { color: c })) { color = antes; pintarMuestra(antes, encendida); }
    };
    selector.addEventListener("change", () => ponerColor(selector.value));
    const rapidos = COLORES.map((c) => {
      const b = el("button", { type: "button", class: "hogar-color", ariaLabel: "Color " + c, disabled: !luz.en_linea });
      b.style.setProperty("--color", c);
      b.addEventListener("click", () => ponerColor(c));
      return b;
    });
    const sw = interruptor(luz.en_linea ? "" : "Sin conexión", encendida, async (si) => {
      encendida = si; pintarMuestra(color, si);
      const ok = await enviarLuz(luz.id, { encendida: si });
      if (!ok) { encendida = !si; pintarMuestra(color, encendida); }
      return ok;
    }, !luz.en_linea);
    sw.querySelector("input").ariaLabel = "Encender " + luz.nombre;
    return el("div", { class: "hogar-luz" + (luz.en_linea ? "" : " sin-conexion") },
      el("div", { class: "hogar-luz-cab" }, muestra, el("strong", null, luz.nombre), sw),
      el("div", { class: "hogar-brillo" }, brillo, valor),
      el("div", { class: "hogar-colores" }, ...rapidos, selector));
  }

  function sinConfigurarCuerpo(variables) {
    return el("div", null, nota("Sin configurar. Añade en el archivo .env de ARIA:"),
      el("ul", { class: "hogar-variables" }, ...variables.map((v) => el("li", null, el("code", null, v)))),
      nota("Después reinicia ARIA (docker compose up -d)."));
  }
  function dialogo(titulo, ...contenido) {
    const cerrar = el("button", { type: "button", class: "dialogo-cerrar", ariaLabel: "Cerrar" }, "×");
    const d = el("dialog", { class: "dialogo hogar-dialogo" }, el("header", { class: "dialogo-cab" }, el("h2", null, titulo), cerrar),
      el("div", { class: "dialogo-cuerpo" }, ...contenido));
    cerrar.addEventListener("click", () => d.close());
    d.addEventListener("close", () => d.remove());
    document.body.append(d);
    d.showModal();
    return d;
  }
  // Sección con su esqueleto de carga: se rellena cuando llegan sus datos, sin esperar a las demás.
  function seccion(id, titulo, extra) {
    return el("section", { class: "tarjeta hogar-seccion", id: "hogar-" + id, ariaBusy: "true" },
      el("div", { class: "tarjeta-cab hogar-seccion-cab" }, el("h2", null, titulo), extra || null),
      el("div", { class: "hogar-seccion-cuerpo" }, el("div", { class: "hogar-esqueleto" }), el("div", { class: "hogar-esqueleto corto" })));
  }
  function rellenar(id, ...contenido) {
    const s = $("hogar-" + id);
    if (!s) return;
    s.ariaBusy = "false";
    s.querySelector(".hogar-seccion-cuerpo").replaceChildren(...contenido.filter(Boolean));
  }
  async function cargar(ruta) {
    const mia = generacion;
    const r = await api(ruta);
    return activo && mia === generacion ? r : null;
  }

  // --- Franja de resumen -------------------------------------------------------------------------------------------
  function pintarResumen() {
    const chips = [];
    const chip = (texto, destino, tono) => {
      const b = el("button", { type: "button", class: "hogar-chip" + (tono ? " " + tono : "") }, texto);
      b.addEventListener("click", () => $("hogar-" + destino)?.scrollIntoView({ behavior: "smooth", block: "start" }));
      chips.push(b);
    };
    const cams = estado.camaras?.datos;
    if (cams?.length) {
      const tapadas = cams.filter((c) => c.privacidad).length, dormidas = cams.filter((c) => !c.en_linea).length;
      chip(cams.length + " cámaras" + (tapadas ? " · " + tapadas + " tapada" + (tapadas > 1 ? "s" : "") : "") + (dormidas ? " · " + dormidas + " sin respuesta" : ""), "camaras", dormidas ? "aviso" : "");
    }
    const luces = estado.luces?.datos;
    if (luces?.length) chip(luces.filter((l) => l.encendida).length + " de " + luces.length + " luces encendidas", "luces");
    const v = estado.vigilancia;
    if (v?.disponible) chip(!v.activa ? "Vigilancia desactivada" : v.estado === "fuera" ? "No hay nadie: la cámara vigila" : "Hay alguien en casa", "casa", v.activa && v.estado === "fuera" ? "aviso" : "");
    const r = estado.router?.datos;
    if (r && r.conectados !== undefined) chip(r.conectados + " dispositivos en la wifi", "casa");
    const nuevos = (estado.eventos || []).filter((e) => !e.visto).length;
    if (nuevos) chip(nuevos + (nuevos > 1 ? " detecciones nuevas" : " detección nueva"), "eventos", "aviso");
    $("hogar-resumen")?.replaceChildren(...chips);
  }

  // --- Luces -------------------------------------------------------------------------------------------------------
  function luces(d) {
    if (!d.configurado) return sinConfigurarCuerpo(["ARIA_GOVEE_API_KEY"]);
    if (d.error) return nota(d.error);
    const lista = d.datos || [];
    if (!lista.length) return nota("Govee no tiene luces en tu cuenta.");
    const apagar = el("button", { type: "button", class: "fantasma pequeno" }, "Apagar todas");
    apagar.addEventListener("click", async () => {
      apagar.disabled = true;
      for (const l of lista.filter((x) => x.encendida && x.en_linea)) await enviarLuz(l.id, { encendida: false });   // de una en una: la API limita
      apagar.disabled = false;
      cargarLuces();
    });
    return el("div", null, el("div", { class: "hogar-luces" }, ...lista.map(filaLuz)), lista.length > 1 ? el("div", { class: "botones" }, apagar) : null);
  }

  // Cuadrícula como la de la app Tapo: imagen de cada cámara (reciente, sin despertar a las de batería a cada visita)
  // y, al tocarla, el directo con sus controles.
  function camaras(d) {
    if (!d.configurado) return sinConfigurarCuerpo(["ARIA_TAPO_USUARIO", "ARIA_TAPO_PASSWORD", "ARIA_TAPO_CAMARAS (IPs)"]);
    if (d.error) return nota(d.error);
    if (!(d.datos || []).length) return nota("No he encontrado cámaras Tapo en la red.");
    const mosaico = el("div", { class: "camaras-mosaico" }, ...d.datos.map((c) => {
      const img = el("img", { alt: "", loading: "lazy", class: "camara-mini-img" });
      const aviso = el("span", { class: "camara-mini-aviso" }, c.en_linea ? (c.privacidad ? "Privacidad activada" : "Cargando imagen…") : "Sin respuesta (¿dormida?)");
      if (c.en_linea && !c.privacidad) {
        img.addEventListener("load", () => { aviso.hidden = true; });
        img.addEventListener("error", () => { img.hidden = true; aviso.textContent = "Toca para ver en directo"; });
        img.src = "/api/hogar/camaras/foto?miniatura=1&ip=" + encodeURIComponent(c.ip);
      }
      const insignias = el("span", { class: "camara-mini-insignias" },
        c.privacidad ? el("span", { class: "pildora" }, "Privacidad") : null,
        c.bateria !== undefined ? el("span", { class: "pildora" + (c.bateria < 20 ? " mal" : "") }, "Batería " + c.bateria + " %") : null,
        c.ptz ? el("span", { class: "pildora" }, "Motorizada") : null);
      const b = el("button", { type: "button", class: "camara-mini", disabled: !c.en_linea, ariaLabel: "Ver en directo " + c.nombre },
        el("span", { class: "camara-mini-imagen" }, img, aviso, el("span", { class: "camara-mini-play", ariaHidden: "true" }, "▶")),
        el("span", { class: "camara-mini-pie" }, el("strong", null, c.nombre), el("span", { class: "muted" }, c.modelo)), insignias);
      b.addEventListener("click", () => CamaraDirecto.abrir(c, () => cargarCamaras()));
      return b;
    }));
    return mosaico;
  }

  // --- Eventos: detecciones de las cámaras con la casa vacía --------------------------------------------------------
  const cuando = (ts) => {
    const f = new Date(ts * 1000), hoy = new Date(), hora = f.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });
    const dia = (x) => x.toDateString();
    if (dia(f) === dia(hoy)) return "hoy " + hora;
    const ayer = new Date(hoy); ayer.setDate(hoy.getDate() - 1);
    if (dia(f) === dia(ayer)) return "ayer " + hora;
    return f.toLocaleDateString("es-ES", { day: "numeric", month: "short" }) + " " + hora;
  };
  function eventos(lista) {
    return el("div", { class: "hogar-eventos" }, ...lista.slice(0, 10).map((e) => {
      const miniatura = el("span", { class: "hogar-evento-foto" }, e.tiene_foto ? el("img", { alt: "", loading: "lazy", src: "/api/hogar/eventos/" + e.id + "/foto" }) : el("span", { class: "muted" }, "Sin foto"));
      const ver = el("button", { type: "button", class: "fantasma pequeno" }, "Ver vídeo");
      ver.addEventListener("click", () => {
        const camara = (estado.camaras?.datos || []).find((c) => c.ip === e.ip) || { ip: e.ip, nombre: e.nombre };
        CamaraDirecto.abrirGrabacion(camara, e.dia, e.inicio, e.fin, () => cargarCamaras());
      });
      return el("div", { class: "hogar-evento" + (e.visto ? "" : " nuevo") }, miniatura,
        el("div", { class: "hogar-evento-info" }, el("strong", null, "Movimiento · " + e.nombre), el("span", { class: "muted" }, cuando(e.inicio))), ver);
    }));
  }
  async function cargarEventos() {
    const r = await cargar("/api/hogar/eventos?limite=10");
    if (!r) return;
    const s = $("hogar-eventos");
    estado.eventos = r.ok ? r.data.eventos || [] : [];
    if (!estado.eventos.length) { s?.remove(); pintarResumen(); return; }   // la sección solo aparece si hay algo
    if (s) s.hidden = false;
    rellenar("eventos", eventos(estado.eventos), nota("Detecciones de las cámaras mientras no había nadie en casa (últimos 30 días)."));
    pintarResumen();
    if (estado.eventos.some((e) => !e.visto)) api("/api/hogar/eventos/vistos", { method: "POST" });
  }

  // --- Casa: vigilancia automática y wifi ---------------------------------------------------------------------------
  const hace = (ts) => { if (!ts) return "aún no visto"; const m = Math.round((Date.now() / 1000 - ts) / 60); return m < 3 ? "en casa" : "fuera hace " + (m < 120 ? m + " min" : Math.round(m / 60) + " h"); };
  function vigilancia(v) {
    if (!v?.disponible) return null;
    const titulo = !v.activa ? "Desactivada" : v.estado === "fuera" ? "No hay nadie en casa: la cámara vigila" : "Hay alguien en casa: la cámara está tapada";
    const configurar = el("button", { type: "button", class: "fantasma pequeno" }, "Configurar");
    configurar.addEventListener("click", () => configurarVigilancia(v));
    return el("div", { class: "hogar-bloque" },
      el("div", { class: "hogar-bloque-cab" }, el("h3", null, "Vigilancia automática"), configurar),
      el("p", { class: "hogar-estado" + (v.activa ? (v.estado === "fuera" ? " aviso" : " ok") : "") }, el("span", { class: "hogar-punto", ariaHidden: "true" }), titulo),
      v.moviles.length ? el("div", { class: "hogar-moviles" }, ...v.moviles.map((m) =>
        el("span", { class: "pildora" + (m.en_casa || hace(m.ultima_vez) === "en casa" ? " ok" : "") }, m.nombre + " · " + (m.en_casa ? "en casa" : hace(m.ultima_vez))))) : nota("Elige los móviles de la familia en «Configurar»."));
  }
  async function configurarVigilancia(v) {
    const cuerpo = el("div", { class: "hogar-config" }, nota("Buscando los dispositivos de la red…"));
    const d = dialogo("Vigilancia automática", cuerpo);
    const r = await api("/api/hogar/vigilancia?candidatos=1");   // incluye los dormidos (concesiones DHCP)
    if (!d.open) return;
    const datos = r.ok ? r.data : v;
    const pareceMovil = (n) => /pixel|galaxy|s2\d|xiaomi|redmi|poco|iphone|android|oppo|realme|oneplus|motorola|honor|huawei/i.test(n);
    const fila = (m, elegido) => el("label", { class: "hogar-opcion" }, el("input", { type: "checkbox", checked: elegido, value: m.id }), el("span", null, m.nombre));
    const elegidos = datos.moviles.map((m) => fila(m, true));
    const otros = [...(datos.candidatos || [])].sort((a, b) => pareceMovil(b.nombre) - pareceMovil(a.nombre) || a.nombre.localeCompare(b.nombre)).map((m) => fila(m, false));
    const cams = (estado.camaras?.datos || []).filter((c) => c.privacidad !== undefined).map((c) =>
      el("label", { class: "hogar-opcion" }, el("input", { type: "checkbox", checked: datos.camaras.includes(c.ip), value: c.ip }), el("span", null, c.nombre)));
    const minutos = el("select", { ariaLabel: "Minutos fuera antes de vigilar" }, ...[5, 10, 15, 20, 30, 60].map((n) => el("option", { value: n, selected: n === datos.minutos }, n + " minutos")));
    const activa = el("input", { type: "checkbox", checked: datos.activa });
    const guardar = el("button", { type: "button", class: "primario" }, "Guardar");
    guardar.addEventListener("click", async () => {
      const marcados = (filas) => filas.map((l) => l.querySelector("input")).filter((c) => c.checked).map((c) => c.value);
      const res = await api("/api/hogar/vigilancia", { method: "POST", json: { activa: activa.checked, minutos: Number(minutos.value), moviles: marcados([...elegidos, ...otros]), camaras: marcados(cams) } });
      if (!res.ok) { toast(res.data.error || "No se pudo guardar.", "mal"); return; }
      toast("Vigilancia guardada."); d.close(); cargarCasa();
    });
    cuerpo.replaceChildren(
      el("label", { class: "interruptor hogar-interruptor" }, activa, el("span", null, "Activada")),
      nota("Cuando todos estos móviles lleven el tiempo elegido fuera de la wifi (o sin contestar), ARIA destapa las cámaras marcadas; en cuanto vuelve uno, las tapa. Si el router no responde, no cambia nada."),
      el("h3", null, "Móviles de la familia"), elegidos.length ? el("div", { class: "hogar-opciones" }, ...elegidos) : nota("Aún no has elegido ninguno."),
      otros.length ? el("details", { class: "hogar-anadir" }, el("summary", null, "Añadir otro móvil"), el("div", { class: "hogar-opciones" }, ...otros)) : null,
      el("h3", null, "Cámaras"), cams.length ? el("div", { class: "hogar-opciones" }, ...cams) : nota("No hay cámaras con modo privacidad."),
      el("label", { class: "hogar-opcion" }, el("span", null, "Tiempo fuera:"), minutos),
      el("div", { class: "botones" }, guardar));
  }
  function wifi(d) {
    if (!d) return null;
    if (!d.configurado) return el("div", { class: "hogar-bloque" }, el("h3", null, "Wifi"), sinConfigurarCuerpo(["ARIA_ROUTER_PASSWORD", "ARIA_ROUTER_IP (opcional)"]));
    if (d.error) return el("div", { class: "hogar-bloque" }, el("h3", null, "Wifi"), nota(d.error));
    const r = d.datos || {};
    const invitados = r.invitados_24 !== undefined || r.invitados_5 !== undefined
      ? interruptor("Wifi de invitados", r.invitados_24 || r.invitados_5, async (si) => {
        const res = await api("/api/hogar/router/invitados", { method: "POST", json: { activa: si } });
        if (!res.ok) toast(res.data.error || "No se pudo cambiar la wifi de invitados.", "mal");
        return res.ok;
      }) : null;
    const ver = el("button", { type: "button", class: "fantasma pequeno" }, "Ver dispositivos");
    ver.addEventListener("click", () => dialogo("Conectados a la wifi (" + (r.conectados || 0) + ")",
      el("ul", { class: "filas hogar-clientes" }, ...(r.clientes || []).map((c) => el("li", { class: "fila" },
        el("div", { class: "fila-info" }, el("strong", null, c.nombre), el("span", { class: "muted" }, [c.ip, c.banda].filter(Boolean).join(" · "))))))));
    const reiniciar = el("button", { type: "button", class: "peligro pequeno" }, "Reiniciar router");
    reiniciar.addEventListener("click", async () => {
      if (!await confirmar("Reiniciar el router", "Se cortará internet en casa unos 2 minutos (ARIA incluida).", "Reiniciar")) return;
      reiniciar.disabled = true;
      const res = await api("/api/hogar/router/reiniciar", { method: "POST" });
      toast(res.ok ? "Reiniciando el router: vuelve en un par de minutos." : res.data.error || "No se pudo reiniciar.", res.ok ? "" : "mal");
    });
    return el("div", { class: "hogar-bloque" },
      el("div", { class: "hogar-bloque-cab" }, el("h3", null, "Wifi"), el("span", { class: "muted" }, r.modelo || "")),
      el("p", { class: "hogar-cifra" }, el("strong", null, String(r.conectados ?? "–")), el("span", { class: "muted" }, " dispositivos conectados")),
      invitados, el("div", { class: "botones" }, ver, reiniciar));
  }

  // --- Carga por secciones ------------------------------------------------------------------------------------------
  async function cargarCamaras() {
    const r = await cargar("/api/hogar/camaras");
    if (!r) return;
    estado.camaras = r.ok ? r.data : { configurado: true, error: r.data.error || "No se pudo consultar las cámaras." };
    rellenar("camaras", camaras(estado.camaras), estado.camaras.datos?.length ? nota("Toca una cámara para verla en directo, moverla, hablar o ver sus grabaciones.") : null);
    pintarResumen();
  }
  async function cargarLuces() {
    const r = await cargar("/api/hogar/luces");
    if (!r) return;
    estado.luces = r.ok ? r.data : { configurado: true, error: r.data.error || "No se pudieron consultar las luces." };
    rellenar("luces", luces(estado.luces));
    pintarResumen();
  }
  async function cargarCasa() {
    const [v, r] = await Promise.all([cargar("/api/hogar/vigilancia"), cargar("/api/hogar/router")]);
    if (!v && !r) return;
    estado.vigilancia = v?.ok ? v.data : null;
    estado.router = r?.ok ? r.data : r ? { configurado: true, error: r.data.error || "No se pudo consultar el router." } : null;
    rellenar("casa", vigilancia(estado.vigilancia), wifi(estado.router));
    pintarResumen();
  }
  function pintar() {
    generacion++;
    const cuerpo = $("hogar-cuerpo");
    const partes = [el("div", { class: "hogar-resumen", id: "hogar-resumen", role: "status" })];
    if (Sesion.verCamaras) partes.push(seccion("camaras", "Cámaras"));
    if (Sesion.esAdmin) { const ev = seccion("eventos", "Eventos"); ev.hidden = true; partes.push(ev); }
    // Luces y Casa: solo administradores. Un usuario con permiso solo ve las cámaras.
    if (Sesion.esAdmin) partes.push(el("div", { class: "hogar-columnas" }, seccion("luces", "Luces"), seccion("casa", "Casa")));
    else if (!Sesion.verCamaras) partes.push(nota("Aquí no tienes nada que ver todavía: pídele al administrador acceso a las cámaras."));
    cuerpo.replaceChildren(...partes);
    if (Sesion.verCamaras) cargarCamaras();
    if (Sesion.esAdmin) { cargarCasa(); cargarLuces(); cargarEventos(); }
  }
  return { iniciar() {}, activar(si) { const antes = activo; activo = si; if (si && !antes) pintar(); } };
})();
