# ARIA de demostración

Una ARIA con **datos inventados** (Ana, Lucía, red `192.168.1.x`, Madrid) para hacer las capturas del README y probar la interfaz sin tocar tu casa.

```bash
herramientas/demo/arrancar.sh --sembrar      # construye, arranca y rellena con datos de ejemplo
python3 herramientas/demo/capturar.py docs/img   # regenera las capturas (todas o las que nombres)
herramientas/demo/arrancar.sh --parar
```

- La demo escucha solo en `127.0.0.1:18080`. Usuario `demo`; la contraseña aleatoria está en `herramientas/demo/.demo/demo.env` (no se sube a git).
- `telemetria_falsa.py` simula el agente del sistema y los dispositivos de la red; `sembrar.py` crea eventos, cumpleaños, finanzas, memoria, avisos…
- `capturar.py` usa Chromium sin ventana (CDP), en modo oscuro, con la hora de la mañana. Necesita `chromium`, `Pillow` y `websockets` (`pip install websockets`).
- Si usas Docker con `sudo`: `DOCKER="sudo docker" herramientas/demo/arrancar.sh`.
