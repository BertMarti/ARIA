"use strict";
// Hogar: luces Govee, cámaras Tapo y router TP-Link. Los cambios se ven al momento y se deshacen si fallan.
const Hogar = (() => {
  let activo = false;
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

  function luces(d) {
    if (!d.configurado) return sinConfigurar("Luces", ["ARIA_GOVEE_API_KEY"]);
    if (d.error) return tarjeta("Luces", nota(d.error));
    const lista = d.datos || [];
    if (!lista.length) return tarjeta("Luces", nota("Govee no tiene luces en tu cuenta."));
    const apagar = el("button", { type: "button", class: "fantasma" }, "Apagar todas");
    apagar.addEventListener("click", async () => {
      apagar.disabled = true;
      const encendidas = lista.filter((l) => l.encendida && l.en_linea);
      for (const l of encendidas) await enviarLuz(l.id, { encendida: false });   // de una en una: la API limita
      apagar.disabled = false;
      pintar();
    });
    return tarjeta("Luces", el("div", { class: "hogar-luces" }, ...lista.map(filaLuz)), el("div", { class: "botones" }, apagar));
  }

  // Cuadrícula como la de la app Tapo: imagen de cada cámara (reciente, sin despertar a las de batería a cada visita)
  // y, al tocarla, el directo con sus controles.
  function camaras(d) {
    if (!d.configurado) return sinConfigurar("Cámaras", ["ARIA_TAPO_USUARIO", "ARIA_TAPO_PASSWORD", "ARIA_TAPO_CAMARAS (IPs)"]);
    if (d.error) return tarjeta("Cámaras", nota(d.error));
    if (!(d.datos || []).length) return tarjeta("Cámaras", nota("No he encontrado cámaras Tapo en la red."));
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
      b.addEventListener("click", () => CamaraDirecto.abrir(c, () => pintar()));
      return b;
    }));
    const t = tarjeta("Cámaras", mosaico, nota("Toca una cámara para verla en directo y controlarla."));
    t.classList.add("hogar-camaras");
    return t;
  }

  function router(d) {
    if (!d.configurado) return sinConfigurar("Router", ["ARIA_ROUTER_PASSWORD", "ARIA_ROUTER_IP (opcional)"]);
    if (d.error) return tarjeta("Router", nota(d.error));
    const r = d.datos || {};
    const invitados = r.invitados_24 !== undefined || r.invitados_5 !== undefined
      ? interruptor("Wifi de invitados", r.invitados_24 || r.invitados_5, async (si) => {
        const res = await api("/api/hogar/router/invitados", { method: "POST", json: { activa: si } });
        if (!res.ok) toast(res.data.error || "No se pudo cambiar la wifi de invitados.", "mal");
        return res.ok;
      }) : null;
    const clientes = el("details", { class: "hogar-clientes" }, el("summary", null, (r.conectados || 0) + " dispositivos conectados"),
      el("ul", { class: "filas" }, ...(r.clientes || []).map((c) => el("li", { class: "fila" },
        el("div", { class: "fila-info" }, el("strong", null, c.nombre), el("span", { class: "muted" }, [c.ip, c.banda].filter(Boolean).join(" · ")))))));
    const reiniciar = el("button", { type: "button", class: "peligro" }, "Reiniciar el router");
    reiniciar.addEventListener("click", async () => {
      if (!await confirmar("Reiniciar el router", "Se cortará internet en casa unos 2 minutos (ARIA incluida).", "Reiniciar")) return;
      reiniciar.disabled = true;
      const res = await api("/api/hogar/router/reiniciar", { method: "POST" });
      toast(res.ok ? "Reiniciando el router: vuelve en un par de minutos." : res.data.error || "No se pudo reiniciar.", res.ok ? "" : "mal");
    });
    return tarjeta("Router", el("p", null, el("strong", null, r.modelo || "TP-Link")), invitados, clientes, el("div", { class: "botones" }, reiniciar));
  }

  // Vigilancia automática: cámaras destapadas solo cuando todos los móviles elegidos llevan un rato fuera de casa.
  function vigilancia(v, camarasHogar) {
    if (!v || !v.disponible) return null;
    const hace = (ts) => { if (!ts) return "aún no visto"; const m = Math.round((Date.now() / 1000 - ts) / 60); return m < 3 ? "en casa" : "fuera hace " + (m < 120 ? m + " min" : Math.round(m / 60) + " h"); };
    // Solo los móviles elegidos a la vista; el resto de la red, plegado (los que parecen móviles, primero).
    const pareceMovil = (n) => /pixel|galaxy|s2\d|xiaomi|redmi|poco|iphone|android|oppo|realme|oneplus|motorola|honor|huawei/i.test(n);
    const fila = (m, elegido) => {
      const c = el("input", { type: "checkbox", checked: elegido, value: m.id });
      const info = elegido ? (m.en_casa ? "en casa" : hace(m.ultima_vez)) : "";
      return el("label", { class: "hogar-opcion" }, c, el("span", null, m.nombre), info ? el("span", { class: "muted" }, " · " + info) : null);
    };
    const elegidos = v.moviles.map((m) => fila(m, true));
    const otros = [...v.candidatos].sort((a, b) => pareceMovil(b.nombre) - pareceMovil(a.nombre) || a.nombre.localeCompare(b.nombre)).map((m) => fila(m, false));
    const casillas = [...elegidos, ...otros];
    const anadir = otros.length ? el("details", { class: "hogar-anadir" }, el("summary", null, "Añadir otro móvil"), el("div", { class: "hogar-opciones" }, ...otros)) : null;
    const cams = (camarasHogar || []).filter((c) => c.privacidad !== undefined).map((c) =>
      el("label", { class: "hogar-opcion" }, el("input", { type: "checkbox", checked: v.camaras.includes(c.ip), value: c.ip }), el("span", null, c.nombre)));
    const minutos = el("select", { ariaLabel: "Minutos fuera antes de vigilar" }, ...[5, 10, 15, 20, 30, 60].map((n) => el("option", { value: n, selected: n === v.minutos }, n + " minutos")));
    const guardar = async (activa) => {
      const json = { activa, minutos: Number(minutos.value),
        moviles: casillas.map((l) => l.querySelector("input")).filter((c) => c.checked).map((c) => c.value),
        camaras: cams.map((l) => l.querySelector("input")).filter((c) => c.checked).map((c) => c.value) };
      const r = await api("/api/hogar/vigilancia", { method: "POST", json });
      if (!r.ok) { toast(r.data.error || "No se pudo guardar.", "mal"); return false; }
      toast(activa ? "Vigilancia automática activada." : "Guardado."); return true;
    };
    const activa = interruptor("Activada", v.activa, (si) => guardar(si));
    const boton = el("button", { type: "button", class: "fantasma" }, "Guardar cambios");
    boton.addEventListener("click", () => guardar(activa.querySelector("input").checked));
    const estado = v.activa ? el("p", null, el("strong", null, v.estado === "fuera" ? "No hay nadie en casa: la cámara vigila." : "Hay alguien en casa: la cámara está tapada.")) : null;
    return tarjeta("Vigilancia automática", activa, estado,
      nota("Cuando todos estos móviles lleven el tiempo elegido fuera de la wifi, ARIA destapa las cámaras marcadas; en cuanto vuelve uno, las tapa otra vez. Si el router no responde, no cambia nada."),
      el("h3", null, "Móviles de la familia"), elegidos.length ? el("div", { class: "hogar-opciones" }, ...elegidos) : nota("Aún no has elegido ninguno."), anadir,
      el("h3", null, "Cámaras"), cams.length ? el("div", { class: "hogar-opciones" }, ...cams) : nota("No hay cámaras con modo privacidad."),
      el("label", { class: "hogar-opcion" }, el("span", null, "Tiempo fuera: "), minutos), el("div", { class: "botones" }, boton));
  }

  async function pintar() {
    const cuerpo = $("hogar-cuerpo");
    const r = await api("/api/hogar");
    if (!activo) return;
    if (!r.ok) { cuerpo.replaceChildren(nota(r.data.error || "No se pudo consultar el hogar.")); return; }
    const partes = [];
    if (r.data.camaras) partes.push(camaras(r.data.camaras));   // las cámaras, arriba y a todo el ancho
    partes.push(luces(r.data.luces));
    if (r.data.router) partes.push(router(r.data.router));
    if (Sesion.esAdmin) {
      const v = await api("/api/hogar/vigilancia");
      if (!activo) return;
      if (v.ok) partes.push(vigilancia(v.data, r.data.camaras?.datos));
    }
    cuerpo.replaceChildren(...partes.filter(Boolean));
  }
  return { iniciar() {}, activar(si) { const antes = activo; activo = si; if (si && !antes) pintar(); } };
})();
