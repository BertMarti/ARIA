"use strict";
const Ubicacion = (() => {
  const CLAVE = "aria_ubicacion_activa";
  let temporizador;
  // Activada por defecto: el navegador pide permiso la primera vez; si se rechaza, se apaga y se usa la de casa.
  const leer = () => { try { return localStorage.getItem(CLAVE) !== "0"; } catch (_) { return true; } };
  const guardar = (v) => { try { localStorage.setItem(CLAVE, v ? "1" : "0"); } catch (_) {} };
  function pintar(d) { const x = $("ubicacion-estado"); if (x) x.textContent = d ? (d.origen === "dispositivo" ? "📍 " : "🏠 ") + (d.nombre || "Ubicación") : "🏠 Casa"; }
  async function pedir() {
    if (!leer() || !navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(async (p) => {
      const r = await api("/api/ubicacion", { method: "POST", json: { lat: p.coords.latitude, lon: p.coords.longitude } });
      if (r.ok) { pintar(r.data); window.dispatchEvent(new Event("aria:ubicacion")); }
    }, (e) => { if (e.code === 1) { guardar(false); const c = $("ubicacion-activar"); if (c) c.checked = false; toast("No has permitido la ubicación; se ha desactivado.", "mal"); } }, { enableHighAccuracy: false, maximumAge: 600000, timeout: 15000 });
  }
  function iniciar() {
    const c = $("ubicacion-activar"); if (!c) return;
    c.checked = leer(); c.addEventListener("change", () => { guardar(c.checked); if (c.checked) pedir(); });
    $("ubicacion-olvidar").addEventListener("click", async () => { const r = await api("/api/ubicacion", { method: "DELETE" }); if (r.ok) { pintar(r.data.ubicacion); window.dispatchEvent(new Event("aria:ubicacion")); toast("Ubicación olvidada."); } });
    api("/api/ubicacion").then((r) => { if (r.ok) pintar(r.data); }); pedir();
    temporizador = setInterval(() => { if (!document.hidden) pedir(); }, 900000);
    document.addEventListener("visibilitychange", () => { if (!document.hidden) pedir(); });
  }
  iniciar();
  return { iniciar };
})();
