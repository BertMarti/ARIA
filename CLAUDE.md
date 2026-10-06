# 🤖 CLAUDE.md - ARIA - Configuración de Agentes

## Resumen

ARIA es un asistente IA autónomo que funciona completamente en tu Raspberry Pi 5. Este documento describe cómo los agentes Claude deben configurar y mantener ARIA.

## Agentes Autónomos Integrados

### Agent 1: Setup Agent (Opus 5.5)
**Responsabilidad:** Configuración inicial del sistema

**Tareas:**
1. Instalar Ollama en la Raspberry Pi
2. Descargar modelo Mistral 7B o Llama 2
3. Configurar FastAPI y FastUI
4. Inicializar base de datos SQLite
5. Generar JWT secret automáticamente
6. Crear usuario admin por defecto

**Ejecución:** Una vez al inicio, luego bajo demanda

---

### Agent 2: Integration Agent (Sonnet 5.5)
**Responsabilidad:** Integrar APIs externas

**Tareas:**
1. Conectar con Netflix API
2. Conectar con Spotify API
3. Configurar credenciales de forma segura
4. Probar conexiones y reportar estado
5. Actualizar integraciones automáticamente

**Ejecución:** Bajo demanda, con triggers automáticos

---

### Agent 3: Monitor Agent (Haiku 4.5)
**Responsabilidad:** Monitoreo continuo y mantenimiento

**Tareas:**
1. Health checks cada 5 minutos
2. Monitoreo de logs en tiempo real
3. Auto-restart si algún servicio falla
4. Reportar estado del sistema
5. Alertas de problemas

**Ejecución:** Continuo (24/7)

---

## Instrucciones para Agentes

### Setup Inicial
```bash
# Los agentes automáticamente ejecutarán:
pip install -r docker/requirements.txt
python src/main.py

# Ollama se instalará automáticamente
ollama pull mistral
```

### Testing
```bash
curl http://localhost:8001/health
curl http://localhost:8001/api/chat -d '{"message":"Hola"}'
```

### Logs y Debugging
```bash
docker-compose logs -f aria
docker-compose logs aria --tail 100
```

---

## Variables de Entorno (Auto-generadas)

Los agentes generarán automáticamente:
- `JWT_SECRET` - Seguridad de tokens
- `ADMIN_PASSWORD` - Contraseña inicial admin
- `OLLAMA_MODEL` - Modelo IA a usar

---

## Próximos Pasos para Agentes

1. ✅ **Setup Agent** - Instala todo (automático)
2. ✅ **Integration Agent** - Conecta APIs (automático)
3. ✅ **Monitor Agent** - Monitorea 24/7 (automático)

---

**Documento en español** 🇪🇸  
Última actualización: 2026-10-06  
🤖 Construido con Claude AI
