# Architecture

This page is for developers and the merely curious. It covers the moving parts, the data flow, the four `SKILL.md` playbooks, and a file-by-file walkthrough of the project.

## High-level diagram

```
                          +-----------------------------+
                          |  Foundry VTT v14 (browser)  |
                          |                             |
                          |  +-----------------------+  |
                          |  | FVTT-CC-Generator     |  |
                          |  |  scripts/main.js      |  |
                          |  |  sheets/designer.js   |  |
                          |  |  lib/ws-client.js     |  |
                          |  |  lib/commit.js        |  |
                          |  +----------+------------+  |
                          +-------------|---------------+
                                        |
                                ws://127.0.0.1:7777/ws/v1
                                Sec-WebSocket-Protocol: fab.v1.token=…
                                        |
                          +-------------v---------------+
                          |  fab-agent  (Python)        |
                          |                             |
                          |  +-----------------------+  |
                          |  | server.py  (FastAPI / |  |
                          |  |   websockets)         |  |
                          |  +----------+------------+  |
                          |             |               |
                          |  +----------v------------+   |
                          |  | handlers.py           |  |
                          |  | validators.py         |  |
                          |  | prompts.py            |  |
                          |  | skills_loader.py      |  |
                          |  +----------+------------+  |
                          |             |               |
                          |  +----------v------------+   |
                          |  | llm.py  (litellm)     |  |
                          |  +----------+------------+  |
                          +------|------|------|----+
                                 |      |      |
                            +----v+ +---v---+ +v----+
                            | LLM | | 4 x  | |open()|
                            | API | |SKILL | |comp  |
                            +-----+ +------+ +------+
                                                |
                          +---------------------v--------+
                          | Foundry compendia (read-only) |
                          |   read by fab-agent at draft  |
                          |   time to find reusable items |
                          +------------------------------+
```

Three trust boundaries:

- The **browser** runs the Foundry module. It owns the UI, the WebSocket, and all writes to the world.
- **`fab-agent`** runs locally. It is the only process that talks to the LLM and the only process that reads compendia at draft time.
- The **LLM provider** is opaque. It is treated as an untrusted string-generator wrapped by a JSON schema.

## The four skills

`fab-agent` loads four `SKILL.md` files at startup and concatenates their contents into the system prompt. Each is a small playbook — half rules, half examples — that steers the LLM.

| Skill | Purpose |
| --- | --- |
| **campaign-codex-sheets** | The shape of every CC sheet (location, npc, region, shop, group, quest). Field names, parent links, tag conventions. |
| **dnd5e-content-authoring** | How to express things in dnd5e terms: races, classes, CR, AC, ability scores, damage types, item rarities. |
| **compendium-search-first** | **The contract.** Before inventing a new actor or item, the LLM must call the compendium search tool and prefer an existing UUID. No duplicate SRD goblins. |
| **world-context-linking** | How to attach new sheets to existing regions, factions, and NPCs using `@UUID` references. |

Adding a fifth skill is a `mkdir` + a `SKILL.md` — see **[Development](./development.md)**.

## Data flow — from prompt to committed journal

```
 user types prompt
        │
        v
 [designer.js]  ── ws.send( design.start { sheetType, prompt, links[] } ) ──▶  [server.py]
                                                                                     │
                                                                       [handlers.py]  load session
                                                                                     │
                                                                       [prompts.py]   build system prompt
                                                                                          │
                                                                       4 × SKILL.md + world context  ──▶  system
                                                                       user prompt + sheet type       ──▶  user
                                                                                     │
                                                                       [llm.py]  call litellm
                                                                                     │
                                                                       raw text   ◀──  LLM
                                                                                     │
                                                                       [validators.py]  parse + JSON-schema check
                                                                                          │
                                                                       draft       ◀──  ok / error
                                                                                     │
 ws.send( design.preview { draft, reuse[] } )  ◀──────────────────────────────────────┘
        │
        v
 [designer.js] renders preview, user reviews
        │
 user clicks Refine  ── ws.send( design.refine { instruction } ) ──▶   (loops at LLM step)
        │
 user clicks Commit  ── ws.send( design.commit { acceptedDraft } )  ──▶  [commit.js]  writes JournalEntry + Actor + Items
                                                                                     │
                                                                       opens compendium, sets CC flags, sets parentId
                                                                                     │
 ws.send( design.committed { uuid } )  ◀─────────────────────────────────────────────┘
```

All streamed events (`design.thinking`, `design.preview`, `design.committed`, `design.error`) share one envelope — see **[Protocol](./protocol.md)**.

## Why a separate agent process?

We considered running the LLM call inside the Foundry module itself. The decision to split was deliberate.

- **Security.** The LLM API key never has to live in a process the browser can inspect. `fab-agent` is a normal local process; the module never sees the key.
- **Latency.** Foundry's main thread is on the critical path for every dice roll and every render. A long LLM call (10-30s) would freeze the UI. A WebSocket keeps the heavy work off-thread.
- **Cost / provider flexibility.** The LLM story in Foundry v14 is still nascent. By keeping the LLM behind `litellm`, swapping OpenAI for Anthropic or Ollama is a `.env` change — no module rebuild, no Foundry restart.
- **Operability.** The agent has its own log stream, can be run in a terminal, in a `nohup`, in `tmux`, or eventually in Docker. It's the standard Python process model.
- **Hermes compatibility.** The original prototype used Hermes Agent to load the `SKILL.md` files. The v1 agent reproduces that *contract* in plain Python, so a future version can delegate back to Hermes without changing the Foundry side or the protocol.

