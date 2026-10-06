# 🤖 AGENTS.md - Autonomous Agent Workflows

## Agent Registry

### SetupAgent (Opus 5.5)
- **Model:** claude-opus-5-5
- **Role:** Initial setup and configuration
- **Schedule:** On-demand
- **Tools:** Bash, File I/O, Docker
- **Instructions:** See CLAUDE.md

### IntegrationAgent (Sonnet 5.5)
- **Model:** claude-sonnet-5-5
- **Role:** API integrations
- **Schedule:** On-demand
- **Tools:** HTTP, File I/O, Testing
- **Instructions:** See CLAUDE.md

### MonitorAgent (Haiku 4.5)
- **Model:** claude-haiku-4-5
- **Role:** Health monitoring
- **Schedule:** Every 5 minutes
- **Tools:** Bash, Health checks
- **Instructions:** See CLAUDE.md

## Workflow

1. **Setup** → Prepare environment
2. **Integration** → Connect APIs
3. **Monitor** → Continuous health checks
4. **Update** → Auto-update when needed

## Configuration

Agentes se configuran automáticamente con variables:
- `GITHUB_TOKEN` - Para updates
- `OPENAI_COMPATIBLE_API` - Para Ollama
- `SERVICE_AUTH_TOKEN` - Autenticación interna

