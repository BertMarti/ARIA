"use strict";
// Navegación entre vistas (Chat, Centro de control, Ajustes) con #hash.
(() => {
  const VISTAS = ["inicio", "chat", "control", "ajustes"];
  function mostrar() {
    let v = location.hash.replace("#", "");
    if (!VISTAS.includes(v) || (v === "control" && !Sesion.esAdmin)) v = "inicio";
    for (const n of VISTAS) $("v-" + n).hidden = n !== v;
    document.querySelectorAll(".nav-btn[data-vista]").forEach((b) => b.classList.toggle("activo", b.dataset.vista === v));
    Control.activar(v === "control");
    Inicio.activar(v === "inicio");
    if (v === "ajustes") { Ajustes.activar(); Usuarios.activar(); Memoria.activar(); }
    document.title = "ARIA · " + { inicio: "Inicio", chat: "Chat", control: "Centro de control", ajustes: "Ajustes" }[v];
  }
  document.querySelectorAll(".nav-btn[data-vista]").forEach((b) => b.addEventListener("click", () => { location.hash = b.dataset.vista; }));
  window.addEventListener("hashchange", mostrar);
  (async () => {
    await cargarSesion();
    ManosLibres.iniciarUI(); Chat.iniciar(); Control.iniciar(); Inicio.iniciar(); Ajustes.iniciar(); Usuarios.iniciar(); Memoria.iniciar();
    Chat.refrescarCerebro();
    if (new URLSearchParams(location.search).get("spotify")) history.replaceState(null, "", "/#ajustes");
    mostrar();
  })();
})();
