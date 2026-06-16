---
name: campaign-codex-sheets
description: "Use when authoring Foundry VTT v14 Campaign Codex sheets — location, npc, region, shop, group, quest, tags sheet types; their flag-based field schemas, cross-reference syntax, the convertJournalToCCSheet API, and the openTOCSheet API. Load this when the agent needs to produce structured Campaign Codex input (rather than freeform HTML journals)."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [foundry, vtt, campaign-codex, sheets, journal, dnd5e, content-authoring]
    related_skills: [dnd5e-content-authoring, compendium-search-first, world-context-linking]
---

# Campaign Codex Sheets — Schema Reference

## Overview

**Campaign Codex** is a major Foundry VTT v14 module (v3.8.x) by wgtnGM that **extends the journal system** with bespoke sheet types, cross-references, and a Table of Contents (TOC) navigation. A "CC sheet" is *not* a different document — it's a `JournalEntry` whose `flags.campaign-codex` payload tells CC how to render it.

This skill is the schema reference. **Use it when generating content for any of the 6 typed sheets** (location, npc, region, shop, group, quest).

**Source of truth for schema:** Reverse-engineered from the live Campaign Codex module by inspecting generated sheets in the GUI. Verified against CC v3.8.1 (v14-compatible). If you see a new field, prefer the CC source over this skill.

## When to Use

- The agent is producing structured input for a CC sheet
- The user mentions "Campaign Codex", "CC sheet", or any of the 6 sheet types
- You need to choose between `convertJournalToCCSheet()` and writing flag data directly
- You're writing code that creates or modifies CC sheets programmatically

**Don't use for:** Generic `JournalEntry` content (no CC); module development for CC itself.

## Sheet Type Reference

All 6 sheet types share this base structure:

```json
{
  "_id": "abc123...",
  "name": "Display Name",
  "img": "path/to/image.webp",          // optional, falls back to CC type icon
  "folder": "FolderId",                  // optional
  "ownership": { "default": 0 },         // 0=none, 1=observer, 2=owner, 3=limited owner
  "flags": {
    "campaign-codex": {
      "sheetType": "location",           // REQUIRED — one of 6 types
      "type": "tavern",                  // subtype (e.g. "city", "dungeon", "tavern" for locations)
      "tags": ["coastal", "smuggler"],  // string[] — for cross-cutting filter
      "parentLocation": "Saltcliff - Dock Ward",  // string, name reference (resolved on commit)
      "linkedJournals": {                // bidirectional cross-refs
        "linkedLocationId": "uuid-1",
        "linkedNpcId": "uuid-2"
      },
      "custom": { /* system-specific or user fields */ }
    }
  },
  "pages": []  // page content (see Page Format below)
}
```

### 1. `location` Sheet

Represents a place in the world. Has the richest set of fields.

