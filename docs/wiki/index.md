# FVTT-CC-Generator Wiki

Reference documentation for the FVTT-CC-Generator project — a Foundry VTT v14 module plus a local Python WebSocket agent that drafts Campaign Codex sheets with an LLM.

If you just want to install and start using the tool, jump to **[Install](./install.md)**.

## Contents

| Page | What it's for |
| --- | --- |
| [Install](./install.md) | Prerequisites, Foundry module install, agent install, token, verify |
| [Usage](./usage.md) | The AI Designer sidebar — workflow, tips, worked example |
| [Architecture](./architecture.md) | Module + agent design, the four skills, data flow, project layout |
| [Protocol](./protocol.md) | WebSocket envelopes, message types, events, errors |
| [Development](./development.md) | Dev setup, add a sheet type, add a skill, lint, release |
| [Troubleshooting](./troubleshooting.md) | Common issues and how to fix them |

## Get started

- New to the project? Read **[Install](./install.md)** first — it walks you from a fresh clone to a working "Connected" sidebar in six steps.
- Want to see the tool in action before installing? Read **[Usage](./usage.md)** — it has a worked example ("build a smuggler's tavern") you can follow once the agent is up.

## Use the tool

- **[Usage](./usage.md)** covers the AI Designer sidebar end-to-end: sheet types, prompts, the streaming preview, refinement, **Link to existing**, auto-commit, and prompt-crafting tips.

## Understand the system

- **[Architecture](./architecture.md)** is for developers and curious GMs. It explains why the agent is a separate process, what the four `SKILL.md` playbooks do, how the compendium-search-first guarantee works, and how a prompt becomes a committed journal page.
- **[Protocol](./protocol.md)** is the JSON-over-WebSocket contract between the Foundry module and `fab-agent`. Reference doc for anyone writing an alternative client or extending the message types.

## Extend

- **[Development](./development.md)** is the contributor guide. It covers project structure, dev setup, running the test suites, adding a new sheet type, adding a new skill, adding a new LLM provider via `litellm`, lint, hot reload, and the release process.

## Reference

- **[Protocol](./protocol.md)** — every message type, every event, every error code, with a full worked example of a design session.

## Help

- **[Troubleshooting](./install.md)** — wait, no: **[Troubleshooting](./troubleshooting.md)** — connection issues, LLM errors, schema validation failures, stale UUIDs, debug logging.
