"use strict";
// Navegación entre vistas (Chat, Centro de control, Ajustes) con #hash.
(() => {
  const VISTAS = ["inicio", "chat", "finanzas", "informacion", "red", "seguridad", "control", "ajustes", "agenda", "mapa", "hud"];
  const SOLO_ADMIN = ["control", "red", "seguridad"];
  function mostrar() {
    let v = location.hash.replace("#", "");
    if (!VISTAS.includes(v) || (SOLO_ADMIN.includes(v) && !Sesion.esAdmin) || (v !== "ajustes" && !puede(v))) v = "inicio";
    for (const n of VISTAS) $("v-" + n).hidden = n !== v;
    document.body.classList.toggle("modo-hud", v === "hud");
    document.querySelectorAll(".nav-btn[data-vista]").forEach((b) => b.classList.toggle("activo", b.dataset.vista === v));
    document.querySelector(".nav-btn.activo")?.scrollIntoView({ block: "nearest", inline: "nearest" });   // barra inferior en móvil
    Control.activar(v === "control");
    Inicio.activar(v === "inicio");
    Finanzas.activar(v === "finanzas");
    Informacion.activar(v === "informacion");
    Agenda.activar(v === "agenda");
    Red.activar(v === "red");
    Seguridad.activar(v === "seguridad");
    Mapa.activar(v === "mapa");
    Hud.activar(v === "hud");
    if (v === "ajustes") { Ajustes.activar(); Usuarios.activar(); Memoria.activar(); Avisos.activar(); Rutinas.activar(); if (Sesion.esAdmin) { Modulos.pintarAjustes(); Automatizaciones.activar(); Accesos.activar(); } }
    document.title = "ARIA · " + { inicio: "Inicio", chat: "Chat", finanzas: "Finanzas", informacion: "Información", agenda: "Agenda", red: "Red", seguridad: "Seguridad", control: "Centro de control", ajustes: "Ajustes", mapa: "Mapa", hud: "HUD" }[v];
  }
  document.querySelectorAll(".nav-btn[data-vista]").forEach((b) => b.addEventListener("click", () => { location.hash = b.dataset.vista; }));
  window.addEventListener("hashchange", mostrar);
  (async () => {
    await cargarSesion();
    ManosLibres.iniciarUI(); Chat.iniciar(); Control.iniciar(); Finanzas.iniciar(); Informacion.iniciar(); Agenda.iniciar(); Red.iniciar(); Seguridad.iniciar(); Inicio.iniciar(); Ajustes.iniciar(); Usuarios.iniciar(); Memoria.iniciar(); Avisos.iniciar(); Rutinas.iniciar(); Paleta.iniciar(); Mapa.iniciar(); Hud.iniciar();
    Chat.refrescarCerebro();
    if (new URLSearchParams(location.search).get("spotify")) history.replaceState(null, "", "/#ajustes");
    Compartir.revisar(); // «Compartir con ARIA» desde otra app del móvil (Web Share Target)
    // Invitados: fuera de la barra lo que su acceso no incluye
    document.querySelectorAll(".nav-btn[data-vista]").forEach((b) => { if (b.dataset.vista !== "ajustes" && !puede(b.dataset.vista)) b.hidden = true; });
    mostrar();
  })();
})();
