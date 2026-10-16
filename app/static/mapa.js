"use strict";
// Vista cartográfica. La geolocalización solo se solicita tras pulsar el botón.
const Mapa = (() => {
  let mapa = null, ruta = null, marcador = null, iniciado = false;
  let modo = "2d", geometriaRuta = null, punto = null, maplibreCargando = null;
  const estado = (s, error = false) => { $("mapa-estado").textContent = s; $("mapa-estado").className = "mapa-estado " + (error ? "error" : "muted"); };
  const reducido = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
  const centroZoom = () => modo === "3d" ? { center: [mapa.getCenter().lng, mapa.getCenter().lat], zoom: mapa.getZoom() } : { center: [mapa.getCenter().lng, mapa.getCenter().lat], zoom: mapa.getZoom() };
  function actualizarModo() {
    $("mapa-2d").setAttribute("aria-pressed", String(modo === "2d"));
    $("mapa-3d").setAttribute("aria-pressed", String(modo === "3d"));
    $("mapa-cenital").hidden = modo !== "3d";
  }
  function ponerMarcador(lat, lon) {
    punto = [Number(lon), Number(lat)];
    if (modo === "3d") {
      if (marcador) marcador.remove();
      marcador = new maplibregl.Marker({ color: "#38d6ff" }).setLngLat(punto).addTo(mapa);
    } else {
      if (marcador) marcador.remove();
      marcador = L.marker([lat, lon]).addTo(mapa);
    }
  }
  function centrar(lat, lon, zoom = 15) {
    ponerMarcador(lat, lon);
    if (modo === "3d") {
      const opciones = { center: [Number(lon), Number(lat)], zoom: 16, pitch: 60, bearing: -20, duration: 2500 };
      if (reducido()) mapa.jumpTo(opciones); else mapa.flyTo(opciones);
    } else mapa.setView([lat, lon], zoom);
  }
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
      geometriaRuta = r.data.geometria; dibujarRuta();
      estado(`${(r.data.distancia / 1000).toFixed(1)} km, unos ${Math.round(r.data.duracion / 60)} min.`);
    });
    $("mapa-buscar").after(f);
  }
  function dibujarRuta() {
    if (!geometriaRuta || !mapa) return;
    if (modo === "3d") {
      if (mapa.getSource("ruta")) mapa.getSource("ruta").setData(geometriaRuta);
      else { mapa.addSource("ruta", { type: "geojson", data: geometriaRuta }); mapa.addLayer({ id: "ruta", type: "line", source: "ruta", paint: { "line-color": "#38d6ff", "line-width": 5 } }); }
      const coords = geometriaRuta.coordinates || geometriaRuta.geometry?.coordinates || [];
      const b = new maplibregl.LngLatBounds(); (Array.isArray(coords[0]?.[0]) ? coords.flat() : coords).forEach((c) => b.extend(c));
      if (!b.isEmpty()) mapa.fitBounds(b, { padding: 30, pitch: 60 });
    } else { if (ruta) ruta.remove(); ruta = L.geoJSON(geometriaRuta, { style: { color: "#38d6ff", weight: 6 } }).addTo(mapa); mapa.fitBounds(ruta.getBounds(), { padding: [20, 20] }); }
  }
  async function cerca() {
    if (!mapa) return; const c = mapa.getCenter(); estado("Buscando sitios cercanos…");
    const q = new URLSearchParams({ lugar: `${c.lat},${c.lng}`, tipo: $("mapa-tipo").value }); const r = await api("/api/mapa/cerca?" + q);
    if (!r.ok) return estado(r.data.error || "No se pudo buscar.", true);
    pintarResultados((r.data.resultados || []).map((x) => ({ ...x, nombre: `${x.nombre} (${x.metros >= 1000 ? (x.metros / 1000).toFixed(1) + " km" : x.metros + " m"})` })));
    estado(`${r.data.resultados.length} resultados cerca del centro del mapa.`);
  }
  function ajustarEstilo() {
    for (const capa of mapa.getStyle().layers || []) {
      try {
        if (capa.type === "background") mapa.setPaintProperty(capa.id, "background-color", "#070b12");
        if (capa.type === "fill" && /water/i.test(capa.id)) mapa.setPaintProperty(capa.id, "fill-color", "#0d263b");
        if (capa.type === "line" && /(road|street|highway)/i.test(capa.id)) mapa.setPaintProperty(capa.id, "line-color", "#334b66");
      } catch (_) { /* algunas capas del estilo no admiten estos cambios */ }
    }
    const edificio = mapa.getStyle().layers?.find((x) => x.type === "fill-extrusion");
    if (!edificio && mapa.getSource("openmaptiles")) mapa.addLayer({ id: "aria-edificios", type: "fill-extrusion", source: "openmaptiles", "source-layer": "building", minzoom: 15, paint: { "fill-extrusion-color": "#263d57", "fill-extrusion-height": ["coalesce", ["get", "render_height"], 10], "fill-extrusion-base": ["coalesce", ["get", "render_min_height"], 0], "fill-extrusion-opacity": .82 } });
  }
  function cargarMaplibre() {
    if (maplibreCargando) return maplibreCargando;
    maplibreCargando = new Promise((resolve, reject) => {
      if (!document.querySelector('link[href="/static/vendor/maplibre/maplibre-gl.css"]')) { const css = document.createElement("link"); css.rel = "stylesheet"; css.href = "/static/vendor/maplibre/maplibre-gl.css"; document.head.append(css); }
      const s = document.createElement("script"); s.src = "/static/vendor/maplibre/maplibre-gl-csp.js"; s.onload = resolve; s.onerror = reject; document.head.append(s);
    });
    return maplibreCargando;
  }
  function crearLeaflet(actual) {
    const m = L.map("mapa", { zoomControl: true }).setView([actual.center[1], actual.center[0]], actual.zoom);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap" }).addTo(m);
    return m;
  }
  async function cambiarModo(nuevo) {
    if (nuevo === modo) return;
    const actual = centroZoom();
    if (nuevo === "3d") {
      try { await cargarMaplibre(); const lienzo = document.createElement("canvas"); if (!window.maplibregl || !(lienzo.getContext("webgl2") || lienzo.getContext("webgl"))) throw new Error("WebGL");   // MapLibre 4 ya no trae supported() maplibregl.setWorkerUrl("/static/vendor/maplibre/maplibre-gl-csp-worker.js");
        if (marcador) marcador.remove(); if (ruta) ruta.remove(); mapa.remove();
        modo = "3d"; mapa = new maplibregl.Map({ container: "mapa", style: "https://tiles.openfreemap.org/styles/liberty", center: actual.center, zoom: actual.zoom, pitch: 60, bearing: -20, attributionControl: false });
        mapa.addControl(new maplibregl.NavigationControl({ showCompass: true }), "top-right"); mapa.addControl(new maplibregl.AttributionControl({ customAttribution: "© OpenFreeMap © OpenMapTiles © colaboradores de OpenStreetMap" }));
        mapa.once("style.load", () => { ajustarEstilo(); dibujarRuta(); if (punto) ponerMarcador(punto[1], punto[0]); });   // en cuanto llega el estilo: sin destello claro
        mapa.once("error", () => { if (modo === "3d") { toast("Tu navegador no puede mostrar el mapa 3D", "mal"); mapa.remove(); modo = "2d"; mapa = crearLeaflet(actual); dibujarRuta(); if (punto) ponerMarcador(punto[1], punto[0]); actualizarModo(); } });
      } catch (_) { toast("Tu navegador no puede mostrar el mapa 3D", "mal"); modo = "2d"; mapa = crearLeaflet(actual); dibujarRuta(); if (punto) ponerMarcador(punto[1], punto[0]); actualizarModo(); return; }
    } else {
      if (marcador) marcador.remove(); mapa.remove(); modo = "2d"; mapa = crearLeaflet(actual); dibujarRuta(); if (punto) ponerMarcador(punto[1], punto[0]);
    }
    Prefs.set("mapa_modo", modo); actualizarModo();
  }
  function iniciar() {
    if (iniciado) return; iniciado = true; modo = "2d";
    mapa = crearLeaflet({ center: [-3.7038, 40.4168], zoom: 6 });
    $("mapa-buscar").addEventListener("submit", buscar); $("mapa-ubicacion").addEventListener("click", miUbicacion); $("mapa-ruta-btn").addEventListener("click", rutaForm); $("mapa-tipo").addEventListener("change", cerca);
    $("mapa-2d").addEventListener("click", () => cambiarModo("2d")); $("mapa-3d").addEventListener("click", () => cambiarModo("3d")); $("mapa-cenital").addEventListener("click", () => mapa.easeTo({ pitch: 0, bearing: 0, duration: reducido() ? 0 : 600 })); actualizarModo();
    if (Prefs.get("mapa_modo", "2d") === "3d") cambiarModo("3d");
  }
  function activar(activa) {
    if (!activa || !mapa) return; setTimeout(() => modo === "3d" ? mapa.resize() : mapa.invalidateSize(), 0);
    const p = new URLSearchParams(location.hash.split("?")[1] || ""), lugar = p.get("lugar");
    if (lugar) { $("mapa-consulta").value = lugar; buscar({ preventDefault() {} }); }
    if (p.get("desde") && p.get("hasta")) { rutaForm(); $("mapa-desde").value = p.get("desde"); $("mapa-hasta").value = p.get("hasta"); $("mapa-ruta-form").requestSubmit(); }
  }
  return { iniciar, activar };
})();
