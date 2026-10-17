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
    }
    return datos;
  }
  function tiene(id) { return datos.funciones?.[id] !== false; }
  function candado(elemento, id) {
    if (!elemento || tiene(id) || elemento.querySelector(".premium-insignia")) return elemento;
    elemento.classList.add("premium-bloqueado");
    elemento.setAttribute("aria-label", (elemento.getAttribute("aria-label") || elemento.textContent.trim()) + ". Requiere Premium");
    elemento.append(el("span", { class: "premium-insignia" }, "Premium"));
    elemento.addEventListener("click", (ev) => { ev.preventDefault(); location.hash = "ajustes"; Ajustes.irSeccion("premium"); });
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
  return { cargar, iniciar, tiene, candado };
})();
