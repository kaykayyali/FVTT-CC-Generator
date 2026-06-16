# Usage

The **AI Designer** is a sidebar tab in Foundry. It is the only surface you normally interact with — the agent and the LLM are invisible plumbing behind it.

## The sidebar

The sidebar is split into three regions, top to bottom:

| Region | What it does |
| --- | --- |
| **Header** | Connection status pill (**Connected** / **Disconnected**), sheet-type selector, **Settings** gear (opens module settings). |
| **Composer** | A multi-line prompt box. Type the world content you want; pick the sheet type; click **Design**. |
| **Preview** | A streaming preview pane. Shows the **thinking** indicator, then the draft sheet, then **Refine** / **Link to existing** / **Commit** controls. |

The sidebar is modeless — you can keep editing your world, move tokens, open journals, and the agent keeps working in the background.

## Workflow

The end-to-end flow is eight steps. Most sessions use only the first six.

### 1. Pick a sheet type

The dropdown in the header. Choices map directly to Campaign Codex sheet types:

| Sheet type | Generates |
| --- | --- |
| `location` | A CC Location sheet (description, tags, parent region). |
| `npc` | A CC NPC sheet (description, role, location, tags) plus a dnd5e Actor stub. |
| `region` | A CC Region sheet (overview, settlements, parent). |
| `shop` | A CC Shop sheet (inventory, proprietor, parent location) — generated NPC for the proprietor if not linked. |
| `group` | A CC Group / Faction sheet (goals, members, leader). |
| `quest` | A CC Quest sheet (summary, objectives, reward, giver). |

### 2. Write a prompt

