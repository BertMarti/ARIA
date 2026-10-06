"use strict";
// Markdown seguro construido solo con nodos del DOM (nunca innerHTML).
// Soporta: párrafos, **negrita**, *cursiva*, `código`, bloques ```, listas con
// viñetas y numeradas, títulos (#) y enlaces http(s) (rel=noopener).

const MD_INLINE_SRC = /(`[^`\n]+`|\*\*[^*\n]+?\*\*|\*[^*\s][^*\n]*?\*|\[[^\]\n]+\]\(https?:\/\/[^\s)]+\)|https?:\/\/[^\s<>)"']+)/;

function mdUrlSegura(u) {
  try { return ["https:", "http:"].includes(new URL(u).protocol); } catch (_) { return false; }
}
function mdEnlace(url, texto) {
  return el("a", { href: url, target: "_blank", rel: "noopener noreferrer" }, texto);
}

function mdInline(txt, padre) {
  let ultimo = 0, m;
  const re = new RegExp(MD_INLINE_SRC.source, "g"); // una instancia por llamada (mdInline es recursiva)
  while ((m = re.exec(txt))) {
    if (m.index > ultimo) padre.append(txt.slice(ultimo, m.index));
    const t = m[0];
    if (t[0] === "`") padre.append(el("code", null, t.slice(1, -1)));
    else if (t.startsWith("**")) { const s = el("strong"); mdInline(t.slice(2, -2), s); padre.append(s); }
    else if (t[0] === "*") { const s = el("em"); mdInline(t.slice(1, -1), s); padre.append(s); }
    else if (t[0] === "[") {
      const k = t.indexOf("](");
      const url = t.slice(k + 2, -1);
      if (mdUrlSegura(url)) padre.append(mdEnlace(url, t.slice(1, k))); else padre.append(t);
    } else {
      let url = t, cola = "";
      while (/[.,;:!?]$/.test(url)) { cola = url.slice(-1) + cola; url = url.slice(0, -1); }
      if (mdUrlSegura(url)) padre.append(mdEnlace(url, url), cola); else padre.append(t);
    }
    ultimo = m.index + t.length;
  }
  if (ultimo < txt.length) padre.append(txt.slice(ultimo));
}

function mdParrafo(lineas) {
  const p = el("p");
  lineas.forEach((l, i) => { if (i) p.append(el("br")); mdInline(l, p); });
  return p;
}

function renderMd(txt, cont) {
  cont.replaceChildren();
  const lineas = txt.replace(/\r\n?/g, "\n").split("\n");
  let i = 0, parrafo = [];
  const cerrarParrafo = () => { if (parrafo.length) { cont.append(mdParrafo(parrafo)); parrafo = []; } };
  while (i < lineas.length) {
    const l = lineas[i];
    let m;
    if ((m = /^\s*```\s*([\w+-]*)\s*$/.exec(l))) {            // bloque de código (puede estar sin cerrar al hacer streaming)
      cerrarParrafo();
      const codigo = [];
      i++;
      while (i < lineas.length && !/^\s*```\s*$/.test(lineas[i])) codigo.push(lineas[i++]);
      i++;
      const c = el("code", null, codigo.join("\n"));
      if (m[1]) c.dataset.lang = m[1];
      cont.append(el("pre", null, c));
    } else if ((m = /^(#{1,4})\s+(.*)$/.exec(l))) {            // títulos
      cerrarParrafo();
      const h = el("h" + (m[1].length + 2), { class: "md-h" });
      mdInline(m[2], h); cont.append(h); i++;
    } else if (/^\s*([-*•])\s+/.test(l) || /^\s*\d+[.)]\s+/.test(l)) {   // listas
      cerrarParrafo();
      const ord = /^\s*\d+[.)]\s+/.test(l);
      const lista = el(ord ? "ol" : "ul");
      const re = ord ? /^\s*\d+[.)]\s+(.*)$/ : /^\s*[-*•]\s+(.*)$/;
      if (ord) { const n = parseInt(l, 10); if (n > 1) lista.start = n; }
      while (i < lineas.length && (m = re.exec(lineas[i]))) {
        const li = el("li"); mdInline(m[1], li); lista.append(li); i++;
      }
      cont.append(lista);
    } else if (!l.trim()) { cerrarParrafo(); i++; }
    else { parrafo.push(l); i++; }
  }
  cerrarParrafo();
}

// Texto plano para la lectura en voz alta (sin símbolos de Markdown).
function mdATexto(txt) {
  return txt.replace(/```[\s\S]*?```/g, " ").replace(/`([^`]*)`/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1").replace(/\*([^*]+)\*/g, "$1")
    .replace(/\[([^\]]+)\]\(https?:[^)]*\)/g, "$1").replace(/https?:\/\/\S+/g, "enlace")
    .replace(/^#{1,4}\s+/gm, "").replace(/^\s*([-*•]|\d+[.)])\s+/gm, "");
}
