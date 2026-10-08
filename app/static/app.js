"use strict";
// Navegación entre vistas (Chat, Centro de control, Ajustes) con #hash.
(() => {
  const VISTAS = ["inicio", "chat", "finanzas", "red", "seguridad", "control", "ajustes"];
  const SOLO_ADMIN = ["control", "red", "seguridad"];
  function mostrar() {
    let v = location.hash.replace("#", "");
    if (!VISTAS.includes(v) || (SOLO_ADMIN.includes(v) && !Sesion.esAdmin)) v = "inicio";
    for (const n of VISTAS) $("v-" + n).hidden = n !== v;
    document.querySelectorAll(".nav-btn[data-vista]").forEach((b) => b.classList.toggle("activo", b.dataset.vista === v));
    Control.activar(v === "control");
    Inicio.activar(v === "inicio");
    Finanzas.activar(v === "finanzas");
    Red.activar(v === "red");
    Seguridad.activar(v === "seguridad");
    if (v === "ajustes") { Ajustes.activar(); Usuarios.activar(); Memoria.activar(); Avisos.activar(); }
    document.title = "ARIA · " + { inicio: "Inicio", chat: "Chat", finanzas: "Finanzas", red: "Red", seguridad: "Seguridad", control: "Centro de control", ajustes: "Ajustes" }[v];
  }
  document.querySelectorAll(".nav-btn[data-vista]").forEach((b) => b.addEventListener("click", () => { location.hash = b.dataset.vista; }));
  window.addEventListener("hashchange", mostrar);
  (async () => {
    await cargarSesion();
    ManosLibres.iniciarUI(); Chat.iniciar(); Control.iniciar(); Finanzas.iniciar(); Red.iniciar(); Seguridad.iniciar(); Inicio.iniciar(); Ajustes.iniciar(); Usuarios.iniciar(); Memoria.iniciar(); Avisos.iniciar();
    Chat.refrescarCerebro();
    if (new URLSearchParams(location.search).get("spotify")) history.replaceState(null, "", "/#ajustes");
    mostrar();
  })();
})();
