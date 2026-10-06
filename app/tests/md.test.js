// Prueba del renderizador de Markdown con un DOM mínimo. Uso: node app/tests/md.test.js
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");

class N { constructor(t) { this.tag = t; this.kids = []; this.dataset = {}; this.className = ""; }
  append(...c) { this.kids.push(...c); } replaceChildren() { this.kids = []; } }
global.document = { createElement: (t) => new N(t) };
const est = path.join(__dirname, "..", "static");
const src = fs.readFileSync(path.join(est, "util.js"), "utf8") + fs.readFileSync(path.join(est, "md.js"), "utf8") + "; return renderMd;";
const renderMd = new Function("el_", src.replace('"use strict";', ""))();
const el = (t) => new N(t);
const dump = (n) => typeof n === "string" ? JSON.stringify(n) : "<" + n.tag + (n.href ? " href=" + n.href : "") + ">" + n.kids.map(dump).join("") + "</" + n.tag + ">";
const render = (t) => { const d = el("div"); renderMd(t, d); return d.kids.map(dump).join(""); };

assert(render("Hola **negrita** y *cursiva*").includes("<strong>"));
assert(render("**negrita con *cursiva* dentro**").includes("<em>"));   // inline recursivo (antes: bucle infinito)
assert(render("- a\n- b").startsWith("<ul>"));
assert(render("1. a\n2. b").startsWith("<ol>"));
assert(render("# Título").startsWith("<h3>"));
assert(render("```\ncódigo <b>\n```").startsWith("<pre>"));
assert(render("```\nsin cerrar").startsWith("<pre>"));
assert(!render("[x](javascript:alert(1))").includes("href=javascript"));
assert(render("[x](https://e.com)").includes("href=https://e.com"));
assert(render("<img src=x onerror=alert(1)>").includes('"<img src=x onerror=alert(1)>"'));  // texto, no HTML
console.log("md.test.js: OK");
