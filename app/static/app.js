"use strict";
// Navegación entre vistas (Chat, Centro de control, Ajustes) con #hash.
(() => {
  const VISTAS = ["chat", "control", "ajustes"];
  function mostrar() {
    let v = location.hash.replace("#", "");
    if (!VISTAS.includes(v)) v = "chat";
    for (const n of VISTAS) $("v-" + n).hidden = n !== v;
    document.querySelectorAll(".nav-btn[data-vista]").forEach((b) => b.classList.toggle("activo", b.dataset.vista === v));
    Control.activar(v === "control");
    if (v === "ajustes") Ajustes.activar();
    document.title = "ARIA · " + { chat: "Chat", control: "Centro de control", ajustes: "Ajustes" }[v];
  }
  document.querySelectorAll(".nav-btn[data-vista]").forEach((b) => b.addEventListener("click", () => { location.hash = b.dataset.vista; }));
  window.addEventListener("hashchange", mostrar);
  Chat.iniciar(); Control.iniciar(); Ajustes.iniciar();
  api("/api/info").then(({ data }) => { if (data.modelo) $("modelo-activo").textContent = data.modelo; });
  if (new URLSearchParams(location.search).get("spotify")) history.replaceState(null, "", "/#ajustes");
  mostrar();
})();
