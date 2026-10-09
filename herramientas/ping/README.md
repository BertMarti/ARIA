# Ping en SVG

Ping (el hada de luz de ARIA) dibujado en **SVG animado** para el README y la documentación: GitHub no ejecuta JavaScript, pero sí anima el CSS que va dentro de un SVG. Es la misma figura del escaparate (`app/static/escaparate/ping.js`): esfera con remolino, anillos que giran, alas holográficas que baten y estela de píxeles. Con «reducir movimiento», se queda quieta.

```bash
python3 herramientas/ping/generar_svg.py   # → docs/img/ping/*.svg
```

Para añadir otro Ping, pon una línea en `PINGS` con su estado (`ok` cian, `aviso` ámbar, `alerta` rosa, `pensando` violeta), su frase y si va volteado (Ping a la derecha y el bocadillo a la izquierda).
