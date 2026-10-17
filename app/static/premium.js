"use strict";
// Estado y bloqueos visuales de Premium. El servidor siempre vuelve a comprobarlos.
const Premium = (() => {
  let datos = { funciones: {} };
  // Qué incluye cada versión (lo comprueba el servidor; esto solo lo explica).
  const TABLA = [
    ["Chat, voz, notas, agenda e información", "Sí", "Sí"],
    ["Bloqueo de anuncios, VPN y escaneo de la red", "Sí", "Sí"],
    ["Compartir: reproductor en el navegador", "Sí", "Sí"],
    ["Enviar a la tele", "No", "Sí"],
    ["Modo HUD y Cerebro", "No", "Sí"],
    ["«Arreglar lo que ARIA puede»", "Ver hallazgos", "Sí"],
    ["Finanzas", "Movimientos y CSV", "Además presupuestos, reglas y sugerencias"],
    ["Documentos con búsqueda inteligente", "Hasta 20", "Hasta 200"],
    ["Automatizaciones", "Hasta 3", "Hasta el máximo de ARIA"],
    ["Usuarios", "Hasta 2", "Sin límite"],
    ["App de Android", "1 móvil", "Varios móviles y Siri"],
  ];
  async function cargar() {
    const r = await api("/api/premium");
    if (!r.ok) return datos;
    datos = r.data;
    pintar();
    if (datos.exigir) {
      candado(document.querySelector('.nav-btn[data-vista="cerebro"]'), "cerebro");
      candado($("medios-enviar"), "tele");
      candado(document.querySelector('.mi-carta[href="#hud"]'), "hud");
      candado($("seg-arreglar"), "remedios");
    }
    return datos;
  }
  function irAPremium() { location.hash = "ajustes"; Ajustes.irSeccion("premium"); }
  // Vistas enteras de Premium (HUD y Cerebro): en lugar de la vista, una tarjeta que explica qué es y cómo tenerla.
  const VISTAS = { hud: ["hud", "El modo HUD convierte ARIA en una cabina de mando a pantalla completa."],
    cerebro: ["cerebro", "Cerebro dibuja en directo cómo piensa ARIA: agentes, herramientas y memoria."] };
  function vistaBloqueada(vista) {
    const def = VISTAS[vista], seccion = $("v-" + vista);
    seccion?.querySelector(".premium-muro")?.remove();
    if (!def || tiene(def[0])) return false;
    const boton = el("button", { type: "button", class: "primario" }, "Ver ARIA Premium");
    boton.addEventListener("click", irAPremium);
    seccion.prepend(el("div", { class: "premium-muro tarjeta" }, el("span", { class: "premium-insignia" }, "Premium"),
      el("h2", null, "Esto es de ARIA Premium"), el("p", { class: "muted" }, def[1]),
      el("p", { class: "muted" }, "Prueba Premium 14 días gratis, sin tarjeta."), boton));
    return true;
  }
  let ultimoAviso = 0;
  function avisar(e) {
    if (Date.now() - ultimoAviso < 4000) return;   // varias peticiones a la vez: un solo aviso
    ultimoAviso = Date.now();
    const b = window.PingCompa && PingCompa.decir("¡Eh, mira! " + e.detail.texto, [
      { texto: "Ver Premium", clase: "primario pequeno", accion: () => { PingCompa.ocultar(); irAPremium(); } },
      { texto: "Ahora no", clase: "fantasma pequeno", accion: () => PingCompa.ocultar() }]);
    if (!b) toast(e.detail.texto + " Mira Ajustes → ARIA Premium.", "aviso");
  }
  addEventListener("aria:premium", avisar);
  function tiene(id) { return datos.funciones?.[id] !== false; }
  function candado(elemento, id) {
    if (!elemento || tiene(id) || elemento.querySelector(".premium-insignia")) return elemento;
    elemento.classList.add("premium-bloqueado");
    elemento.setAttribute("aria-label", (elemento.getAttribute("aria-label") || elemento.textContent.trim()) + ". Requiere Premium");
    elemento.append(el("span", { class: "premium-insignia" }, "Premium"));
    elemento.addEventListener("click", (ev) => { ev.preventDefault(); ev.stopImmediatePropagation(); irAPremium(); }, true);
    return elemento;
  }
  function pintar() {
    const estado = $("premium-estado");
    if (!estado) return;
    const nombres = { gratis: "Gratis", prueba: "Prueba", premium: "Premium", gracia: "Periodo de gracia", caducada: "Caducada" };
    estado.className = "premium-estado premium-" + (datos.modo_prueba ? "prueba" : datos.estado);
    estado.textContent = datos.modo_prueba ? "Modo prueba" : nombres[datos.estado] || datos.estado;
    $("premium-nota").textContent = datos.modo_prueba ? "ARIA Premium aún está en pruebas: todo sigue desbloqueado."
      : datos.dias_restantes != null ? "Días restantes: " + datos.dias_restantes : "";
    const filas = TABLA.map(([nombre, gratis, pago]) => el("tr", null, el("td", null, nombre), el("td", null, gratis), el("td", null, pago)));
    $("premium-funciones").replaceChildren(...filas);
  }
  function iniciar() {
    $("premium-licencia")?.addEventListener("submit", async (ev) => { ev.preventDefault(); const r = await api("/api/premium/licencia", { method: "POST", json: { licencia: $("premium-texto").value.trim() } }); $("premium-msg").textContent = r.ok ? "Licencia activada." : (r.data.error || "No se pudo activar."); if (r.ok) cargar(); });
    $("premium-prueba")?.addEventListener("click", async () => { const r = await api("/api/premium/prueba", { method: "POST", json: {} }); toast(r.ok ? "Prueba iniciada." : (r.data.error || "No se pudo iniciar la prueba."), r.ok ? "" : "mal"); if (r.ok) cargar(); });
  }
  return { cargar, iniciar, tiene, candado, vistaBloqueada };
})();
