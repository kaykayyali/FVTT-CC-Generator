# Development

This is the contributor guide. It covers project layout, dev setup, the two test suites, how to extend the agent with a new sheet type or skill, lint, hot reload, and the release process.

## Project structure

See **[Architecture](./architecture.md)** for the full file-by-file walkthrough. The short version:

```
FVTT-CC-Generator/
├── foundry-module/   # the Foundry VTT v14 module
├── agent/            # the local Python WebSocket agent
├── docs/wiki/        # these docs
└── tests/quench/     # planned in-Foundry integration tests
```

The two halves are loosely coupled — the only contract is the WebSocket protocol in **[Protocol](./protocol.md)**. You can hack on either side independently.

## Dev environment

### Agent (Python)

Requires **Python 3.10+** and **[`uv`](https://docs.astral.sh/uv/)**.

```bash
cd agent
uv sync --all-extras        # --all-extras pulls pytest, ruff, mypy, etc.
cp .env.example .env
$EDITOR .env                # set LLM_API_KEY, LLM_MODEL
```

Run the agent in dev mode with auto-reload on file change:

```bash
uv run fab-agent --reload
```

`--reload` watches `src/fab_agent/**/*.py` and restarts the WebSocket server on change. Session state is dropped on reload.

### Foundry module (JS)

The module is plain JavaScript — no build step. For development:

1. Symlink `foundry-module/` into your Foundry `Data/modules/` directory.
2. Install the [devMode](https://foundryvtt.com/packages/dev-mode) module.
3. In Foundry, open **Game Settings → Configure Settings → Dev Mode** and enable **Hot Reload**.
4. With devMode on, editing a file in `foundry-module/scripts/` causes Foundry to re-evaluate it on the next browser refresh (Ctrl+R / Cmd+R).

The WebSocket side does **not** need a Foundry restart to pick up code changes — just a refresh.

## Running tests

### Agent — `pytest`

```bash
cd agent
uv run pytest                        # full suite
uv run pytest tests/test_handlers.py # one file
uv run pytest -k "refine"            # one keyword
```

The agent tests are in-process WebSocket tests. They spin up the server on an ephemeral port, connect a stub client, and assert the full `design.start` → `design.preview` envelope round-trip. LLM calls are mocked with `litellm`'s test fixtures — the test suite does not need an `LLM_API_KEY` to pass.

### Foundry — `quench` (planned)

`tests/quench/` will hold in-Foundry integration tests using [quench](https://github.com/schultzcole/FVTT-Quench). These run inside Foundry's own test runner and exercise the WebSocket client against a live `fab-agent`. Not yet written — see [issue tracker](https://github.com/kaykayyali/FVTT-CC-Generator/issues) for the milestone.

## Adding a new sheet type

Sheet types are the contract between the agent and the LLM. To add a new one (e.g. `event`):

1. **Add the enum value** in `agent/src/fab_agent/protocol.py`:
   ```python
   class SheetType(str, Enum):
       LOCATION = "location"
       NPC = "npc"
       REGION = "region"
       SHOP = "shop"
       GROUP = "group"
       QUEST = "quest"
       EVENT = "event"      # <-- new
   ```

2. **Define the schema** in `agent/src/fab_agent/validators.py` (or a sibling module). The validator is a JSON-schema dict keyed by `SheetType`. Re-use the Campaign Codex field-naming conventions.

3. **Add a JSON template** at `agent/src/fab_agent/templates/dnd5e/event.json`. The template is the empty starting point the validator checks drafts against.

4. **Document the sheet type** in the **`campaign-codex-sheets`** `SKILL.md`:
   ```markdown
   ### `event`
   Fields: name, date, location (@UUID), participants (NPC @UUID[]), summary.
   Tag convention: `event:<category>`.
   ```

5. **Mirror it on the Foundry side** in `foundry-module/scripts/lib/constants.js`:
   ```javascript
   export const SHEET_TYPES = ['location','npc','region','shop','group','quest','event'];
   ```

6. **Add a unit test** in `agent/tests/test_handlers.py` that posts a `design.start { sheetType: "event" }` and asserts a `design.preview` with a valid `event` draft.

7. **Update the docs**: add a row to the table in **[Usage](./usage.md)**.

## Adding a new skill

Skills are `SKILL.md` files under `agent/src/fab_agent/skills/<skill-name>/`. To add one (e.g. `darkvision-campaign-style`):

1. **Create the directory and file**:
   ```bash
   mkdir -p agent/src/fab_agent/skills/darkvision-campaign-style
   touch agent/src/fab_agent/skills/darkvision-campaign-style/SKILL.md
   ```

2. **Write the playbook**. The format is loose Markdown — the loader concatenates the raw text into the system prompt. A good skill has:
   - A one-paragraph mission statement.
   - A short list of "rules" (do / don't).
   - Two or three worked examples.
   - Anything else the LLM needs to do this well.

3. **No code change required** — `skills_loader.py` globs `skills/*/SKILL.md` at startup. Restart the agent to pick up the new skill.

4. **Verify it's loaded** — the agent logs `loading N skills` on startup. N should be 5 instead of 4.

5. **Update the docs** — the skills table in **[Architecture](./architecture.md)**.

## Adding a new LLM provider

`fab-agent` uses [`litellm`](https://github.com/BerriAI/litellm) for LLM calls. Adding a provider is a `.env` change, not a code change:

```toml
# Anthropic
LLM_MODEL=anthropic/claude-3-5-sonnet-latest
LLM_API_KEY=sk-ant-...

# OpenRouter
LLM_MODEL=openrouter/anthropic/claude-3.5-sonnet
LLM_API_KEY=sk-or-...
LLM_BASE_URL=https://openrouter.ai/api/v1

# Ollama (no key)
LLM_MODEL=ollama/llama3.1
LLM_BASE_URL=http://127.0.0.1:11434

# Azure OpenAI
LLM_MODEL=azure/<deployment>
LLM_API_KEY=...
LLM_BASE_URL=https://<resource>.openai.azure.com/
```

See [`litellm`'s provider docs](https://docs.litellm.ai/docs/providers) for the full list. Restart the agent to pick up the new `.env`.

## Linting

### Python — `ruff`

```bash
cd agent
uv run ruff check .
uv run ruff format .
```

CI runs `ruff check --strict` and `ruff format --check`. The repo has a `pyproject.toml` `[tool.ruff]` block — read it before adding ignores.

### JavaScript — `eslint`

```bash
cd foundry-module
npm install                  # first time only
npx eslint scripts/          # lint
npx eslint scripts/ --fix    # autofix
```

The repo ships an `.eslintrc.json` that extends `eslint:recommended` and a few airbnb-style rules. Pull requests that don't pass lint will be bounced.

## Hot reload

| Side | Mechanism | How |
| --- | --- | --- |
| **Agent (Python)** | `fab-agent --reload` watches `src/fab_agent/**/*.py` and restarts. | `uv run fab-agent --reload` |
| **Foundry (JS)** | The `devMode` module + browser refresh. | Install devMode, enable **Hot Reload**, edit a file, refresh. |

If a hot reload breaks the WebSocket, see **[Troubleshooting](./troubleshooting.md#hot-reload-broke-the-websocket)**.

## Publishing releases

We publish a single zip per release that contains both halves — `fvtt-cc-generator-<version>.zip`. The Foundry manifest inside the zip points at the **unzipped** path. Operators unzip into `Data/modules/fvtt-cc-generator/` and run `agent/` separately.

The release script (`scripts/release.sh`) is not yet written; the manual process is:

```bash
# 1. Tag the release
git tag v0.1.0
git push --tags

# 2. Build the zip
./scripts/build-release.sh v0.1.0
# → dist/fvtt-cc-generator-0.1.0.zip

# 3. Draft a GitHub release with the zip attached.
#    Update the module.json "version", "download", "manifest" fields if needed.
```

The Foundry module's `module.json` `manifest` and `download` URLs point at the GitHub release of the matching tag.

## Contributing guidelines

- **Open an issue first** for anything beyond a typo. The protocol and the skill playbooks are easy to break from the outside; an issue lets us align on the design before you write code.
- **One PR per change.** Sheet-type additions, skill additions, and protocol changes should each be their own PR.
- **Tests for behaviour, not implementation.** A new sheet type should ship with a `pytest` case that drives it through the WebSocket. UI-only changes need a manual test note in the PR description.
- **Don't break the protocol.** Any change to the message types in **[Protocol](./protocol.md)** is a breaking change and needs a `v2` plan, not a silent edit.
- **Lint clean.** `ruff check` and `eslint` must pass.
- **Update the docs.** Wiki pages are checked into `docs/wiki/`. If you change a skill, update the skills table in `architecture.md`. If you add a sheet type, update `usage.md`.

PRs that ignore the above will be politely bounced.
