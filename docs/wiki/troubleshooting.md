# Troubleshooting

Common failures and how to fix them. If your problem isn't here, open an issue with the output of `uv run fab-agent --debug` and the relevant Foundry log.

## Quick diagnosis

Run through this before anything else:

1. **Is the agent running?** A foreground `uv run fab-agent` should be open. A blinking cursor and a `listening on ws://127.0.0.1:7777/ws/v1` line means yes.
2. **Is the sidebar showing Connected?** Top of the **AI Designer** tab.
3. **What does the agent's stderr say?** Most failures print a one-liner.
4. **What does Foundry's log say?** **Setup → View Console** (F12 in most browsers).

---

## Agent not connecting

**Symptoms:** the sidebar status pill stays **Disconnected**, or flickers between Connected/Disconnected.

| Check | Fix |
| --- | --- |
| Is the agent process running? | Start it: `uv run fab-agent` |
| Does `AGENT_HOST` / `AGENT_PORT` in `.env` match the Foundry module's **Agent Host** / **Agent Port** settings? | Make them match. Default is `127.0.0.1:7777`. |
| Do the tokens match? | `AGENT_TOKEN` in `.env` must equal **Agent Token** in the module settings. |
| Is something else on port 7777? | `lsof -iTCP:7777 -sTCP:LISTEN` (macOS/Linux) or `netstat -ano | findstr :7777` (Windows). Change `AGENT_PORT` if needed. |
| Firewall? | On Windows, the first time the agent binds the loopback port, Defender may prompt. Allow it. For non-loopback binds, allow inbound TCP on the port. |
| IPv6 vs IPv4? | If Foundry is on `::1` and the agent is on `127.0.0.1`, the WS upgrade will fail. Set `AGENT_HOST=0.0.0.0` (binds both) or pin both to the same family. |
| Foundry and agent on different machines? | Set `AGENT_HOST=0.0.0.0` in `.env` and **Agent Host** in the module settings to the agent's LAN IP. Confirm TCP reachability with `nc -vz <host> 7777` or `Test-NetConnection -Port 7777` on Windows. |

The server replies with WS close code `4401` on a bad token and `4404` on a version mismatch.

## LLM not responding

**Symptoms:** the **thinking** indicator spins for a long time, then the sidebar shows `LLM timeout` or `LLM auth`.

