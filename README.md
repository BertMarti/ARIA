# 🤖 ARIA - AI Assistant for Your Home

**Status:** Pre-release (MVP Phase 1)
**Version:** 0.1.0

## What is ARIA?

ARIA is a **free, local-first AI assistant** that runs on your Raspberry Pi 5.

### Features
- 💬 Natural language chat (Ollama)
- 🎬 Netflix search and control
- 🎵 Spotify playback control
- 🌐 Web UI
- 🔐 Secure (all local)

## Quick Start

```bash
# Clone
git clone https://github.com/BertMarti/ARIA.git
cd ARIA

# Setup
cp .env.example .env
docker-compose up -d

# Access
https://your-rp-ip:443
```

## Architecture

```
FastAPI (8001)
├── Ollama Chat
├── Netflix Integration
├── Spotify Integration
└── Auth/JWT
```

## Requirements

- Raspberry Pi 5 (8GB RAM)
- Docker & Docker Compose
- 8GB disk space

## See Also

- [CLAUDE.md](CLAUDE.md) - Agent configuration
- [AGENTS.md](AGENTS.md) - Autonomous workflows
- [SKILLS.md](SKILLS.md) - Custom skills
- [MEMORY.md](MEMORY.md) - Agent memory

## License

MIT