The trade-off: the user has to run two things instead of one. `uv run fab-agent` is the entire cost.

## The compendium-search-first guarantee

This is the single most important behavioural claim in the project. A GM using the AI Designer should never end up with a **second** SRD goblin because the LLM invented a new one.

The guarantee is enforced by the **compendium-search-first** `SKILL.md` plus the **search tool** the agent exposes to the LLM:

1. The system prompt instructs the LLM: *"Before writing any actor or item UUID, call `compendium.search` with the relevant terms. If a result matches, use its UUID. Only invent a new document if no match is found and explain why in the draft notes."*
2. The LLM emits a `compendium.search` tool call. The agent executes it against the user's actual compendia at draft time.
3. The LLM sees the results, picks the best match (or declines with a reason), and only then writes the draft JSON.
4. The draft is validated. If the LLM claimed a UUID that doesn't exist in the world, validation fails and the user sees a **Reuse suggestions** panel in the preview listing the closest compendium matches.

This means the agent has to be able to **read the user's compendia** at draft time. The agent does not write to them — only the Foundry module does — but it does open them via the standard Foundry API. The `fab-agent` therefore ships with a read-only compendium client; the trust boundary is "the agent can read, only the module can write".

## Project structure

```
FVTT-CC-Generator/
├── README.md                        # landing page
├── foundry-module/                  # Foundry VTT v14 module
│   ├── module.json                  # manifest, manifest URL anchor
│   ├── scripts/
│   │   ├── main.js                  # module entry, registers settings, sidebar tab
│   │   ├── sheets/
│   │   │   └── designer.js          # the AI Designer sidebar Application
│   │   └── lib/
│   │       ├── constants.js         # WS path, message types, default token
│   │       ├── settings.js          # registerSettings() — agentHost, agentPort, agentToken, autoCommit
│   │       ├── ws-client.js         # the WebSocket client; reconnect; envelope codec
│   │       ├── world-context.js     # reads compendia, journals, CC TOC; builds the world context blob
│   │       └── commit.js            # the commit step: writes JournalEntry / Actor / Item, sets CC flags
│   ├── templates/
│   │   └── designer.hbs             # Handlebars template for the sidebar
│   ├── lang/en.json                 # i18n strings
│   ├── styles/fab.css               # sidebar styling
│   └── assets/                      # icons
│
├── agent/                           # the local Python WebSocket agent
│   ├── pyproject.toml               # uv project, console-script entry point
│   ├── README.md                    # agent-specific readme
│   ├── .env.example                 # template for the user’s .env
│   ├── src/fab_agent/
│   │   ├── __init__.py
│   │   ├── __main__.py              # `python -m fab_agent` entry
│   │   ├── cli.py                   # argparse; `fab-agent` console script
│   │   ├── config.py                # pydantic settings, reads .env
│   │   ├── server.py                # FastAPI / websockets server, /ws/v1 route
│   │   ├── protocol.py              # envelope, message types, validation
│   │   ├── handlers.py              # design.start / refine / commit dispatch
│   │   ├── validators.py            # JSON-schema checks, CC sheet schema
│   │   ├── llm.py                   # litellm wrapper, streaming, retries
│   │   ├── prompts.py               # system-prompt assembly, world context injection
│   │   ├── skills_loader.py         # reads SKILL.md, splits into the four playbooks
│   │   ├── skills/                  # <-- the four playbooks
│   │   │   ├── campaign-codex-sheets/SKILL.md
│   │   │   ├── dnd5e-content-authoring/SKILL.md
│   │   │   ├── compendium-search-first/SKILL.md
│   │   │   └── world-context-linking/SKILL.md
│   │   └── templates/dnd5e/         # JSON templates for dnd5e Actor / Item / JournalPage
│   │       ├── actor.json
│   │       ├── item.json
│   │       └── journal-page.json
│   └── tests/                       # pytest, in-process WebSocket tests
│
├── docs/
│   └── wiki/                        # GitHub Pages wiki (these docs)
│       ├── index.md
│       ├── install.md
│       ├── usage.md
│       ├── architecture.md          # this file
│       ├── protocol.md
│       ├── development.md
│       └── troubleshooting.md
│
└── tests/
    └── quench/                      # in-Foundry integration tests (planned)
```

### Where to start reading

- **The protocol first** if you want to understand the contract. See **[Protocol](./protocol.md)**.
- **`agent/src/fab_agent/server.py`** is the shortest path through the agent. One file, ~150 lines, all the routing is obvious.
- **`foundry-module/scripts/lib/ws-client.js`** is the equivalent on the module side.
- **`agent/src/fab_agent/skills/`** is where the *behaviour* lives. Read all four `SKILL.md` files end-to-end — they're short and they're the source of truth for what the LLM is told to do.
