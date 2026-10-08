"use strict";
// Vista cartográfica. La geolocalización solo se solicita tras pulsar el botón.
const Mapa = (() => {
  let mapa = null, ruta = null, marcador = null, iniciado = false;
  const estado = (s, error = false) => { $("mapa-estado").textContent = s; $("mapa-estado").className = "mapa-estado " + (error ? "error" : "muted"); };
  const centrar = (lat, lon, zoom = 15) => { mapa.setView([lat, lon], zoom); if (marcador) marcador.remove(); marcador = L.marker([lat, lon]).addTo(mapa); };
  function pintarResultados(resultados) {
    const caja = $("mapa-resultados"); caja.replaceChildren();
    for (const r of resultados || []) {
      const b = el("button", { type: "button", class: "mapa-resultado" }, r.nombre || "Lugar");
      b.addEventListener("click", () => centrar(r.lat, r.lon)); caja.append(b);
    }
  }
  async function buscar(e) {
    e.preventDefault(); const q = $("mapa-consulta").value.trim(); if (!q) return;
    estado("Buscando…"); const r = await api("/api/mapa/buscar?q=" + encodeURIComponent(q));
    if (!r.ok) return estado(r.data.error || "No se pudo buscar.", true);
    pintarResultados(r.data.resultados); const p = r.data.resultados[0];
    if (p) { centrar(p.lat, p.lon); estado(p.nombre); } else estado("No se han encontrado lugares.");
  }
  function miUbicacion() {
    if (!navigator.geolocation) return estado("Este navegador no ofrece geolocalización.", true);
    estado("Solicitando ubicación…"); navigator.geolocation.getCurrentPosition((p) => {
      centrar(p.coords.latitude, p.coords.longitude); estado("Ubicación actual (solo en este dispositivo).");
    }, () => estado("No se ha podido obtener tu ubicación.", true), { enableHighAccuracy: false, timeout: 10000 });
  }
  function rutaForm() {
    if ($("mapa-ruta-form")) return;
    const f = el("form", { id: "mapa-ruta-form", class: "mapa-form" },
      el("input", { id: "mapa-desde", placeholder: "Desde…", maxLength: 200, required: true }),
      el("input", { id: "mapa-hasta", placeholder: "Hasta…", maxLength: 200, required: true }),
      el("select", { id: "mapa-modo", ariaLabel: "Modo de transporte" }, el("option", { value: "driving" }, "Coche"), el("option", { value: "foot" }, "A pie"), el("option", { value: "bike" }, "Bici")),
      el("button", { type: "submit", class: "primario" }, "Calcular"));
    f.addEventListener("submit", async (e) => { e.preventDefault(); estado("Calculando ruta…");
      const q = new URLSearchParams({ desde: $("mapa-desde").value, hasta: $("mapa-hasta").value, modo: $("mapa-modo").value });
      const r = await api("/api/mapa/ruta?" + q); if (!r.ok) return estado(r.data.error || "No se pudo calcular la ruta.", true);
      if (ruta) ruta.remove(); ruta = L.geoJSON(r.data.geometria, { style: { color: "#38d6ff", weight: 6 } }).addTo(mapa); mapa.fitBounds(ruta.getBounds(), { padding: [20, 20] });
      estado(`${(r.data.distancia / 1000).toFixed(1)} km, unos ${Math.round(r.data.duracion / 60)} min.`);
    });
    $("mapa-buscar").after(f);
  }
  async function cerca() {
    if (!mapa) return; const c = mapa.getCenter(); estado("Buscando sitios cercanos…");
    const q = new URLSearchParams({ lugar: `${c.lat},${c.lng}`, tipo: $("mapa-tipo").value }); const r = await api("/api/mapa/cerca?" + q);
    if (!r.ok) return estado(r.data.error || "No se pudo buscar.", true);
    pintarResultados((r.data.resultados || []).map((x) => ({ ...x, nombre: `${x.nombre} (${x.metros >= 1000 ? (x.metros / 1000).toFixed(1) + " km" : x.metros + " m"})` })));
    estado(`${r.data.resultados.length} resultados cerca del centro del mapa.`);
  }
  function iniciar() {
    if (iniciado) return; iniciado = true;
    mapa = L.map("mapa", { zoomControl: true }).setView([40.4168, -3.7038], 6);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap" }).addTo(mapa);
    $("mapa-buscar").addEventListener("submit", buscar); $("mapa-ubicacion").addEventListener("click", miUbicacion);
    $("mapa-ruta-btn").addEventListener("click", rutaForm); $("mapa-tipo").addEventListener("change", cerca);
  }
  function activar(activa) {
    if (!activa || !mapa) return;
    setTimeout(() => mapa.invalidateSize(), 0);
    const p = new URLSearchParams(location.hash.split("?")[1] || ""), lugar = p.get("lugar");
    if (lugar) { $("mapa-consulta").value = lugar; buscar({ preventDefault() {} }); }
    if (p.get("desde") && p.get("hasta")) {
      rutaForm(); $("mapa-desde").value = p.get("desde"); $("mapa-hasta").value = p.get("hasta");
      $("mapa-ruta-form").requestSubmit();
    }
  }
  return { iniciar, activar };
})();
