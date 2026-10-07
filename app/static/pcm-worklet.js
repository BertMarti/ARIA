"use strict";
// AudioWorklet: convierte el micrófono (44,1/48 kHz, float) en PCM 16 kHz mono int16 y lo
// entrega en bloques de 80 ms (1280 muestras) al hilo principal, que los envía por WebSocket.
class Pcm16k extends AudioWorkletProcessor {
  constructor() {
    super();
    this.paso = sampleRate / 16000;  // muestras de entrada por muestra de salida
    this.pos = 0; this.suma = 0; this.cuenta = 0;
    this.buf = new Int16Array(1280); this.n = 0;
  }
  process(entradas) {
    const canal = entradas[0] && entradas[0][0];
    if (!canal) return true;
    for (let i = 0; i < canal.length; i++) {
      // Diezmado con media (filtro paso bajo sencillo para evitar aliasing).
      this.suma += canal[i]; this.cuenta++; this.pos += 1;
      if (this.pos >= this.paso) {
        this.pos -= this.paso;
        const v = Math.max(-1, Math.min(1, this.suma / this.cuenta));
        this.buf[this.n++] = v < 0 ? v * 32768 : v * 32767;
        this.suma = 0; this.cuenta = 0;
        if (this.n === this.buf.length) {
          this.port.postMessage(this.buf.buffer, [this.buf.buffer]);
          this.buf = new Int16Array(1280); this.n = 0;
        }
      }
    }
    return true;
  }
}
registerProcessor("pcm16k", Pcm16k);
