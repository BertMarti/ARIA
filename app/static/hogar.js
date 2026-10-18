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

  function camaras(d) {
    if (!d.configurado) return sinConfigurar("Cámaras", ["ARIA_TAPO_USUARIO", "ARIA_TAPO_PASSWORD", "ARIA_TAPO_CAMARAS (opcional: IPs)"]);
    if (d.error) return tarjeta("Cámaras", nota(d.error));
    if (!(d.datos || []).length) return tarjeta("Cámaras", nota("No he encontrado cámaras Tapo en la red."));
    return tarjeta("Cámaras", ...d.datos.map((c) => el("div", { class: "hogar-fila" },
      el("div", null, el("strong", null, c.nombre), el("span", { class: "muted" }, " · " + c.modelo + " · " + (c.en_linea ? "en línea" : "sin respuesta"))),
      c.privacidad === undefined ? nota("Sin modo privacidad") : interruptor("Privacidad (lente tapada)", c.privacidad, async (si) => {
        const r = await api("/api/hogar/camaras/privacidad", { method: "POST", json: { ip: c.ip, activa: si } });
        if (!r.ok) toast(r.data.error || "No se pudo cambiar la privacidad.", "mal");
        else toast(si ? "Cámara tapada." : "Cámara destapada.");
        return r.ok;
      }, !c.en_linea))));
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

  async function pintar() {
    const cuerpo = $("hogar-cuerpo");
    const r = await api("/api/hogar");
    if (!activo) return;
    if (!r.ok) { cuerpo.replaceChildren(nota(r.data.error || "No se pudo consultar el hogar.")); return; }
    const partes = [luces(r.data.luces)];
    if (r.data.camaras) partes.push(camaras(r.data.camaras));
    if (r.data.router) partes.push(router(r.data.router));
    cuerpo.replaceChildren(...partes);
  }
  return { iniciar() {}, activar(si) { const antes = activo; activo = si; if (si && !antes) pintar(); } };
})();
