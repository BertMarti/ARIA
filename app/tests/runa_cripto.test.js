// Cifrado de la página «Crear secreto» del módulo RUNA (modulos/runa/web/runa-cripto.mjs) frente a vectores
// generados por protocolo.py con la misma llave e IV: el navegador debe producir exactamente los mismos bytes.
// Uso: node app/tests/runa_cripto.test.js
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");

const VECTORES = [{"texto": "hola, ARIA", "pass": "", "ciphertext": "AAECAwQFBgcICQoL91RgYsUPNQ7ORm-avV_I8Vt7vUlaj0rhGPGU5UAkbfbPsNtVu7dya1a_sKT936gkPU1oUgQe1YZk2LtuyHzCWKRJrb9fQC6lAScT3m5NOKeAh1J7E1E-9ufAywB1k98VzF0n1EPALnC86D0CBr6EuS1IEP5RKSEyP3SflykbqRoq6PttsoDspNVUm0RAkU9_XXeAVTaj7QL2Zh2eTpjqBF4yditCEwAlfnQkVISO_UC6NxK8n8RvZiAF9Ok6KgWqObfa7WfCAetl8UVZspZffJbQo6uoGUkigLDIr5PXGBAkpnv81FeYz7nswkwOzU9QgCldiPyI1wdnxEjWpbskCXLbVDw6k3UimyslPw0EL_RRP47NJaI_obzt5UKhcR70LqCkUR57mMLA1NuvzrXGdjCOH7rPh_4jVkYS1MywLeB9cwFmRvriy1s1Y5zjpNEKyHqPyGB1K0cMl0FNJcNBp4vG5nhtE4izQv6nSgppbRF6xdDndEuJgsyuh3Ey64gw3_NAUnZWgCdiciuoMuEZzJun_zv7KRGyOn45nD2DPL8a8KmBtIJ3EG4NX0zdNwfNTXv-_HYywpqcryXeXjRQQl3_ctYKPCIzCUl0Agq1xA7FrwN7_KGvyoGKpQZ_OxCGwhzLWn3lCQIqBVw7_oPvACVYaebeKX0aUoO3ehL0R82GJgZ62LFMqirf1QAHwg27zgXDCscIXqkksfAnMbm49SJBmNs5aaNVBXXBu4kG2erNvJ1inmhURxlrSN8LNG0w4LPH72II5ouG6_cTNejmuK5rC297HbU976ooRBktnry6gn_8eO0EGO08p3oyRPoLGfyQt5NgjJDDwPNTXgXCF7lfKr7MH97erLGna6XvwQ-rCZI74-bphYLt8zD5fuN4G5v9YI-1oBIFZyxvyyVsg65mYTmsxJDOwleOZZVBlOhEPAmGGcCLrh1--a6BFxyezDCgTxmrdxfzhZJtA5rhDkb-dNIaF-HV8IRe_GHwZ4PpgElnvOhjwG3tF1D3zmrsVe3QGGiKGQiLIbfX0H5Uwt-n85tbyCh0fflGsYCTdrEJbd4zgcFxFAi7Iwl2VuR6EqvODEh2vRJdhw12ubk-S4RQKPEG7EkR1NtSJUkWKK7CKY9FmNQamNg2rCPS55Dph70soCB2XSsS_F-ICk7ZgYGvefITq1SlxylY2r1b0U5apRJpB1CwbC0ZWpAz4tulbIjtADTphG4cg1cIzP1MVAuzsZ98zWOJCIP8qktv7WGRAURQdUyV8qhJj8lJKuIEdbdDWAZN-JZWoA7ng5Pvsk0DimI7VKNPNWxgi5KnzSyzv3hJAKkhR1Gfu_lhkZCVAeXPyF2N_4jr5rfo0DZ0-Cl0gtH7ol0Lo_golcM8fbY", "verifier": "d6fcaaefa3fbc55cf3298c52644198fce20ec1ff8506380aff7a38d8d7908579", "linkVerifier": "185492f15a0712d9ced01b9d89d23ab39a226f4730f5d256b5e621493b1215f2", "fragmento": "v1.AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8"}, {"texto": "Clave: Ñu-77 ✓", "pass": "caballo", "ciphertext": "AAECAwQFBgcICQoLl4V_uiPIIa1Cg4tunc15tFcHtd7oQ0tJXs44zWlVQtk10VKi8oDTYVeUus3qckkfxYXNpCrLeTwBv1WPVGKpI-7vwKizsUC7ZeiN-WlLM911VhU6yFsTy9DN66lMNleZ1YBs4tvZkZ5jAen4XGhuTOK3VtfO6hteFjyCvYKVFRYEgi0qFaf2-Jtkmy4TrU7dqROOJviqiip2gg7Z0kd54wQ1NDVmbv7mkooyRD4os3cJHmRvUo-LE54aBsMdprViaa1xteViMxWNsPiLjE--XxrU5S2j0awJCPophoGHqYCRNNmUTXblbL9oDmUN5bnJ_0PzuO3JzaISiciviRzGqEUAu-NmaNbiOZPrYvhbzMkRhc-meD9DClCW6fB7lMjbI3ZHx82CNVEHGPh7M1PoqIttwC8SYc-SgNZqW6mwcnJ4-mhZKuSe-Qmr_UrWgWyHIfEysjaOVFJ8-g7UdwdrIvsv8ut0FZgoq7SDcE0vQWq_T-zYkoBOZ59B0bMa8cEfk43eJA9pQr31mvkNT0nL9Naoy7z51SG9JWUj__M8iou20Hk1yIoJaEamES3KC3T6BjUGM_RqE743WQO6DqabuP34Y74z2KBnQ5k2RjPR5o1ib2Oy5r822JCcd0Eob-JOTXOYABpNZAeoNWN0K28bOPhvgP2P8X0MJqnTr3di-vgeMQDzR5NmRMISK2wdsuRwqH-aJGoME7eiQymugzABN788ByxVbBximXUP4EBTml-2wZpXKvp4NS73w1AqhFIMtldTQ5plQC3kIt_iMj7T7vPJw7daPiz3g4yKiXTEEreWKDcrmme844d22UY6N3Rzq6iPkUIkvMSGP4l3E4uYnxI6caQ-aOt3ZnLtQR666dRFIyQvMeC3D61c9b0VIAKELM8vYXeikz-qluIP-qGXVcnKYBINiiPnti5ljxtToth7fb1lP3sCA2r8yVc9J-8-wV4jA34D60YbRZxqKLKyH9qeDNahjr6exxz0nTaKPKYWXKbB5fOPa5Ea6RxiKu0F5HwOwj8oWtSFD7sL4P8g3ArYZvgTs1zzIgL_fhEXU3NM1Y8Qg9ocnUSkXyTVbkvGZ1SLAuF3bwfL_ZHa4WhXNxHiwe3lJowNr3aCdGPXtupufZhip-i-KVbaVTfmHGO_BDrvk8iflf5PGUC_7zFIxir-ZuvW_PYI-DH1kuGankHA_mH8K7bkGTyw6jlFR81F__YINGgMILZ4nwaS2bPC4nOk6zgscA6lrx1Ycks5taWYhbUdpc3kQA24DyzNYMH7QfmFx9s-hTJtoxD2u0yV5a39DeUsDLV7iifpKBKudSAupI-ERHHOC5PEgVY-ET4ObcwPaEHHbwmh_J93RxW-Ksq6ENpYxz4f_Q186lS8fU8", "verifier": "4787b866c94bc756b3bfdcfd90b5c2a7c0963d1fb3c81b1cfafb8ebc14d02fce", "linkVerifier": "185492f15a0712d9ced01b9d89d23ab39a226f4730f5d256b5e621493b1215f2", "fragmento": "v1.AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8.p"}];
const web = path.join(__dirname, "..", "..", "modulos", "runa", "web");

