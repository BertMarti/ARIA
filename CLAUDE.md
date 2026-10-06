# 🤖 CLAUDE.md - ARIA Configuration for Agents

## Overview
ARIA es un asistente IA autónomo. Este documento describe cómo los agentes Claude deben configurar y mantener ARIA.

## Agentes Autónomos

### Agent 1: Setup Agent (Opus)
**Responsabilidad:** Configuración inicial
**Tasks:**
1. Instalar Ollama en la Raspberry Pi
2. Descargar modelo Mistral 7B
3. Configurar FastAPI
4. Setup inicial de base de datos
5. Generar JWT secret

### Agent 2: Integration Agent (Sonnet)
**Responsabilidad:** Integrar APIs externas
**Tasks:**
1. Conectar Netflix API
2. Conectar Spotify API
3. Configurar credenciales
4. Test de conexiones

### Agent 3: Monitor Agent (Haiku)
**Responsabilidad:** Monitoreo y mantenimiento
**Tasks:**
1. Health checks cada 5 minutos
2. Logs monitoring
3. Auto-restart si falla
4. Reportar estado

## Instrucciones para Agentes

### Environment Setup
```bash
pip install -r requirements.txt
python src/main.py
```

### Testing
```bash
curl http://localhost:8000/health
```

### Logs
```bash
docker-compose logs -f aria
```

## Next Steps
- Implementar integración con Ollama
- Agregar Netflix API
- Agregar Spotify API
- Web UI

