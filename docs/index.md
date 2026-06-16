---
title: FVTT-CC-Generator
description: AI-powered Campaign Codex content generator for Foundry VTT v14
---

# FVTT-CC-Generator

AI-powered Campaign Codex content generator for Foundry Virtual Tabletop v14.

A wrapper Foundry module talks to a local Python agent over WebSocket. The
agent produces structured Campaign Codex sheets (locations, NPCs, regions,
shops, groups, quests) — with **compendium-search-first** reuse of existing
items and actors from your world and the dnd5e SRD.

## Documentation

- [Home & Overview](./index)
- [Install Guide](./install)
- [User Guide](./usage)
- [Architecture](./architecture)
- [WebSocket Protocol](./protocol)
- [Development Guide](./development)
- [Troubleshooting](./troubleshooting)

## Quick Start

1. **Install the Foundry module** with manifest URL: `https://raw.githubusercontent.com/kaykayyali/FVTT-CC-Generator/main/foundry-module/module.json`
2. **Enable Campaign Codex** (required soft dependency)
3. **Install the agent**:
   ```bash
   cd agent
   uv sync
   cp .env.example .env  # edit with your LLM API key
   uv run fab-agent
   ```
4. **Open the AI Designer** in the Foundry sidebar.

## Links

- [GitHub Repository](https://github.com/kaykayyali/FVTT-CC-Generator)
- [Issue Tracker](https://github.com/kaykayyali/FVTT-CC-Generator/issues)
- [Campaign Codex Module](https://foundryvtt.com/packages/campaign-codex)

## License

[MIT](https://github.com/kaykayyali/FVTT-CC-Generator/blob/main/LICENSE)