(async () => {
  const { sellar, BLOQUES } = await import(path.join(web, "runa-cripto.mjs"));
  const K = Uint8Array.from({ length: 32 }, (_, i) => i);
  const IV = Uint8Array.from({ length: 12 }, (_, i) => i);
  for (const v of VECTORES) {
    const s = await sellar(v.texto, v.pass, K, IV);
    assert.deepStrictEqual(s, { ciphertext: v.ciphertext, verifier: v.verifier, linkVerifier: v.linkVerifier, fragmento: v.fragmento },
      `vector «${v.pass ? "con" : "sin"} contraseña» distinto de protocolo.py`);
  }
  // Llave e IV aleatorios en uso normal, y relleno a bloque fijo (1 y 900 caracteres pesan igual).
  const a = await sellar("x"), b = await sellar("x".repeat(900));
  assert.notStrictEqual(a.fragmento, b.fragmento);
  assert.strictEqual(a.ciphertext.length, b.ciphertext.length);
  assert.ok(BLOQUES.every((n) => n <= 1024 * 1024));    // el servidor de ARIA no reenvía más de 1 MiB
  // La interfaz nunca interpreta texto como HTML.
  for (const f of ["crear.js", "runa-cripto.mjs"]) {
    assert.doesNotMatch(fs.readFileSync(path.join(web, f), "utf8"), /innerHTML|outerHTML|insertAdjacentHTML|document\.write|eval\(/, f);
  }
  console.log("runa_cripto: ok");
})().catch((e) => { console.error(e); process.exit(1); });
