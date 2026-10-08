"use strict";
// Service worker de ARIA: SOLO notificaciones push y su clic. No guarda nada en caché (las páginas
// autenticadas nunca se sirven sin conexión). Versión: __VERSION__
const VERSION = "__VERSION__";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

// Solo rutas relativas del propio ARIA (nunca una URL externa que venga en el mensaje).
function rutaSegura(u) {
  return typeof u === "string" && u.startsWith("/") && !u.startsWith("//") ? u : "/";
}

self.addEventListener("push", (e) => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (_) { d = { cuerpo: e.data ? e.data.text() : "" }; }
  const titulo = String(d.titulo || "ARIA").slice(0, 80);
  e.waitUntil(self.registration.showNotification(titulo, {
    body: String(d.cuerpo || "").slice(0, 400),
    tag: String(d.etiqueta || "aria").slice(0, 40),
    icon: "/static/icon.svg",
    badge: "/static/icon.svg",
    lang: "es-ES",
    data: { url: rutaSegura(d.url), version: VERSION },
  }));
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const destino = new URL(rutaSegura(e.notification.data && e.notification.data.url), self.location.origin).href;
  e.waitUntil((async () => {
    const ventanas = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const v of ventanas) {
      if (new URL(v.url).origin === self.location.origin && "focus" in v) {
        await v.focus();
        if ("navigate" in v) { try { await v.navigate(destino); } catch (_) { /* sin control: se queda enfocada */ } }
        return;
      }
    }
    await self.clients.openWindow(destino);
  })());
});
