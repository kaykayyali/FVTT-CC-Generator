# Install

This guide takes you from a fresh checkout to a working **AI Designer** sidebar in Foundry. The whole thing is six steps and about five minutes.

## Prerequisites

You need all of the following on the machine that runs Foundry VTT:

| Requirement | Version | Why |
| --- | --- | --- |
| **Foundry VTT** | v14.x | Module target. Earlier versions lack the v14 data-model APIs the module uses. |
| **dnd5e system** | latest | The agent expects dnd5e compendia for the search-first guarantee. |
| **[Campaign Codex](https://foundryvtt.com/packages/campaign-codex)** | 3.8+ | Soft dependency. Required for the **Commit** step to do anything useful. |
| **Python** | 3.10+ | The `fab-agent` runtime. |
| **[`uv`](https://docs.astral.sh/uv/)** | latest | Recommended Python package manager. Falls back to `pip` if you must. |
| **LLM API key** | — | OpenAI, Anthropic, OpenRouter, Azure, Bedrock, Vertex, **or** a local Ollama install (no key needed). |

> **Foundry and the agent can run on different machines.** The default is loopback, but the WebSocket is plain — point it at any reachable host with `agentHost` in the module settings.

---

## Step 1 — Install the Foundry module

In Foundry, open **Add-on Modules → Install Module** and paste this manifest URL:

```
https://raw.githubusercontent.com/kaykayyali/FVTT-CC-Generator/main/foundry-module/module.json
```

Click **Install**. Foundry will download the module and show a success toast.

> **Manual / development install:** symlink or copy `foundry-module/` into your Foundry `Data/modules/` directory and enable it in **Manage Modules** with the **FVTT-CC-Generator** entry.

---

## Step 2 — Enable Campaign Codex

1. Install **Campaign Codex** from the Foundry package browser if you haven't already.
2. Open **Game Settings → Manage Modules**.
3. Enable both **Campaign Codex** and **FVTT-CC-Generator**.

The module declares Campaign Codex as a soft dependency, so the sidebar will still open without it — but the **Commit** button will refuse to fire and show a warning.

---

## Step 3 — Install the Python agent

```bash
git clone https://github.com/kaykayyali/FVTT-CC-Generator.git
cd FVTT-CC-Generator/agent

# Create a virtualenv and install dependencies + the `fab-agent` console script
uv sync

# Create your local config from the template
cp .env.example .env
```

Open `.env` in your editor and set at minimum:

```toml
# .env (KEY=VALUE, no quoting needed)
LLM_API_KEY=sk-...                          # not required for Ollama
LLM_MODEL=openai/gpt-4o-mini                # or anthropic/claude-3-5-sonnet-latest, etc.
LLM_BASE_URL=                                # leave blank unless using a proxy / Ollama
AGENT_HOST=127.0.0.1
AGENT_PORT=7777
AGENT_TOKEN=change-me-in-module-settings     # must match the Foundry-side token (Step 4)
```

> **`uv` not available?** You can use `python -m venv .venv && source .venv/bin/activate && pip install -e .` instead. The console script will be installed as `fab-agent` into the venv.

---

## Step 4 — Configure the shared token

The Foundry module and `fab-agent` authenticate each other with a shared secret passed in the `Sec-WebSocket-Protocol` header. Both sides must agree.

1. In Foundry: open **Game Settings → Configure Settings → FVTT-CC-Generator**.
2. Find the **Agent Token** field. Paste the value you put in `AGENT_TOKEN` in `.env` (default: `change-me-in-module-settings`).
3. **Save**.

You can leave the default token for local development, but **change it for any setup reachable beyond loopback**.

---

## Step 5 — Start the agent

```bash
uv run fab-agent
```

You should see something like:

```
[fab-agent] loading 4 skills from src/fab_agent/skills
[fab-agent] listening on ws://127.0.0.1:7777/ws/v1
[fab-agent] litellm model: openai/gpt-4o-mini
```

The agent stays in the foreground. **Keep this terminal open** while you use the Foundry sidebar.

---

## Step 6 — Verify

1. In Foundry, open the right-hand sidebar and click the new **AI Designer** tab.
2. The status pill at the top should turn green and read **Connected**.
3. Pick any sheet type (e.g. **location**), type "a small coastal inn run by a retired pirate", and click **Design**.
4. Within a few seconds you should see the **thinking** indicator stream, then a preview pane with a draft.

If you see **Disconnected** or the **Design** button does nothing, jump to **[Troubleshooting](./troubleshooting.md)**.

---

## Cross-platform notes

The agent is pure Python and runs anywhere Foundry does. Tested on:

### Windows (git-bash / PowerShell)

```bash
# Use forward slashes — git-bash converts them
cd C:/Users/you/FVTT-CC-Generator/agent
uv sync
uv run fab-agent
```

If Windows Defender prompts you the first time `uv` downloads Python or the agent opens a port, allow it. The bind is on `127.0.0.1` only.

### macOS / Linux

```bash
cd ~/code/FVTT-CC-Generator/agent
uv sync
uv run fab-agent
```

If you want the agent to keep running after you close the terminal:

```bash
nohup uv run fab-agent > ~/fab-agent.log 2>&1 &
```

### Running Foundry and the agent on different machines

Set `AGENT_HOST=0.0.0.0` in `.env` and `agentHost` in the module settings to the agent's LAN IP. The `Sec-WebSocket-Protocol` token is the only auth — make sure it's a real secret on a LAN.

---

## Docker

**Not yet.** v1 is `uv run` based. A multi-stage `Dockerfile` for the agent is on the roadmap. If you need it today, the agent has no native deps beyond Python 3.10 — drop a `Dockerfile` in `agent/` and a `uv pip install --system .` will get you most of the way.

---

## Verifying the install — checklist

Walk through this list once after install. Every box should be ticked.

- [ ] Foundry v14 with the dnd5e system active
- [ ] Campaign Codex installed and enabled
- [ ] FVTT-CC-Generator installed and enabled
- [ ] `agent/.env` exists and has a valid `LLM_API_KEY` (or Ollama running)
- [ ] `AGENT_TOKEN` in `.env` matches the **Agent Token** in the module settings
- [ ] `uv run fab-agent` is running in a terminal and showing `listening on ws://127.0.0.1:7777/ws/v1`
- [ ] The **AI Designer** sidebar shows **Connected**
- [ ] A test prompt produces a preview within ~10s

If you can tick all eight, you're done — head to **[Usage](./usage.md)**.
