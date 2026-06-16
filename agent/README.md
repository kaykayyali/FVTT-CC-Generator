# fab-agent

The local Python WebSocket agent that powers [FVTT-CC-Generator](../foundry-module/).
The companion Foundry VTT v14 module connects to this agent over a loopback
WebSocket and uses it to generate structured **Campaign Codex** sheets
(location, npc, region, shop, group, quest) for a tabletop campaign.

The agent is **standalone**: it has no dependency on the Hermes Agent
runtime. It speaks directly to your chosen LLM provider via
[`litellm`](https://github.com/BerriAI/litellm) (OpenAI, Anthropic,
OpenRouter, Ollama, Azure, Bedrock, VertexAI, …) and combines the
[four SKILL.md](src/fab_agent/skills) files into the LLM's system prompt.

```
+----------------------+        ws://127.0.0.1:7777/ws/v1          +-----------------+
|  Foundry VTT module  |  <--------------------------------------> |   fab-agent     |
|  (FVTT-CC-Generator) |   Sec-WebSocket-Protocol: fab.v1.token=…  |  (this project) |
+----------------------+                                            +--------+--------+
                                                                              |
                                                                              v
                                                                       +-------------+
                                                                       |  LLM API    |
                                                                       | (litellm)   |
                                                                       +-------------+
```

---

## Requirements

* Python **3.10** or newer
* [`uv`](https://docs.astral.sh/uv/) (recommended) — falls back to `pip` if you prefer
* An API key for the LLM provider of your choice (Ollama needs no key)

## Install

```bash
cd agent

# 1. Create the env and install deps + the fab-agent console script
uv sync

# 2. Copy and edit the env template
cp .env.example .env
#   $EDITOR .env
```

## Configure

Open `.env` and set the four blocks described in `.env.example`. The most
important variables are:

| Variable           | Example                                  | Notes                       |
| ------------------ | ---------------------------------------- | --------------------------- |
| `FAB_LLM_PROVIDER` | `openai` / `anthropic` / `openrouter` / `ollama` | Bare name or litellm prefix |
| `FAB_LLM_MODEL`    | `gpt-4o` / `anthropic/claude-sonnet-4-20250514` | Can be a fully-qualified litellm model string |
| `FAB_LLM_API_KEY`  | `sk-…`                                   | Not required for Ollama     |
| `FAB_AGENT_TOKEN`  | (any shared secret)                      | **Must match** the value in the Foundry module settings |

The token is sent in the `Sec-WebSocket-Protocol: fab.v1.token=<token>` header
on every connect. Mismatched tokens are rejected at the WebSocket layer
before any application code runs.

## Run

```bash
# Start the server with the values from .env
uv run fab-agent

# Or as a module
uv run python -m fab_agent
```

You should see something like:

```
2026-06-16 12:34:56 INFO  fab_agent.server — loaded 4 skills (88.4 KB)
2026-06-16 12:34:56 INFO  fab_agent.server — listening on ws://127.0.0.1:7777/ws/v1
2026-06-16 12:34:56 INFO  fab_agent.server — LLM ready: gpt-4o (openai)
```

The Foundry module will auto-connect on its `ready` hook and announce the
connection in its chat banner.

## CLI flags

`fab-agent` accepts a small set of overrides that take precedence over `.env`:

```
fab-agent [--port N] [--token T] [--model M] [--host H]
          [--provider {openai,anthropic,openrouter,ollama,...}]
          [--log-level LEVEL]
          [--check]
          [--help]
```

| Flag          | Effect                                                                |
| ------------- | --------------------------------------------------------------------- |
| `--port N`    | Override `FAB_AGENT_PORT` for this run                                |
| `--host H`    | Override `FAB_AGENT_HOST`                                              |
| `--token T`   | Override `FAB_AGENT_TOKEN`                                             |
| `--model M`   | Override `FAB_LLM_MODEL` (provider inferred from the model string)    |
| `--provider`  | Override `FAB_LLM_PROVIDER`                                            |
| `--log-level` | Override `FAB_LOG_LEVEL` (DEBUG/INFO/WARNING/ERROR)                    |
| `--check`     | Validate config + skills + LLM connectivity, print report, exit      |

`--check` is a **smoke test**: it loads the four SKILL.md files, configures
the LLM client, fires a tiny completion (e.g. `"ping"`), and prints a
human-readable pass/fail report. Use it after editing `.env` to make sure
the agent is wired up before the Foundry module tries to connect.

## Protocol

The wire protocol is documented inside the codebase. The high-level shape is:

* **URL:** `ws://127.0.0.1:7777/ws/v1`
* **Auth:** `Sec-WebSocket-Protocol: fab.v1.token=<token>`
* **Encoding:** JSON, UTF-8
* **Request/response:** `{ "id": "...", "type": "hello" | "design.start" | ... , "payload": {...} }`
  → `{ "id": "...", "ok": true, "type": "hello.result" | ..., "result": {...} }`
* **Server-pushed events:** `{ "type": "design.thinking" | "design.preview" | "design.committed" | "design.error", "sessionId": "...", ... }`

See `src/fab_agent/protocol.py` for the Pydantic message models, and
[`foundry-module/scripts/lib/ws-client.js`](../foundry-module/scripts/lib/ws-client.js)
for the matching JS implementation.

## Development

```bash
# Run the test suite
uv run pytest -q

# Lint
uv run ruff check src tests

# Type check
uv run mypy src
```

The validator unit tests live in `tests/test_validators.py`.

## Project layout

```
agent/
├── pyproject.toml
├── README.md
├── .env.example
├── src/fab_agent/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py             # argparse entry point
│   ├── config.py          # Pydantic settings
│   ├── server.py          # asyncio WebSocket server
│   ├── protocol.py        # Pydantic WS message models
│   ├── handlers.py        # design.start / design.refine / design.commit
│   ├── validators.py      # CC draft validators
│   ├── prompts.py         # system prompt builder
│   ├── skills_loader.py   # loads 4 SKILL.md files
│   ├── llm.py             # litellm wrapper
│   ├── skills/
│   │   ├── campaign-codex-sheets/SKILL.md
│   │   ├── dnd5e-content-authoring/SKILL.md
│   │   ├── compendium-search-first/SKILL.md
│   │   └── world-context-linking/SKILL.md
│   └── templates/
│       └── dnd5e/
│           ├── actor.json
│           ├── item.json
│           └── journal-page.json
└── tests/
    └── test_validators.py
```

## License

MIT — see the repository root [`LICENSE`](../LICENSE).