| Field | Type | Notes |
|-------|------|-------|
| `sheetType` | `"location"` | constant |
| `type` | string | One of: `settlement` (city/village/town), `structure` (tavern/castle/temple), `dungeon`, `wilderness`, `plane`, `region` (use region sheet for big areas), `other` |
| `tags` | string[] | Filter tags, e.g. `["coastal", "lawless"]` |
| `parentLocation` | string | Name of the containing location (e.g. for a tavern, the city it's in) |
| `description` | string | Short hook for the GM, 1-3 sentences |
| `denizens` | object[] | `{ name, role, linkToSheet?: bool }` — NPCs that live/work here |
| `linkedNpcs` | uuid[] | Forward links to NPC sheets |
| `linkedShops` | uuid[] | Forward links to shop sheets |
| `linkedQuests` | uuid[] | Quests that involve this location |
| `rumors` | string[] | 1-3 things NPCs might say about this place |
| `secrets` | string[] | GM-only knowledge, hidden by default |
| `tags` | string[] | Cross-cutting filter |

**Example: A smuggler's tavern**
```json
{
  "sheetType": "location",
  "name": "The Drowned Lantern",
  "type": "structure",
  "tags": ["tavern", "smuggler", "port", "lawless"],
  "parentLocation": "Saltcliff - Dock Ward",
  "description": "A low-beamed dockside tavern lit by bioluminescent jellyfish tanks. The owner lost a hand to the city guard and now runs a smuggling operation out of the cellar.",
  "denizens": [
    { "name": "Vaelen Kett", "role": "Innkeeper (smuggler)" },
    { "name": "Old Maren", "role": "Bouncer, ex-naval" }
  ],
  "rumors": [
    "They say the lanterns in the cellar never go out, even when you snuff them.",
    "Vaelen pays the guard captain in gold, not coin."
  ],
  "secrets": [
    "The cellar connects to a sea cave via an old smuggler's tunnel."
  ]
}
```

### 2. `npc` Sheet

A named character — could be a major NPC, a quest-giver, a shopkeeper, a villain.

| Field | Type | Notes |
|-------|------|-------|
| `sheetType` | `"npc"` | constant |
| `type` | string | One of: `ally`, `neutral`, `enemy`, `patron`, `rival`, `boss`, `commoner` |
| `tags` | string[] | e.g. `["half-elf", "criminal", "Dock Ward"]` |
| `linkedLocation` | uuid | Where they primarily live/work |
| `description` | string | Short GM description, 1-3 sentences |
| `personality` | string | Visible traits, mannerisms |
| `motivation` | string | What they want |
| `secret` | string | GM-only hidden knowledge |
| `voice` | string | Speech pattern / accent notes (dnd5e-content-authoring skill covers this) |
| `linkedNpcs` | uuid[] | Relationships (allies, enemies, family) |
| `linkedQuests` | uuid[] | Quests this NPC gives or appears in |
| `actorUuid` | uuid | OPTIONAL — link to an existing `Actor` sheet (created via Foundry) |

**Example: The innkeeper with a past**
```json
{
  "sheetType": "npc",
  "name": "Vaelen Kett",
  "type": "neutral",
  "tags": ["half-elf", "criminal", "smuggler", "Saltcliff"],
  "description": "Sharp-featured half-elf, mid-40s, with a leather glove over the right hand that isn't there.",
  "personality": "Wry, watchful, fast with a joke but slower with trust. Remembers every drink he's poured.",
  "motivation": "To keep the Lantern running and her crew fed, and to never owe anyone a debt again.",
  "secret": "Vaelen is not her real name. She was once a lieutenant in the city's night-watch, dismissed after she refused an order to burn a smuggler's ship with crew still aboard.",
  "voice": "Slight coastal drawl, drops articles ('seen the tide come in, I have'). Calls most patrons 'friend' or 'captain'."
}
```

### 3. `region` Sheet

A large area — a country, a biome, a city's district. A region contains locations.

| Field | Type | Notes |
|-------|------|-------|
| `sheetType` | `"region"` | constant |
| `type` | string | One of: `kingdom`, `province`, `city`, `district`, `biome` (forest/swamp/etc.), `plane` |
| `tags` | string[] | e.g. `["coastal", "lawless"]` |
| `parentLocation` | uuid | Containing region (provinces → kingdom, districts → city) |
| `description` | string | Overview of the region |
| `linkedLocations` | uuid[] | Locations within this region |
| `linkedNpcs` | uuid[] | NPCs of regional significance |
| `linkedQuests` | uuid[] | Regional-scale quests |

### 4. `shop` Sheet

A merchant's inventory and shop rules.

| Field | Type | Notes |
|-------|------|-------|
| `sheetType` | `"shop"` | constant |
| `type` | string | One of: `general`, `weapons`, `armor`, `magic`, `alchemy`, `tavern`, `black-market`, `other` |
| `tags` | string[] | e.g. `["Saltcliff", "black-market"]` |
| `linkedLocation` | uuid | Where the shop is |
| `linkedNpc` | uuid | Shopkeeper |
| `description` | string | Hook + general stock |
| `inventory` | object[] | `{ name, qty, price, currency, linkToCompendium: true }` — see `compendium-search-first` skill |
| `specialItems` | object[] | `{ name, description, price, linkToCompendium: true }` — magic/unique items |
| `buyMultiplier`, `sellMultiplier` | number | Price modifiers (default 1.0) |
| `tags` | string[] | |

**CRITICAL: Inventory should reference compendium items by `linkToCompendium: true` and a `compendiumUuid` field. Don't invent new items when SRD items exist.** See `compendium-search-first` skill.

### 5. `group` Sheet

A faction, organization, or family.

| Field | Type | Notes |
|-------|------|-------|
| `sheetType` | `"group"` | constant |
| `type` | string | One of: `faction`, `family`, `organization`, `creed`, `other` |
| `tags` | string[] | |
| `description` | string | Overview |
| `goals` | string[] | What the group wants |
| `resources` | string[] | What they have (money, magic, influence) |
| `allies` | uuid[] | Linked groups |
| `enemies` | uuid[] | Linked groups |
| `linkedNpcs` | uuid[] | Member NPCs |
| `linkedLocations` | uuid[] | Places they control or frequent |

### 6. `quest` Sheet

A quest or adventure hook.

| Field | Type | Notes |
|-------|------|-------|
| `sheetType` | `"quest"` | constant |
| `type` | string | One of: `main`, `side`, `personal`, `rumor`, `faction` |
| `tags` | string[] | |
| `description` | string | The hook, in 1-3 sentences |
| `objectives` | object[] | `{ text, completed: bool, optional: bool }` |
| `rewards` | string[] | What the players get |
| `linkedNpcs` | uuid[] | Quest givers and targets |
| `linkedLocations` | uuid[] | Quest locations |
| `linkedItems` | uuid[] | Quest-related items |
| `parentQuest` | uuid | For chains (e.g., Act 1 → Act 2) |

## Page Format (JournalEntryPage)

Each CC sheet has a `pages` array. Pages are rich-text content for the sheet's body.

```json
{
  "pages": [
    {
      "name": "Overview",
      "type": "text",
      "text": {
        "content": "<h2>The Drowned Lantern</h2><p>...</p>",
        "format": 1
      }
    },
    {
      "name": "GM Notes",
      "type": "text",
      "text": { "content": "<p>...</p>", "format": 1 },
      "ownership": { "default": 0 }    // GM-only
    }
  ]
}
```

**`format: 1` is HTML** (the default for v14 rich text). The agent should produce **clean HTML** — no inline styles, no `<script>`, semantic tags (`<h2>`, `<p>`, `<ul>`, `<strong>`, `<em>`).

**Cross-references inside HTML use the `@UUID[...]` syntax:**
```html
<p>Run by <a data-link="" data-uuid="Compendium.dnd5e.items.abc123">Vaelen Kett</a>.</p>
```

When the user already has a Vaelen Kett NPC sheet, the agent can link to it:
```html
<p>Run by @UUID[JournalEntry.uuid-of-vaelen]{Vaelen Kett}.</p>
```

The `[JournalEntry.uuid-of-vaelen]{display text}` form is the **v14 way** — it auto-resolves on render.

## Cross-Reference Resolution

The two ways to create a cross-ref:

**1. Flag-based (preferred for typed fields):**
```json
"linkedNpcs": ["JournalEntry.uuid-1", "JournalEntry.uuid-2"]
```
Stored as UUIDs, resolved by CC at render time.

**2. Inline in page content:**
```html
@UUID[JournalEntry.uuid-1]{Display Name}
```
Resolved by Foundry at render time (in the `text.content` HTML).

**Which to use:**
- **Typed/structured fields** (e.g., `linkedNpcs[]` in a quest) → flag-based
- **Inline mentions in prose** ("they met at the Lantern") → `@UUID`

The agent should be **consistent within a sheet**: don't mix and match the same kind of reference.

## The CC API (programmatic)

```js
// Get the API
const cc = game.modules.get('campaign-codex')?.api;

// Convert an existing JournalEntry into a CC sheet
await cc.convertJournalToCCSheet(uuid, sheetType, separatePages);

// Open the TOC at a specific tab
cc.openTOCSheet('locations');  // or 'npcs', 'regions', 'shops', 'groups', 'tags', 'quests'
```

**The `convertJournalToCCSheet` flow:**
1. Takes an existing `JournalEntry` (with HTML pages, each one a section)
2. Parses the pages
3. Creates a new CC sheet with the parsed content
4. The agent's output is a *plain* `JournalEntry` — CC does the conversion

**This is the safest path for the agent to take:** write a plain JournalEntry, then call `convertJournalToCCSheet`. The agent doesn't need to know the exact flag schema; CC handles it.

**However:** for structured fields (denizens, inventory, objectives, etc.), the flag-based path is better — `convertJournalToCCSheet` doesn't extract structured fields from prose. **Use flag-based for sheets with structure, `convertJournalToCCSheet` for prose-only pages.**

## Authoring Workflow (recommended)

For a sheet with **structured fields + a page body** (the common case):

```js
// 1. Create the JournalEntry with the structured flag payload
const je = await JournalEntry.create({
  name: draft.name,
  pages: [
    {
      name: "Overview",
      type: "text",
      text: { content: draft.description_html, format: 1 }
    }
  ],
  flags: {
    "campaign-codex": {
      sheetType: draft.sheetType,        // "location", "npc", etc.
      type: draft.subtype,                // "tavern", "ally", etc.
      tags: draft.tags,
      // ... all the other fields from the schema above
      denizens: draft.denizens,
      linkedNpcs: draft.linkedNpcs_uuids,
      // etc.
    }
  }
});

// 2. CC renders it as the right sheet type automatically (because of the flag)
```

For a sheet with **only prose** (no structured fields):

```js
// 1. Create a plain JournalEntry with rich text pages
const je = await JournalEntry.create({
  name: draft.name,
  pages: [/* text pages */]
});

// 2. Let CC convert it
await cc.convertJournalToCCSheet(je.uuid, draft.sheetType, false);
```

## Validation Rules (commit-time checks)

Before committing any CC sheet, verify:

1. **`sheetType` is one of: `location`, `npc`, `region`, `shop`, `group`, `quest`** — anything else silently fails to render
2. **`name` is non-empty**
3. **For typed fields:** every UUID in `linkedNpcs[]`, `linkedLocations[]`, etc. must resolve to an existing document
4. **Tags** are short strings, no commas in them (CC uses commas to delimit)
5. **HTML in `pages[].text.content`** is well-formed; no `<script>`, no `onclick=`, no inline event handlers
6. **Images** referenced in HTML exist (best-effort — CC won't fail on missing)

## Common Pitfalls

1. **Forgetting `format: 1`** on `text.content` — defaults to plain text and the HTML renders literally
2. **Inventing CC field names** — the schema is opinionated; an unknown field is silently ignored. Always use the documented field names.
3. **Using markdown instead of HTML** — CC pages are HTML, not markdown
4. **Linking to deleted documents** — the flag stores UUIDs; a stale UUID renders as a broken link
5. **Mixing sheet types** — a quest sheet should not contain `denizens[]` (that's location's field)
6. **Cross-references to compendia that don't exist in the world** — use SRD compendia that come with dnd5e (`dnd5e.items`, `dnd5e.monsters`)
7. **Not respecting the tags convention** — `["coastal", "lawless"]` is fine; `["coastal, lawless"]` is a single tag and breaks the filter
8. **Skipping `parentLocation`** — the LLM often forgets to set this. Locations should nest.

## Verification Checklist

- [ ] `sheetType` is valid
- [ ] All required fields are present
- [ ] All UUIDs in `linked*` arrays resolve to real documents
- [ ] `text.content` is well-formed HTML (no scripts, no inline handlers)
- [ ] `format: 1` set on text pages
- [ ] `tags` are simple strings, no commas
- [ ] For locations: `parentLocation` is set
- [ ] For shops: inventory uses `linkToCompendium: true` (see `compendium-search-first` skill)
- [ ] HTML mentions of NPCs/locations use `@UUID[...]` syntax where the agent knows the UUID

## Related Skills

- **`dnd5e-content-authoring`** — what to put in the structured fields (lore knowledge)
- **`compendium-search-first`** — for inventory/loot/actor references
- **`world-context-linking`** — how to query the existing world and link to existing sheets
