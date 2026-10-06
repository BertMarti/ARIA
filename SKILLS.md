# 🎯 SKILLS.md - Custom Skills

## Available Skills

### skill:aria:chat
Chat con Ollama (local)

### skill:aria:netflix-search
Buscar en Netflix

### skill:aria:spotify-play
Controlar reproducción Spotify

## Creating Custom Skills

```python
# src/services/skills.py
class Skill:
    name: str
    description: str

    async def execute(self, **kwargs):
        pass
```

## Examples

See `src/services/` for implementations.

