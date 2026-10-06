# 🤖 ARIA - Asistente IA para tu hogar

**Estado:** En desarrollo (esqueleto inicial)
**Versión:** 0.1.0
**Licencia:** MIT

## ¿Qué es ARIA?

ARIA es un asistente de IA **gratuito y local** que se ejecuta en una Raspberry Pi 5 (8 GB) y se usa desde el navegador de cualquier PC de tu red.

### Funcionalidades previstas

- 💬 Chat en lenguaje natural con modelos locales vía **Ollama** (sin APIs de pago)
- 🎵 Control de reproducción de Spotify
- 🎬 Accesos rápidos a Netflix
- 🌐 Interfaz web con usuario/contraseña y HTTPS
- 🧩 Arquitectura de integraciones ampliable

## Estado actual

Por ahora el repositorio contiene un servidor FastAPI mínimo (`/health` y un `/api/chat` de prueba), el `Dockerfile` y el `docker-compose.yml`. La conexión real con Ollama, las integraciones y la interfaz web están pendientes.

## Requisitos

- Raspberry Pi 5 (8 GB de RAM) con Raspberry Pi OS de 64 bits, u otra distribución Linux
- Docker y Docker Compose
- ~8 GB libres en disco para los modelos

## Instalación

```bash
git clone https://github.com/BertMarti/ARIA.git
cd ARIA
cp .env.example .env
docker compose up -d
```

Comprobar que funciona:

```bash
curl http://localhost:8001/health
```

## Estructura

```
ARIA/
├── docker/          # Dockerfile y dependencias
├── src/main.py      # Servidor FastAPI
├── .env.example     # Variables de entorno de ejemplo
└── docker-compose.yml
```

## Documentación para agentes

- [CLAUDE.md](CLAUDE.md) – instrucciones para Claude Code
- [AGENTS.md](AGENTS.md) – reparto de tareas entre agentes
- [SKILLS.md](SKILLS.md) – capacidades del asistente
- [MEMORY.md](MEMORY.md) – memoria y decisiones del proyecto

## Licencia

MIT
