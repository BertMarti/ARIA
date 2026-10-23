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


  // --- Escenas: varias luces y cámaras de un toque -----------------------------------------------------------------
  const ICONOS_ESCENA = {   // trazos de 24×24 (sin emojis: en la Pi no hay fuente para ellos)
    luz: "M9 18h6M10 21h4M12 3a6 6 0 0 0-4 10.5c.7.7 1 1.5 1 2.5h6c0-1 .3-1.8 1-2.5A6 6 0 0 0 12 3z",
    cine: "M3 6h18v12H3zM3 10h18M7 6v4M12 6v4M17 6v4",
    noche: "M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z",
    salir: "M14 4h5v16h-5M10 12h10M6 8l-4 4 4 4M2 12h8",
    casa: "m3 11 9-8 9 8v9H3zM9 20v-6h6v6",
    fiesta: "M5 21 9 9l6 6-10 6zM14 4l1 2M19 5l-2 1M20 10h-2M12 2v2",
    lectura: "M4 5h7a2 2 0 0 1 2 2v13a2 2 0 0 0-2-2H4zM20 5h-5a2 2 0 0 0-2 2v13a2 2 0 0 1 2-2h5z",
    despertar: "M12 3v2M4.9 6.9l1.4 1.4M3 14h2M19 14h2M17.7 8.3l1.4-1.4M7 18a5 5 0 0 1 10 0M3 21h18",
  };
  function iconoEscena(clave) {
    const NS = "http://www.w3.org/2000/svg", svg = document.createElementNS(NS, "svg"), p = document.createElementNS(NS, "path");
    svg.setAttribute("viewBox", "0 0 24 24"); svg.setAttribute("class", "svg-ico"); svg.setAttribute("aria-hidden", "true");
    p.setAttribute("d", ICONOS_ESCENA[clave] || ICONOS_ESCENA.luz);
    svg.append(p);
    return svg;
  }
  function escenas(d) {
    const lista = d.escenas || [];
    const nueva = el("button", { type: "button", class: "fantasma pequeno" }, "＋ Nueva");
    nueva.addEventListener("click", () => editarEscena(null, d.iconos));
    if (!lista.length) return [nota("Crea una escena para cambiar varias luces y cámaras de un toque (por ejemplo «Cine» o «Buenas noches»). También puedes pedírsela a ARIA en el chat."), el("div", { class: "botones" }, nueva)];
    const botones = lista.map((e) => {
      const prog = e.programa ? (e.programa.hora || (e.programa.sol === "anochecer" ? "anochecer" : "amanecer")) : "";
      const b = el("button", { type: "button", class: "hogar-escena" }, iconoEscena(e.icono), el("span", null, e.nombre),
        prog ? el("span", { class: "hogar-escena-prog-chip", title: "Se activa sola" }, prog) : null);
      b.addEventListener("click", async () => {
        b.disabled = true; b.classList.add("activando");
        const r = await api("/api/hogar/escenas/" + e.id + "/activar", { method: "POST" });
        b.disabled = false; b.classList.remove("activando");
        if (!r.ok) { toast(r.data.error || "No se pudo activar la escena.", "mal"); return; }
        toast(r.data.fallidas?.length ? "«" + e.nombre + "»: no ha respondido " + r.data.fallidas.join(", ") + "." : "Escena «" + e.nombre + "» activada.", r.data.fallidas?.length ? "mal" : "");
        cargarLuces(); if (Sesion.verCamaras) cargarCamaras();
      });
      const editar = el("button", { type: "button", class: "hogar-escena-editar", ariaLabel: "Editar " + e.nombre }, "⋯");
      editar.addEventListener("click", () => editarEscena(e, d.iconos));
      return el("div", { class: "hogar-escena-caja" }, b, editar);
    });
    return [el("div", { class: "hogar-escenas" }, ...botones), el("div", { class: "botones" }, nueva)];
  }
  function editarEscena(escena, iconos) {
    const previa = new Map((escena?.acciones || []).map((a) => [a.tipo + ":" + (a.id || a.ip), a]));
    const nombre = el("input", { type: "text", maxLength: 30, value: escena?.nombre || "", placeholder: "Cine, Buenas noches…", ariaLabel: "Nombre de la escena" });
    let icono = escena?.icono || "luz";
    const iconosFila = el("div", { class: "hogar-escena-iconos", role: "radiogroup", ariaLabel: "Icono" }, ...(iconos || Object.keys(ICONOS_ESCENA)).map((k) => {
      const b = el("button", { type: "button", class: "hogar-escena-icono" + (k === icono ? " activo" : ""), role: "radio", ariaChecked: String(k === icono), ariaLabel: k }, iconoEscena(k));
      b.addEventListener("click", () => {
        icono = k;
        iconosFila.querySelectorAll("button").forEach((x) => { x.classList.toggle("activo", x === b); x.ariaChecked = String(x === b); });
      });
      return b;
    }));
    const filas = [];
    for (const luz of estado.luces?.datos || []) {
      const a = previa.get("luz:" + luz.id);
      const que = el("select", { ariaLabel: "Qué hacer con " + luz.nombre },
        el("option", { value: "", selected: !a }, "No tocar"), el("option", { value: "on", selected: !!a?.encendida }, "Encender"),
        el("option", { value: "off", selected: a && !a.encendida }, "Apagar"));
      const brillo = el("input", { type: "range", min: 1, max: 100, value: a?.brillo || 100, ariaLabel: "Brillo de " + luz.nombre });
      const color = el("input", { type: "color", value: a?.color || luz.color || "#ffffff", ariaLabel: "Color de " + luz.nombre });
      const conColor = el("input", { type: "checkbox", checked: !!a?.color });
      const extra = el("div", { class: "hogar-escena-extra" }, brillo, el("label", { class: "hogar-opcion" }, conColor, el("span", null, "Color:")), color);
      const ver = () => { extra.hidden = que.value !== "on"; };
      que.addEventListener("change", ver); ver();
      filas.push({ fila: el("div", { class: "hogar-escena-fila" }, el("strong", null, luz.nombre), que, extra),
        leer: () => que.value === "" ? null : que.value === "off" ? { tipo: "luz", id: luz.id, encendida: false }
          : { tipo: "luz", id: luz.id, encendida: true, brillo: Number(brillo.value), ...(conColor.checked ? { color: color.value } : {}) } });
    }
    for (const c of (estado.camaras?.datos || []).filter((x) => x.privacidad !== undefined)) {
      const a = previa.get("camara:" + c.ip);
      const que = el("select", { ariaLabel: "Qué hacer con " + c.nombre },
        el("option", { value: "", selected: !a }, "No tocar"), el("option", { value: "tapar", selected: !!a?.privacidad }, "Tapar"),
        el("option", { value: "destapar", selected: a && !a.privacidad }, "Destapar"));
      filas.push({ fila: el("div", { class: "hogar-escena-fila" }, el("strong", null, c.nombre), que),
        leer: () => que.value === "" ? null : { tipo: "camara", ip: c.ip, privacidad: que.value === "tapar" } });
    }
    // Programación: a una hora o con el sol, los días elegidos.
    const p = escena?.programa;
    const modo = el("select", { ariaLabel: "Cuándo se activa sola" },
      el("option", { value: "", selected: !p }, "Solo cuando la active"), el("option", { value: "hora", selected: !!p?.hora }, "A una hora"),
      el("option", { value: "anochecer", selected: p?.sol === "anochecer" }, "Al anochecer"), el("option", { value: "amanecer", selected: p?.sol === "amanecer" }, "Al amanecer"));
    const hora = el("input", { type: "time", value: p?.hora || "23:30", ariaLabel: "Hora" });
    const desfase = el("select", { ariaLabel: "Antes o después" }, ...[[-60, "1 h antes"], [-30, "30 min antes"], [0, "en el momento"], [30, "30 min después"], [60, "1 h después"]]
      .map(([v, t]) => el("option", { value: v, selected: (p?.desfase || 0) === v }, t)));
    const NOMBRES_DIAS = ["L", "M", "X", "J", "V", "S", "D"];
    const dias = NOMBRES_DIAS.map((n, i) => el("label", { class: "hogar-dia" }, el("input", { type: "checkbox", value: i, checked: p ? p.dias.includes(i) : true }), el("span", null, n)));
    const opcionesProg = el("div", { class: "hogar-escena-prog" }, hora, desfase, el("div", { class: "hogar-dias", role: "group", ariaLabel: "Días" }, ...dias));
    const verProg = () => { opcionesProg.hidden = !modo.value; hora.hidden = modo.value !== "hora"; desfase.hidden = !["anochecer", "amanecer"].includes(modo.value); };
    modo.addEventListener("change", verProg); verProg();
    const leerPrograma = () => {
      if (!modo.value) return null;
      const d = dias.map((l) => l.querySelector("input")).filter((c) => c.checked).map((c) => Number(c.value));
      return modo.value === "hora" ? { hora: hora.value, dias: d } : { sol: modo.value, desfase: Number(desfase.value), dias: d };
    };
    const guardar = el("button", { type: "button", class: "primario" }, "Guardar");
    const borrar = escena ? el("button", { type: "button", class: "peligro" }, "Borrar") : null;
    const d = dialogo(escena ? "Editar escena" : "Nueva escena",
      el("label", { class: "hogar-campo" }, el("span", null, "Nombre"), nombre), iconosFila,
      filas.length ? el("div", { class: "hogar-escena-filas" }, ...filas.map((f) => f.fila)) : nota("No hay luces ni cámaras cargadas todavía."),
      el("h3", null, "Programar"), el("label", { class: "hogar-opcion" }, modo), opcionesProg,
      el("div", { class: "botones" }, borrar, guardar));
    guardar.addEventListener("click", async () => {
      const acciones = filas.map((f) => f.leer()).filter(Boolean);
      if (!acciones.length) { toast("Elige qué hacer con al menos una luz o cámara.", "mal"); return; }
      guardar.disabled = true;
      const r = await api("/api/hogar/escenas" + (escena ? "/" + escena.id : ""), { method: escena ? "PUT" : "POST", json: { nombre: nombre.value, icono, acciones, programa: leerPrograma() } });
      guardar.disabled = false;
      if (!r.ok) { toast(r.data.error || "No se pudo guardar.", "mal"); return; }
      toast("Escena guardada."); d.close(); cargarEscenas();
    });
    borrar?.addEventListener("click", async () => {
      if (!await confirmar("Borrar escena", "Se borrará «" + escena.nombre + "».", "Borrar")) return;
      const r = await api("/api/hogar/escenas/" + escena.id, { method: "DELETE" });
      if (!r.ok) { toast(r.data.error || "No se pudo borrar.", "mal"); return; }
      d.close(); cargarEscenas();
    });
  }

  // --- Casa: vigilancia automática y wifi ---------------------------------------------------------------------------
  const hace = (ts) => { if (!ts) return "aún no visto"; const m = Math.round((Date.now() / 1000 - ts) / 60); return m < 3 ? "en casa" : "fuera hace " + (m < 120 ? m + " min" : Math.round(m / 60) + " h"); };
  function vigilancia(v) {
    if (!v?.disponible) return null;
    const titulo = !v.activa ? "Desactivada" : v.estado === "fuera" ? "No hay nadie en casa: la cámara vigila" : "Hay alguien en casa: la cámara está tapada";
    const configurar = el("button", { type: "button", class: "fantasma pequeno" }, "Configurar");
    configurar.addEventListener("click", () => configurarVigilancia(v));
    const ver = el("button", { type: "button", class: "fantasma pequeno" }, "Historial");
    ver.addEventListener("click", historialPresencia);
    return el("div", { class: "hogar-bloque" },
      el("div", { class: "hogar-bloque-cab" }, el("h3", null, "Vigilancia automática"), el("div", { class: "botones" }, v.moviles.length ? ver : null, configurar)),
      el("p", { class: "hogar-estado" + (v.activa ? (v.estado === "fuera" ? " aviso" : " ok") : "") }, el("span", { class: "hogar-punto", ariaHidden: "true" }), titulo),
      v.moviles.length ? el("div", { class: "hogar-moviles" }, ...v.moviles.map((m) =>
        el("span", { class: "pildora" + (m.en_casa || hace(m.ultima_vez) === "en casa" ? " ok" : "") }, m.nombre + " · " + (m.en_casa ? "en casa" : hace(m.ultima_vez))))) : nota("Elige los móviles de la familia en «Configurar»."));
  }
  async function historialPresencia() {
    const cuerpo = el("div", null, nota("Cargando…"));
    const d = dialogo("Quién llega y quién se va", cuerpo);
    const r = await api("/api/hogar/vigilancia/historial");
    if (!d.open) return;
    const filas = r.ok ? r.data.historial : [];
    cuerpo.replaceChildren(!r.ok ? nota(r.data.error || "No se pudo cargar el historial.")
      : !filas.length ? nota("Aún no hay movimientos: se apuntan a partir de ahora, cuando un móvil sale o vuelve a casa.")
        : el("ul", { class: "filas hogar-historial" }, ...filas.map((h) => el("li", { class: "fila" },
          el("span", { class: "pildora" + (h.evento === "llega" ? " ok" : "") }, h.evento === "llega" ? "Llega" : "Se va"),
          el("div", { class: "fila-info" }, el("strong", null, h.nombre), el("span", { class: "muted" }, cuando(h.ts)))))),
      nota("La salida se apunta con la hora en que el móvil se vio por última vez en la wifi."));
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
    const luces = el("input", { type: "checkbox", checked: !!datos.apagar_luces });
    const llegada = el("select", { ariaLabel: "Escena al llegar de noche" }, el("option", { value: "" }, "Ninguna"),
      ...(estado.escenas?.escenas || []).map((e) => el("option", { value: e.id, selected: e.id === datos.escena_llegada }, e.nombre)));
    const guardar = el("button", { type: "button", class: "primario" }, "Guardar");
    guardar.addEventListener("click", async () => {
      const marcados = (filas) => filas.map((l) => l.querySelector("input")).filter((c) => c.checked).map((c) => c.value);
      const res = await api("/api/hogar/vigilancia", { method: "POST", json: { activa: activa.checked, apagar_luces: luces.checked, escena_llegada: llegada.value ? Number(llegada.value) : null, minutos: Number(minutos.value), moviles: marcados([...elegidos, ...otros]), camaras: marcados(cams) } });
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
      el("label", { class: "hogar-opcion" }, luces, el("span", null, "Al irnos todos, apagar las luces que se hayan quedado encendidas")),
      el("label", { class: "hogar-opcion" }, el("span", null, "Cuando llegue el primero y sea de noche, activar:"), llegada),
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
  async function cargarEscenas() {
    const r = await cargar("/api/hogar/escenas");
    if (!r) return;
    estado.escenas = r.ok ? r.data : null;
    rellenar("escenas", ...(r.ok ? escenas(r.data) : [nota(r.data.error || "No se pudieron cargar las escenas.")]));
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
    if (Sesion.esAdmin) partes.push(seccion("escenas", "Escenas"));
    if (Sesion.esAdmin) { const ev = seccion("eventos", "Eventos"); ev.hidden = true; partes.push(ev); }
    // Luces y Casa: solo administradores. Un usuario con permiso solo ve las cámaras.
    if (Sesion.esAdmin) partes.push(el("div", { class: "hogar-columnas" }, seccion("luces", "Luces"), seccion("casa", "Casa")));
    else if (!Sesion.verCamaras) partes.push(nota("Aquí no tienes nada que ver todavía: pídele al administrador acceso a las cámaras."));
    cuerpo.replaceChildren(...partes);
    if (Sesion.verCamaras) cargarCamaras();
    if (Sesion.esAdmin) { cargarCasa(); cargarLuces(); cargarEventos(); cargarEscenas(); }
  }
  return { iniciar() {}, activar(si) { const antes = activo; activo = si; if (si && !antes) pintar(); } };
})();