One to four sentences. Name the place, the mood, the hook. See [Tips for good prompts](#tips-for-good-prompts) below.

### 3. Click **Design**

The Foundry module opens (or reuses) a WebSocket to `fab-agent` and sends a `design.start` envelope. The sidebar swaps the composer for a **thinking** indicator.

### 4. Watch the thinking indicator stream

`fab-agent` streams the LLM's reasoning text as `design.thinking` events. You see what the model is considering in near-real-time. **You can cancel** with the **Stop** button — the partial draft is discarded.

### 5. Review the preview pane

When the LLM returns a complete JSON draft, the agent validates it against the CC schema and pushes a `design.preview` event. The sidebar renders the sheet in a read-only preview. Tags, links, and structure are highlighted.

### 6. Refine (optional)

Type a follow-up into the **Refine** box at the bottom of the preview and click **Refine**. The agent runs another LLM pass seeded with the previous draft + your instruction. Repeat as needed. The full history is kept on the client so the agent can see what you've already changed.

### 7. Link to existing (optional)

Click **Link to existing** to open a CC-aware search. You can attach the new sheet to:

- a parent **region** or **location** (for `location` / `shop` / `npc`)
- a **group** the NPC belongs to (for `npc`)
- a **quest giver** NPC (for `quest`)

Linked sheets are stored as CC `parentId` / `@UUID` references — the same format the rest of Campaign Codex uses. UUIDs are validated against the world before commit.

### 8. Commit

Click **Commit**. The module writes:

- a new **Journal Entry** (the CC sheet itself)
- any linked dnd5e **Actor** / **Item** documents the draft referenced
- CC TOC entries (the campaign-codex compendium flags)
- `parentId` links to the sheets you attached in step 7

If **Auto-commit** is on (see below), steps 6-8 collapse into a single click.

## Auto-commit mode

Toggle in **Game Settings → Configure Settings → FVTT-CC-Generator → Auto-commit drafts**.

- **Off (default).** You always review the preview before it's written. Safer for one-shots and for prompts you're still learning.
- **On.** Every successful preview is committed immediately. Use this when you trust the LLM and the model, or when you're generating many small sheets in a row.

You can still hit **Refine** before commit even in auto-commit mode — auto-commit only fires when a *new* draft is produced, not on a refine.

## The "Link to existing" feature

Linking matters because Campaign Codex's value comes from the **graph** of relationships between your sheets, not the individual entries. A tavern with no parent region and no proprietor NPC is just a wall of text.

When you click **Link to existing**, the sidebar opens a small CC search dialog:

1. Type a few letters of the sheet you want to link to.
2. Pick from the results (these come from your world's CC TOC, not the LLM).
3. The link is added to the draft as a `@UUID` reference. The agent will reuse this exact UUID — not generate a new one.

If you want to skip the dialog and just type the name, mention it in your prompt (e.g. *"the tavern in Saltmarsh district"*) — the agent will try to resolve it, but the **Link to existing** UI is more reliable because it doesn't depend on the LLM picking the right UUID.

## Worked example — "Build a smuggler's tavern"

1. Open **AI Designer** in the sidebar. Pick sheet type **`location`**.
2. Type the prompt:

   ```
   The Rusted Anchor — a dockside tavern in the worst part of Saltmarsh,
   fronted as a sailor dive but with a hidden basement used by a smuggling
   ring. Owner is a one-eyed half-elf who retired from the city's own coast
   guard. Patrons are dockworkers and a few unsavory regulars.
   ```

3. Click **Design**. You see the **thinking** indicator stream for ~5-10 seconds.
4. Preview appears. It includes:
   - a one-paragraph description of the tavern
   - a short list of "frequent patrons" (placeholder NPCs, not yet committed)
   - a tag set (`tavern`, `smuggling`, `saltmarsh`, `dockside`)
   - a suggested parent region (`Saltmarsh`)
5. Click **Link to existing**, search for `Saltmarsh`, and pick the region journal.
6. Click **Refine**, type: *"add a rumor table and a hidden cellar entry description"*. The next preview includes both.
7. Click **Commit**. The location journal is created, the link to the Saltmarsh region is set, and (if you have dnd5e items with `tavern` or `inn` tags in your compendia) the agent will surface them as **Reuse suggestions** before commit.

Total time: under a minute, fully edited, properly linked into the CC TOC.

## Tips for good prompts

The agent works best with prompts that include:

- **A name.** Even a working name. *"The Rusted Anchor"* beats *"a tavern"*.
- **A setting anchor.** A city, a region, a faction. Lets the agent search the right compendium.
- **Two or three concrete details.** *"one-eyed half-elf ex-coast-guard"*, *"hidden basement"*, *"rumor table"*.
- **The mood or tone.** *"unsavory"*, *"lively"*, *"haunted"*, *"polite but watchful"*.

What to avoid:

- **Vague open-ended prompts.** *"Make me a cool NPC"* — the agent will ask you to be specific, or guess badly.
- **Long blocks of lore.** The agent is a drafter, not a transcriber. A two-sentence summary beats a ten-paragraph setting bible.
- **System-internal instructions.** *"Output JSON with the field name…"* — the agent already knows the schema from the `SKILL.md` playbooks.

## Common sheet types and what they generate

| Sheet | Documents written to the world | Compendia searched |
| --- | --- | --- |
| `location` | 1× JournalEntry (CC location page) | dnd5e items with `location` tag, `Actor`s tagged with the region |
| `npc` | 1× JournalEntry (CC NPC page) + 1× Actor (dnd5e NPC) | dnd5e monsters & NPCs, races, classes |
| `region` | 1× JournalEntry (CC region page) | dnd5e items with `region` tag |
| `shop` | 1× JournalEntry (CC shop page) + 1× Actor (proprietor NPC) + 0..N× Item (inventory) | dnd5e items, equipment, magic items |
| `group` | 1× JournalEntry (CC faction page) | dnd5e items with `faction` tag |
| `quest` | 1× JournalEntry (CC quest page) | dnd5e items, spells (for rewards) |

If the search-first guarantee kicks in, the **Reuse suggestions** panel in the preview shows the existing compendium entries the agent would link to instead of inventing new ones.
