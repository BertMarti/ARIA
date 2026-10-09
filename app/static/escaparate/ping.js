"use strict";
// Ping: el hada de luz que vigila la red de casa. Componente de lienzo reutilizable (escaparate y HUD).
//   const p = new Ping(canvas, { sigue: true });  p.estado("aviso");  p.parar();
// Estados: ok (cian), aviso (ámbar), alerta (rosa), pensando (violeta). Respeta «reducir movimiento».
const Ping = (() => {
  const COLORES = { ok: [56, 214, 255], aviso: [251, 191, 36], alerta: [251, 113, 133], pensando: [124, 140, 255] };
  const reducido = matchMedia("(prefers-reduced-motion: reduce)");
  const rgba = (c, o) => `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${o})`;

  class Ping {
    constructor(lienzo, opciones = {}) {
      this.lienzo = lienzo; this.ctx = lienzo.getContext("2d");
      this.opc = { sigue: false, escala: 1, zona: { x: .5, y: .48, ax: .26, ay: .12 }, ...opciones };
      this.destino = null;   // {x, y} en px del lienzo: vuela allí y se queda revoloteando
      this.col = [...COLORES.ok]; this.obj = COLORES.ok;
      this.p = { x: 0, y: 0, vx: 0, vy: 0 }; this.raton = null; this.estela = []; this.raf = 0; this.t0 = performance.now();
      this._dibujar = this._dibujar.bind(this);
      if (this.opc.sigue) {
        lienzo.addEventListener("pointermove", (e) => { const r = lienzo.getBoundingClientRect(); this.raton = { x: e.clientX - r.left, y: e.clientY - r.top }; });
        lienzo.addEventListener("pointerleave", () => { this.raton = null; });
      }
      if (this.opc.global) {   // lienzo de fondo sin eventos propios (pointer-events: none): escucha a toda la ventana
        addEventListener("pointermove", (e) => {
          const r = lienzo.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top;
          this.raton = x >= 0 && y >= 0 && x <= r.width && y <= r.height ? { x, y } : null;
        }, { passive: true });
        document.documentElement.addEventListener("pointerleave", () => { this.raton = null; });
      }
      this.visible = true;
      if ("IntersectionObserver" in window) {
        new IntersectionObserver(([e]) => { this.visible = e.isIntersecting; if (this.visible) this.iniciar(); }).observe(lienzo);
      }
      document.addEventListener("visibilitychange", () => { if (!document.hidden) this.iniciar(); });
      this.iniciar();
    }
    estado(nombre) { this.obj = COLORES[nombre] || COLORES.ok; }
    posicion() { return { x: this.p.x, y: this.p.y }; }
    iniciar() { if (!this.raf) this.raf = requestAnimationFrame(this._dibujar); }
    parar() { cancelAnimationFrame(this.raf); this.raf = 0; }
    _tam() {
      const r = this.lienzo.getBoundingClientRect(), d = Math.min(2, devicePixelRatio || 1);
      if (this.lienzo.width !== Math.round(r.width * d) || this.lienzo.height !== Math.round(r.height * d)) {
        this.lienzo.width = Math.round(r.width * d); this.lienzo.height = Math.round(r.height * d);
      }
      this.ctx.setTransform(d, 0, 0, d, 0, 0);
      if (!this.p.x) { this.p.x = r.width / 2; this.p.y = r.height / 2; }
      return r;
    }
    _ala(lado, arriba, bat) {
      const c = this.ctx, s = arriba ? 1 : .68, L = 40 * s * bat, A = 16 * s;
      c.save(); c.translate(0, arriba ? -2 : 4); c.scale(lado, 1); c.rotate(arriba ? -.42 : .32);
      c.beginPath(); c.moveTo(6, 0); c.lineTo(6 + L, -A * .9); c.lineTo(6 + L * .86, A * .15); c.lineTo(8, A * .42); c.closePath();
      c.fillStyle = rgba(this.col, .13); c.fill(); c.strokeStyle = rgba(this.col, .85); c.lineWidth = 1; c.stroke();
      c.beginPath(); c.moveTo(10, 2); c.lineTo(6 + L * .55, -A * .42); c.lineTo(6 + L * .78, -A * .5);
      c.strokeStyle = "rgba(255,255,255,.45)"; c.lineWidth = .7; c.stroke();
      c.fillStyle = rgba(this.col, .9); c.fillRect(6 + L * .78 - 1.2, -A * .5 - 1.2, 2.4, 2.4);
      c.restore();
    }
    _dibujar(ahora) {
      this.raf = 0;
      if (!this.visible || document.hidden) return;
      const c = this.ctx, r = this._tam(), W = r.width, H = r.height, quieto = reducido.matches;
      const t = quieto ? 0 : (ahora - this.t0) / 1000, k = this.opc.escala;
      this.col = this.col.map((v, i) => v + (this.obj[i] - v) * .08);
      c.clearRect(0, 0, W, H);
      // Vuelo: sigue al ratón con inercia o pasea solo
      const p = this.p;
      const z = this.opc.zona, d = this.destino;
      const tx = d ? d.x + Math.sin(t * 1.3) * 14 : this.raton ? this.raton.x + 30 : W * z.x + Math.sin(t * .5) * W * z.ax;
      const ty = d ? d.y + Math.sin(t * 1.7) * 8 : this.raton ? this.raton.y - 26 : H * z.y + Math.sin(t * .9) * H * z.ay;
      p.vx += (tx - p.x) * .018; p.vy += (ty - p.y) * .018; p.vx *= .86; p.vy *= .86; p.x += p.vx; p.y += p.vy;
      const y = p.y + (quieto ? 0 : Math.sin(t * 3.2) * 3);
      if (!quieto) { this.estela.push({ x: p.x + (Math.random() * 10 - 5), y: y + 12 * k, v: 1 }); if (this.estela.length > 50) this.estela.shift(); }
      for (const e of this.estela) { e.v -= .02; e.y += .25; if (e.v > 0) { c.fillStyle = rgba(this.col, e.v * .8); c.fillRect(e.x, e.y, 2.4, 2.4); } }
      let g = c.createRadialGradient(p.x, y, 2, p.x, y, 62 * k);
      g.addColorStop(0, rgba(this.col, .42)); g.addColorStop(.5, rgba(this.col, .08)); g.addColorStop(1, rgba(this.col, 0));
      c.fillStyle = g; c.beginPath(); c.arc(p.x, y, 62 * k, 0, 7); c.fill();
      const bat = quieto ? 1 : .35 + .65 * Math.abs(Math.sin(t * 22));
      c.save(); c.translate(p.x, y); c.scale(k, k); c.rotate(Math.max(-.35, Math.min(.35, p.vx * .04)));
      c.globalCompositeOperation = "lighter";
      this._ala(1, true, bat); this._ala(-1, true, bat); this._ala(1, false, bat); this._ala(-1, false, bat);
      c.globalCompositeOperation = "source-over";
      const R = 11;
      g = c.createRadialGradient(-3, -4, 1, 0, 0, R);
      g.addColorStop(0, "rgba(255,255,255,.95)"); g.addColorStop(.35, rgba(this.col, .9)); g.addColorStop(1, rgba(this.col.map((v) => v * .25), .95));
      c.fillStyle = g; c.beginPath(); c.arc(0, 0, R, 0, 7); c.fill();
      c.save(); c.beginPath(); c.arc(0, 0, R, 0, 7); c.clip(); c.globalCompositeOperation = "lighter"; c.lineWidth = .8;
      for (let i = 0; i < 4; i++) { c.strokeStyle = i % 2 ? "rgba(255,255,255,.3)" : rgba(this.col, .3); c.beginPath(); c.ellipse(0, 0, R * (.9 - i * .12), R * (.3 + i * .1), t * (1.2 + i * .3) + i, 0, 7); c.stroke(); }
      c.restore();
      for (const [rad, sen, guion, grosor, op] of [[19, 1, [8, 5], 1.1, .8], [25, -1.4, [2, 6], .7, .55]]) {
        c.save(); c.rotate(t * sen); c.setLineDash(guion); c.strokeStyle = rgba(this.col, op); c.lineWidth = grosor; c.beginPath(); c.arc(0, 0, rad, 0, 7); c.stroke(); c.restore();
      }
      c.strokeStyle = rgba(this.col, .6); c.lineWidth = 1;
      for (let i = 0; i < 4; i++) { const a = i * Math.PI / 2 + Math.PI / 4 + t * .4; c.beginPath(); c.moveTo(Math.cos(a) * 29, Math.sin(a) * 29); c.lineTo(Math.cos(a) * 33, Math.sin(a) * 33); c.stroke(); }
      c.restore();
      if (quieto) return;   // con «reducir movimiento», un solo fotograma
      this.raf = requestAnimationFrame(this._dibujar);
    }
  }
  return Ping;
})();
