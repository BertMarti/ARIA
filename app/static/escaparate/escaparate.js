"use strict";
// Escaparate público de ARIA: todo es local y pregrabado (sin llamadas a la API ni IA en vivo).
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const reducido = matchMedia("(prefers-reduced-motion: reduce)");
  const rgba = (c, o) => `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${o})`;
  const CIAN = [56, 214, 255], VIOLETA = [124, 140, 255];

  const BIENVENIDA = [
    "Hola, bienvenido. Soy ARIA.",
    "Vivo en un ordenador del tamaño de una galleta y cuido de una casa entera.",
    "Hablo, escucho, recuerdo lo que importa… y no hago nada sin tu permiso.",
    "Ah, y esa lucecita nerviosa es Ping. No le hagas mucho caso.",
    "Ponte cómodo: te enseño lo que ya sé hacer.",
  ];
  const RESPUESTAS = [
    "Una asistente que vive en tu casa, no en la nube de nadie. Hablo contigo, cuido de la red y te llevo el día. Lo justo para que no tengas que pensar en ello.",
    "Solo espero a oír «Aria», y eso lo hago en tu propia máquina. Lo que dices después se transcribe y se olvida: el audio no se guarda nunca.",
    "Vigila la red, atrapa anuncios y presume de ello. Mucho. Yo pongo la calma; él, el entusiasmo.",
    "Nada. Soy de código abierto: me instalas en una Raspberry Pi o en un PC con Linux y soy tuya.",
  ];
  const FRASES_PING = [
    ["ok", "¡Eh, mira! 1.284 anuncios atrapados hoy."],
    ["ok", "Récord de la semana. De nada."],
    ["aviso", "Hay un móvil nuevo en la red… Ah, no, es el tuyo."],
    ["ok", "VPN: dos conectados. Todo en orden, jefa."],
    ["pensando", "Sí, soy pequeño. Pero muy rápido."],
  ];

  // --- Cielo de estrellas con parallax suave -------------------------------------------------------
  const cielo = $("#cielo"), cc = cielo.getContext("2d"), estrellas = [];
  let raton = { x: .5, y: .5 };
  function tamCielo() {
    const d = Math.min(2, devicePixelRatio || 1);
    cielo.width = innerWidth * d; cielo.height = innerHeight * d; cc.setTransform(d, 0, 0, d, 0, 0);
    estrellas.length = 0;
    const n = Math.min(220, Math.floor(innerWidth * innerHeight / 6000));
    for (let i = 0; i < n; i++) estrellas.push({ x: Math.random(), y: Math.random(), z: .2 + Math.random() * .8, f: Math.random() * 6 });
  }
  function dibujarCielo(ahora) {
    const t = reducido.matches ? 0 : ahora / 1000, W = innerWidth, H = innerHeight;
    cc.clearRect(0, 0, W, H);
    for (const s of estrellas) {
      cc.fillStyle = `rgba(220,235,255,${(.18 + .5 * s.z * (.6 + .4 * Math.sin(t * 1.2 + s.f))).toFixed(2)})`;
      const x = ((s.x * W - (raton.x - .5) * 30 * s.z) % W + W) % W, y = s.y * H - (raton.y - .5) * 20 * s.z;
      cc.fillRect(x, y, s.z * 1.6, s.z * 1.6);
    }
    if (!reducido.matches) requestAnimationFrame(dibujarCielo);
  }
  addEventListener("pointermove", (e) => { raton = { x: e.clientX / innerWidth, y: e.clientY / innerHeight }; });
  addEventListener("resize", tamCielo);
  tamCielo(); requestAnimationFrame(dibujarCielo);

  // --- Orbe de ARIA (versión ligera del HUD) ---------------------------------------------------------
  class Orbe {
    constructor(lienzo) {
      this.l = lienzo; this.c = lienzo.getContext("2d"); this.nivel = 0; this.suave = 0; this.col = [...CIAN]; this.obj = CIAN; this.t0 = performance.now();
      this.part = Array.from({ length: 70 }, () => ({ a: Math.random() * 7, r: 1.05 + Math.random() * .75, s: .6 + Math.random() * 1.6, o: .25 + Math.random() * .6, v: (.4 + Math.random()) * (Math.random() < .5 ? -1 : 1), vio: Math.random() < .35 }));
      this.raf = 0; this.visible = true; this._d = this._d.bind(this);
      if ("IntersectionObserver" in window) new IntersectionObserver(([e]) => { this.visible = e.isIntersecting; if (this.visible) this.iniciar(); }).observe(lienzo);
      document.addEventListener("visibilitychange", () => { if (!document.hidden) this.iniciar(); });
      this.iniciar();
    }
    iniciar() { if (!this.raf) this.raf = requestAnimationFrame(this._d); }
    _d(ahora) {
      this.raf = 0;
      if (!this.visible || document.hidden) return;
      const c = this.c, r = this.l.getBoundingClientRect(), dpr = Math.min(2, devicePixelRatio || 1);
      if (!r.width) return;
      if (this.l.width !== Math.round(r.width * dpr)) { this.l.width = Math.round(r.width * dpr); this.l.height = Math.round(r.height * dpr); }
      c.setTransform(dpr, 0, 0, dpr, 0, 0);
      const w = r.width, h = r.height, x = w / 2, y = h / 2, R = Math.min(w, h) * .27, halo = Math.min(w, h) / 2;
      const t = reducido.matches ? 0 : (ahora - this.t0) / 1000;
      this.col = this.col.map((v, i) => v + (this.obj[i] - v) * .06);
      this.suave += (this.nivel - this.suave) * .25;
      const rr = R * (1 + Math.sin(t * 1.1) * .03 + this.suave * .16), vel = .6 + this.suave * 1.5;
      c.clearRect(0, 0, w, h);
      let g = c.createRadialGradient(x, y, rr * .2, x, y, halo);
      g.addColorStop(0, rgba(this.col, .32 + this.suave * .3)); g.addColorStop(.5, rgba(this.col, .07)); g.addColorStop(1, rgba(this.col, 0));
      c.fillStyle = g; c.beginPath(); c.arc(x, y, halo, 0, 7); c.fill();
      g = c.createRadialGradient(x - rr * .25, y - rr * .3, rr * .05, x, y, rr);
      g.addColorStop(0, "rgba(255,255,255,.92)"); g.addColorStop(.25, rgba(this.col, .85)); g.addColorStop(.75, rgba(this.col.map((v) => v * .35), .9)); g.addColorStop(1, rgba(this.col.map((v) => v * .15), .2));
      c.fillStyle = g; c.beginPath(); c.arc(x, y, rr * .78, 0, 7); c.fill();
      c.save(); c.beginPath(); c.arc(x, y, rr * .78, 0, 7); c.clip(); c.globalCompositeOperation = "lighter"; c.lineWidth = 1.2;
      for (let i = 0; i < 6; i++) { c.strokeStyle = i % 2 ? "rgba(255,255,255,.16)" : rgba(this.col, .16); c.beginPath(); c.ellipse(x, y, rr * (.75 - i * .06), rr * (.22 + i * .05), t * vel * (.3 + i * .08) + i, 0, 7); c.stroke(); }
      c.restore(); c.globalCompositeOperation = "lighter";
      for (const [k, s, d, lw, o] of [[1, 1, [rr * .5, rr * .18], 1.6, .8], [1.18, -1.3, [rr * .08, rr * .12], 1, .55], [1.36, .7, [rr * 1.2, rr * .4], 1, .35]]) {
        c.save(); c.translate(x, y); c.rotate(t * vel * .35 * s); c.setLineDash(d); c.strokeStyle = rgba(this.col, o); c.lineWidth = lw; c.beginPath(); c.arc(0, 0, rr * k, 0, 7); c.stroke(); c.restore();
      }
      if (this.suave > .02) {
        c.strokeStyle = rgba(this.col, .9); c.lineWidth = 2; c.beginPath();
        for (let i = 0; i <= 120; i++) { const a = i / 120 * 6.283, q = rr * .86 + Math.sin(a * 6 + t * 7) * this.suave * rr * .12 + Math.sin(a * 11 - t * 5) * this.suave * rr * .06; i ? c.lineTo(x + Math.cos(a) * q, y + Math.sin(a) * q) : c.moveTo(x + Math.cos(a) * q, y + Math.sin(a) * q); }
        c.closePath(); c.stroke();
      }
      for (const p of this.part) {
        if (!reducido.matches) p.a += p.v * vel * .006;
        const d = Math.min(rr * p.r, halo * .97);
        c.fillStyle = rgba(p.vio ? VIOLETA : this.col, p.o); c.beginPath(); c.arc(x + Math.cos(p.a) * d, y + Math.sin(p.a) * d * .92, p.s, 0, 7); c.fill();
      }
      c.globalCompositeOperation = "source-over";
      if (!reducido.matches) this.raf = requestAnimationFrame(this._d);
    }
  }

  const orbe = new Orbe($("#orbe"));
  $$(".mini-orbe").forEach((l) => new Orbe(l));
  $$(".mini-ping").forEach((l) => new Ping(l, { escala: .9 }));

  // --- «Quiero escuchar a ARIA»: voz pregrabada + subtítulos ------------------------------------------
  const boton = $("#escuchar"), sub = $("#subtitulo");
  let audio = null, analizador = null, datos = null, temporizadores = [], activo = false;
  function nivel() {
    if (!activo) { orbe.nivel = 0; return; }
    if (analizador) {
      analizador.getByteTimeDomainData(datos);
      let q = 0; for (const v of datos) q += (v - 128) ** 2;
      orbe.nivel = Math.min(1, Math.sqrt(q / datos.length) / 30);
    } else orbe.nivel = .35 + .25 * Math.sin(performance.now() / 120);
    requestAnimationFrame(nivel);
  }
  function subtitulos(duracion) {
    const total = BIENVENIDA.reduce((n, f) => n + f.length, 0);
    let t = 0;
    BIENVENIDA.forEach((f) => {
      temporizadores.push(setTimeout(() => { sub.textContent = f; sub.classList.add("visible"); }, t * 1000));
      t += duracion * f.length / total;
    });
    temporizadores.push(setTimeout(parar, t * 1000 + 1500));
  }
  function parar() {
    activo = false; temporizadores.forEach(clearTimeout); temporizadores = [];
    if (audio) { audio.pause(); audio.currentTime = 0; }
    sub.classList.remove("visible"); boton.setAttribute("aria-checked", "false"); document.body.classList.remove("escuchando");
  }
  async function empezar() {
    activo = true; boton.setAttribute("aria-checked", "true"); document.body.classList.add("escuchando");
    try {
      if (!audio) {
        audio = new Audio("/static/escaparate/audio/bienvenida.mp3");
        await new Promise((ok, ko) => { audio.addEventListener("loadedmetadata", ok, { once: true }); audio.addEventListener("error", ko, { once: true }); });
        try {
          const ctx = new (window.AudioContext || window.webkitAudioContext)();
          const fuente = ctx.createMediaElementSource(audio);
          analizador = ctx.createAnalyser(); analizador.fftSize = 256; datos = new Uint8Array(analizador.fftSize);
          fuente.connect(analizador); analizador.connect(ctx.destination);
        } catch (_) { analizador = null; }
      }
      await audio.play();
      subtitulos(audio.duration || 20);
    } catch (_) {
      audio = null; $("#aviso-voz").hidden = false;   // sin grabación todavía: solo subtítulos
      subtitulos(18);
    }
    nivel();
  }
  boton.addEventListener("click", () => (activo ? parar() : empezar()));

  // --- Demos en diálogos ---------------------------------------------------------------------------------
  const creados = new Set();
  let pingDemo = null, rotacion = 0;
  function abrir(id) {
    const d = document.getElementById(id);
    d.showModal();
    if (!creados.has(id)) {
      creados.add(id);
      d.querySelectorAll(".demo-orbe").forEach((l) => new Orbe(l));
      d.querySelectorAll(".demo-ping").forEach((l) => { pingDemo = new Ping(l, { sigue: true, escala: 1.4 }); });
    }
    if (id === "demo-casa") {
      let i = 0, n = 1284;
      const dice = $("#ping-dice"), cont = $("#contador");
      clearInterval(rotacion);
      rotacion = setInterval(() => {
        if (!d.open) { clearInterval(rotacion); return; }
        i = (i + 1) % FRASES_PING.length; n += 1 + Math.floor(Math.random() * 3);
        const [estado, frase] = FRASES_PING[i];
        pingDemo?.estado(estado); dice.textContent = frase.replace("1.284", n.toLocaleString("es-ES", { useGrouping: "always" }));
        cont.textContent = n.toLocaleString("es-ES", { useGrouping: "always" });
      }, 3200);
    }
  }
  $$("[data-demo]").forEach((b) => b.addEventListener("click", () => abrir(b.dataset.demo)));
  $$("dialog.demo").forEach((d) => {
    d.querySelector(".cerrar").addEventListener("click", () => d.close());
    d.addEventListener("click", (e) => { if (e.target === d) d.close(); });   // clic fuera del contenido
  });

  // --- Pregúntale algo (respuestas fijas) ---------------------------------------------------------------
  const resp = $("#respuesta");
  let escribir = 0;
  $$(".preguntas button").forEach((b) => b.addEventListener("click", () => {
    $$(".preguntas button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    const texto = RESPUESTAS[Number(b.dataset.r)];
    clearInterval(escribir);
    if (reducido.matches) { resp.textContent = texto; return; }
    let n = 0; resp.textContent = ""; resp.setAttribute("aria-busy", "true");   // el lector de pantalla lee la frase entera al final
    escribir = setInterval(() => { n += 2; resp.textContent = texto.slice(0, n); if (n >= texto.length) { clearInterval(escribir); resp.setAttribute("aria-busy", "false"); } }, 18);
  }));
})();