| Check | Fix |
| --- | --- |
| Is `LLM_API_KEY` set in `.env`? | Open `.env`. It must be a non-empty string. |
| Is the key valid? | `llm_auth` error → the key was rejected. Generate a new one. |
| Is `LLM_MODEL` set to something the provider supports? | `LLM_MODEL=openai/gpt-4o-mini` is a safe default. See **[Development](./development.md#adding-a-new-llm-provider)**. |
| Is the provider URL correct? | `LLM_BASE_URL` should be blank for OpenAI / Anthropic, set to the proxy URL otherwise. |
| Rate-limited? | `LLM rate_limited` → back off and retry. The agent retries with exponential backoff up to 3 times. |
| Ollama? | Make sure the Ollama daemon is running (`ollama serve`) and `LLM_BASE_URL=http://127.0.0.1:11434`. Pull the model first: `ollama pull llama3.1`. |

## Invalid JSON from LLM

**Symptoms:** `design.error { code: "schema_invalid" }` and a **Reuse suggestions** panel in the preview.

This means the LLM produced a draft that didn't match the Campaign Codex schema. It happens most often with:

- weaker / smaller models (try `gpt-4o-mini`, `claude-3-5-sonnet-latest`, or a local `llama3.1:70b`)
- very long prompts where the model loses the schema halfway through
- unusual sheet types the model has little training data for

**Fixes:**

1. **Swap to a stronger model.** This is the single biggest lever.
2. **Shorten the prompt.** Two or three concrete sentences, not a paragraph.
3. **Click Refine** with `please re-emit the draft as valid JSON` — surprisingly effective.
4. **Open an issue** with the model name and the prompt that broke. If it's a systematic failure we'll add a guardrail in the relevant `SKILL.md`.

## Sheet didn't appear in CC TOC

**Symptoms:** the **Commit** click succeeds, the journal entry exists in the **Journal** tab, but it's not in the Campaign Codex TOC.

| Check | Fix |
| --- | --- |
| Is Campaign Codex enabled? | **Manage Modules** — both modules must be ticked. |
| Did the agent set the CC flags? | Open the journal entry, **Details** tab → look for `flags.campaign-codex`. If empty, the agent couldn't find CC at draft time. |
| Did you commit before Campaign Codex loaded? | Reload the world, retry. |
| Auto-commit was on? | Check the Foundry log for `design.committed` and the linked `linkedDocs`. |

## Linked NPC doesn't resolve

**Symptoms:** the preview shows `Linked NPC: @UUID[...]` but the link is red in the journal, or the commit step fails with `uuid_unresolved`.

This means a UUID the agent picked is no longer in the world. Common causes:

- The compendium was rebuilt and UUIDs changed.
- The world was migrated from a previous system version and a referenced document was dropped.
- A module uninstalled removed the document.

**Fix:** open the **Link to existing** dialog in the preview and re-pick the NPC. The agent will use the new UUID on the next refine or commit.

If this happens often, your CC compendium might not be the source of truth — check **Game Settings → Campaign Codex → Compendium Source**.

## Compendium search returned no results

**Symptoms:** the **thinking** stream shows the agent calling `compendium.search` and getting back `[]`. The draft then invents new items you know exist.

| Check | Fix |
| --- | --- |
| Is the right pack enabled? | **Game Settings → Campaign Codex → Compendiums**. The packs you want to search must be **Enabled** for CC, not just installed. |
| Is the world locked? | The search needs read access to the compendium. If the world is locked, the agent gets `compendium_search_failed`. |
| Right pack id? | The agent talks to the packs by their Foundry `metadata.id`, not their display name. Open **Settings → Manage Compendiums** to check. |

## Hot reload broke the WebSocket

**Symptoms:** after editing a file in the agent while running with `--reload`, the Foundry sidebar shows **Disconnected** and won't reconnect.

The reload tears down the WebSocket server. The Foundry client is still pointed at the (now-defunct) connection. **Fix:**

1. Wait for the agent log to show `listening on ws://127.0.0.1:7777/ws/v1` again.
2. Click the **Reconnect** button in the sidebar (or reload the Foundry tab).

If it still won't reconnect, restart the agent without `--reload` to rule out the watcher itself.

## Module not loading

**Symptoms:** the module doesn't show up in **Manage Modules**, or is listed but won't enable.

| Check | Fix |
| --- | --- |
| Foundry version | The module targets **v14.x**. Earlier versions don't have the data-model APIs the module uses. Check **Setup → Foundry VTT** in the bottom-left. |
| Manifest URL fetch failed | Try the **manifest** field in `module.json` directly. If it's a 404, the repo hasn't been pushed to `main` yet. |
| Console errors | **Setup → View Console** (F12). Look for red errors mentioning `fvtt-cc-generator`. |

## Logging locations

| Stream | Location |
| --- | --- |
| **Foundry VTT (browser)** | **Setup → View Console** (F12). For in-world errors, F12 while in the world. |
| **Foundry VTT (Node)** | `~/.local/share/FoundryVTT/Logs/` (Linux), `~/Library/Logs/FoundryVTT/` (macOS), `%APPDATA%\FoundryVTT\Logs\` (Windows). |
| **`fab-agent`** | stderr of the terminal running `uv run fab-agent`. Pipe to a file with `uv run fab-agent > ~/fab-agent.log 2>&1`. |

## Enabling debug logging

### Agent

```bash
# In .env
LOG_LEVEL=DEBUG
```

Or per-run:

```bash
LOG_LEVEL=DEBUG uv run fab-agent
```

DEBUG-level logs include:

- The full system prompt (length only, by default — set `LOG_PROMPTS=1` to dump it)
- Every LLM tool call
- Every WebSocket envelope id
- The full draft JSON after validation

### Foundry module

In **Game Settings → Configure Settings → FVTT-CCGenerator** there's a **Debug logging** checkbox. When on, the module logs every WebSocket envelope to the browser console with a `[fab]` prefix.

For deep debugging, the devMode module adds a "suspend on error" breakpoint and a per-module logger — see **[Development](./development.md)**.
