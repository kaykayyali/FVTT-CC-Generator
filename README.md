# FVTT-CC-Generator

An AI-powered Campaign Codex content generator for Foundry VTT v14 — describe a place, an NPC, or a quest, and a local agent drafts a structured Campaign Codex sheet for you in seconds.

## What is this?

FVTT-CC-Generator is a two-part project:

1. **`foundry-module/`** — a Foundry VTT v14 module that adds an **AI Designer** sidebar tab. You pick a sheet type, write a prompt, and the module streams a draft back for review before committing it to your world.
2. **`agent/`** — a small local Python WebSocket service (the **`fab-agent`**) that talks to your LLM provider, applies four `SKILL.md` playbooks, searches your existing compendia for reusable content, and returns validated JSON.

The two communicate over `ws://127.0.0.1:7777/ws/v1` — no cloud, no telemetry, no third-party server.

## Why?

- **Hermes-powered, but local-first.** The agent was originally driven by Hermes Agent's skill format, but in v1 the runtime is **plain Python** with the four `SKILL.md` playbooks loaded at startup. You can swap the LLM behind it without touching Foundry.
- **Compendium-search-first.** The agent is required to look up SRD actors and items in your existing compendia before inventing new ones. You will not get three competing copies of "Goblin" because it found the SRD goblin and reused its UUID.
- **GM in the loop.** Every sheet is previewed before commit. The agent drafts, you review, you refine, then you save.
- **No Foundry-side LLM coupling.** Foundry v14's "AI" story is still immature. Keeping the LLM in a separate process means you can use OpenAI, Anthropic, OpenRouter, Ollama, Azure, Bedrock, or Vertex — and you can run the agent on a different machine if you want.

## How it works

```
+----------------------+        ws://127.0.0.1:7777/ws/v1          +-----------------+
|  Foundry VTT module  |  <--------------------------------------> |   fab-agent     |
|  (FVTT-CC-Generator) |   Sec-WebSocket-Protocol: fab.v1.token=…  |  (Python)       |
+----------------------+                                            +--------+--------+
        |                                                                   |
        |  reads Foundry compendia, journals, CC TOC                         |  calls LLM via litellm
        v                                                                   v
+----------------------+                                            +-------------+
|  Foundry VTT world   |                                            |  LLM API    |
+----------------------+                                            +-------------+
```

1. You write a prompt in the AI Designer sidebar and pick a sheet type (location, npc, region, shop, group, quest).
2. The Foundry module opens (or reuses) a WebSocket to `fab-agent` on `127.0.0.1:7777` and sends a `design.start` envelope.
3. `fab-agent` composes a system prompt from the four `SKILL.md` playbooks + your world context + a compendium search, then calls the LLM.
4. The LLM returns a JSON draft. The agent validates it against the Campaign Codex schema and pushes a `design.preview` event back.
5. The sidebar renders the preview. You refine, link to existing CC sheets, or hit **Commit**.
6. On commit, the Foundry module writes the document directly into your world and (optionally) auto-links it in the Campaign Codex TOC.

## Quick Start

```bash
# 1. Install the Foundry module via the manifest URL
#    https://raw.githubusercontent.com/kaykayyali/FVTT-CC-Generator/main/foundry-module/module.json
#    Then enable it in your world. Campaign Codex is a soft dependency — install it too.

# 2. Install the local agent
git clone https://github.com/kaykayyali/FVTT-CC-Generator.git
cd FVTT-CC-Generator/agent
uv sync
cp .env.example .env
$EDITOR .env            # set LLM_API_KEY and LLM_MODEL

# 3. Start the agent
uv run fab-agent

# 4. Open Foundry → AI Designer sidebar tab → should read "Connected"
```

That's it. Write a prompt, click **Design**, review the preview, **Commit**.

## Architecture

The Foundry module owns the UI and the world-write side. `fab-agent` owns the LLM, the skills, and the JSON validation. They are decoupled by a small JSON-over-WebSocket protocol documented in [docs/wiki/protocol.md](docs/wiki/protocol.md). The full architecture — including the four `SKILL.md` playbooks, the validation pipeline, and the compendium-search-first guarantee — is in [docs/wiki/architecture.md](docs/wiki/architecture.md).

## Documentation

| Page | Audience | What's in it |
| --- | --- | --- |
| [Install](docs/wiki/install.md) | GMs | Prerequisites, manifest URL, `uv` setup, token, verify |
| [Usage](docs/wiki/usage.md) | GMs | The AI Designer sidebar, workflow, tips |
| [Architecture](docs/wiki/architecture.md) | Devs | Skills, data flow, project layout |
| [Protocol](docs/wiki/protocol.md) | Integrators | WebSocket messages, envelopes, errors |
| [Development](docs/wiki/development.md) | Contributors | Add a sheet type, add a skill, lint, release |
| [Troubleshooting](docs/wiki/troubleshooting.md) | Everyone | Common failures and fixes |

## Companion modules

- **[Campaign Codex](https://foundryvtt.com/packages/campaign-codex)** — *required* as a soft dependency. The agent emits sheets in CC's schema; the sidebar links to CC's TOC.
- **dnd5e system** — *required*. The agent expects dnd5e compendia for the search-first guarantee to be useful.

The module will load without Campaign Codex, but the **Commit** step will be a no-op and the sidebar will show a warning.

## Contributing

Issues and PRs welcome. See [docs/wiki/development.md](docs/wiki/development.md) for the dev workflow, code style, and how to add a new sheet type or skill. The agent is a small, fast-moving project — start by opening an issue so we can align on the design before you write code.

## License

MIT — see `LICENSE`.
