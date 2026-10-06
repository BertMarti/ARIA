# 💾 MEMORY.md - Agent Memory System

## Memory Storage

Agentes almacenan memoria en:
- **Local:** `/app/data/agent_memory.json`
- **Persistent:** Volumes Docker
- **TTL:** 30 días

## Format

```json
{
  "agent_id": "setup-agent",
  "timestamp": "2026-10-06T00:00:00Z",
  "memory": {
    "tasks_completed": [],
    "issues_found": [],
    "config": {}
  }
}
```

## Usage

Agentes automáticamente cargan/guardan memoria.

