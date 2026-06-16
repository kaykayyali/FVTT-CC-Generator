---
name: world-context-linking
description: "Use when the agent needs to read or link to a Foundry VTT v14 user's existing world content — finding existing Campaign Codex sheets, NPCs, locations, parent regions, and quests; avoiding name collisions; emitting @UUID cross-references in HTML page content. Load this whenever the agent generates content that should integrate with (not duplicate) the world's existing data."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [foundry, vtt, world, journal, npc, location, link, uuid, context, search]
    related_skills: [campaign-codex-sheets, dnd5e-content-authoring, compendium-search-first]
---

# World Context & Linking

## Overview

The user's Foundry VTT world is a **living database**, not a blank canvas. By the time the agent is asked to "create a tavern" or "generate an NPC", the world may already contain hundreds of `JournalEntry` documents, `Actor` documents, `Scene` documents, and especially `Campaign Codex` sheets wired into a graph of cross-references.

This skill teaches the agent to **read the world first, link to what exists, and only create new documents when nothing similar is present**. Compendium searching is a different problem (covered by `compendium-search-first`); this skill is about the *world* — the GM's own data.

The agent runs inside Foundry's browser/macro context with full access to the `game` global, including `game.journal`, `game.actors`, `game.scenes`, `game.items`, `fromUuid()`, and document flags. All code in this skill is intended to execute in that context (Foundry macro, API console, or FVTT-CC-Generator agent runtime).

## When to Use

Load this skill whenever the agent is about to **create** any of the following:

- A new NPC sheet (CC `npc` or a raw `Actor` of type `npc`)
- A new location sheet (CC `location`, `region`, `shop`, `dungeon`, `structure`)
- A new quest sheet (CC `quest`) or a quest that references existing NPCs/locations
- A new group/faction sheet (CC `group`)
- A new region, sub-region, or district that should sit *inside* an existing one
- Any page content that mentions a person, place, faction, or quest already known to the world

**Do not use** for:
- Queries against D&D SRD compendia → use `compendium-search-first`
- Pure 5e mechanics/statblock authoring → use `dnd5e-content-authoring`
- CC flag schema and field shapes → use `campaign-codex-sheets`

## The Rule

> **The user's world is the source of truth. Before creating any NPC, location, or quest, search the world. Link to existing content. Only create new when nothing similar exists.**

Concretely, the agent must:

1. **Search** `game.journal` and `game.actors` for the proposed name and close variants.
2. **Read** the `flags['campaign-codex']` payload to see if matches are CC sheets and what type they are.
3. **Decide**: *reuse* (link), *extend* (add a page / new field on an existing doc), or *create* (new doc only if nothing fits).
4. **Link** every cross-reference in new content with `@UUID[...]` syntax. Never leave a known name as plain text.

If the agent skips step 1, it will *duplicate* the world. If the agent skips step 4, the new content will be *orphaned* from the world's link graph.

## Querying the World (JS workflow)

The agent executes JavaScript in Foundry's browser context. The `game` global exposes the full document collections.

### Get all journals

```js
// Two equivalent forms
const allJournals = game.journal.contents;        // array
const alsoAll     = Array.from(game.journal);    // array
```

`game.journal` is a `Collection` (a `Map`-like), so `.contents` is the canonical way to get a real `Array`.

### Get all actors (filtering for NPCs)

```js
const allActors  = game.actors.contents;
const npcs       = game.actors.filter(a => a.type === 'npc');
const pcs        = game.actors.filter(a => a.type === 'character');
```

### Filter by name (case-insensitive, partial)

```js
// Substring match — robust to "Captain Voss" vs "captain voss" vs "Capt. Voss"
const matches = game.journal.filter(j =>
  j.name?.toLowerCase().includes('dragon')
);

// Whole-word prefix match
const captains = game.actors.filter(a =>
  /^captain\s/i.test(a.name)
);

// Exact (case-insensitive) match
const exact = game.journal.find(j =>
  j.name?.toLowerCase() === 'saltcliff'
);
```

### Read a document's UUID

Every Foundry document has a `uuid` property — the canonical handle for cross-references.

```js
const doc  = game.journal.getName('Vaelen Kett');
const uuid = doc.uuid;            // e.g. "JournalEntry.abc123XYZ"
const type = doc.documentName;    // "JournalEntry"
```

The world-side format is always `DocumentName.<id>`. The ID is the document's `_id` field.

### Read a document's CC sheet type

CC sheets are regular `JournalEntry` documents with a flag payload. The presence of `sheetType` is the marker.

```js
const ccType = doc.flags?.['campaign-codex']?.sheetType;
// Possible values: 'location' | 'npc' | 'region' | 'shop' | 'group' | 'quest' | undefined
```

A document with no `flags['campaign-codex']` is a *raw* journal — not a CC sheet.

### Read a document's CC tags

```js
const tags = doc.flags?.['campaign-codex']?.tags ?? [];
// e.g. ["coastal", "smuggler", "lawless"]
```

Tags are how CC does faceted filtering. Use them for cross-cutting searches ("show me all coastal NPCs").

### Use `fromUuid(uuid)` to resolve a UUID

`fromUuid()` is the universal resolver. It accepts:

- World UUIDs: `JournalEntry.abc123`
- Compendium UUIDs: `Compendium.<pack>.<id>`
- Scene/token embedded UUIDs: `Scene.<id>.Token.<id>`

```js
const doc = await fromUuid('JournalEntry.abc123');
console.log(doc.name, doc.flags?.['campaign-codex']?.sheetType);
```

It returns a `Promise<Document | null>`. Always `await`. It is **not** synchronous in v14.

### Check linked journals on a CC page

CC structured fields store cross-refs as UUIDs (in `linkedJournals`, `linkedNpcs`, `linkedShops`, `linkedQuests`, `denizens` (by `linkToSheet`)).

```js
const npc = game.journal.getName('Vaelen Kett');
const linkedNpcUuids = npc.flags?.['campaign-codex']?.linkedNpcs ?? [];
// Resolve each
const linkedNpcs = await Promise.all(linkedNpcUuids.map(uuid => fromUuid(uuid)));
```

The `linkedJournals` flag is the older, more general cross-ref bucket. Prefer the typed fields (`linkedNpcs`, `linkedShops`, `linkedQuests`) when present.

## Detecting Campaign Codex Sheets

A "CC sheet" is *any* `JournalEntry` whose `flags['campaign-codex']` payload exists. There is no separate document type — CC is a flag schema layered on top of vanilla journals.

```js
// 1. All CC sheets, regardless of type
const ccSheets = game.journal.filter(j => j.flags['campaign-codex']?.sheetType);

// 2. Narrow to a type
const locations = ccSheets.filter(j => j.flags['campaign-codex'].sheetType === 'location');
const npcs      = ccSheets.filter(j => j.flags['campaign-codex'].sheetType === 'npc');
const regions   = ccSheets.filter(j => j.flags['campaign-codex'].sheetType === 'region');
const shops     = ccSheets.filter(j => j.flags['campaign-codex'].sheetType === 'shop');
const groups    = ccSheets.filter(j => j.flags['campaign-codex'].sheetType === 'group');
const quests    = ccSheets.filter(j => j.flags['campaign-codex'].sheetType === 'quest');
```

### One-liner index (recommended for large worlds)

Build a type-keyed index once, then look up by type in O(1) per doc.

```js
const ccIndex = game.journal.contents.reduce((acc, j) => {
  const t = j.flags?.['campaign-codex']?.sheetType;
  if (t) (acc[t] ??= []).push(j);
  return acc;
}, {});

// Lookup
const allNpcs = ccIndex.npc ?? [];
const npcByName = new Map(allNpcs.map(n => [n.name.toLowerCase(), n]));
```

### Type-aware tag search

```js
const coastalNpcs = (ccIndex.npc ?? []).filter(n =>
  (n.flags['campaign-codex'].tags ?? []).includes('coastal')
);
```

## Avoiding Name Collisions

Name collisions are the #1 way an agent pollutes a world. A user with 200 NPCs does not want a second "Captain Voss" — they want the existing one referenced.

### The search-then-decide pattern

```js
// 1. Search both journals and actors (NPCs may live in either)
function findExisting(name) {
  const q = name.toLowerCase();
  const journalHits = game.journal.filter(j => j.name?.toLowerCase().includes(q));
  const actorHits   = game.actors.filter(a => a.name?.toLowerCase().includes(q));
  return { journalHits, actorHits };
}

const { journalHits, actorHits } = findExisting('Captain Voss');
if (journalHits.length || actorHits.length) {
  // Match found — see decision rule below
}
```

### The merge-vs-new decision rule

Given a proposed new entity and a set of existing matches, decide as follows:

| Situation | Action |
|-----------|--------|
| Exact name match (case-insensitive) in journals or actors | **Reuse**. Link to the existing doc; do not create. |
| Partial match on a *minor* variant (e.g. "Captain Voss II", "Captain Voss the Younger") | **Reuse the canonical**. The variants are noise — link to the existing "Captain Voss". |
| Partial match on a *semantically distinct* entity (e.g. "Captain Voss" the smuggler vs. "Captain Voss" the city guard) | **Disambiguate with the user** before creating. Do not silently create a second one. |
| Substring match on a *different* canonical entity (e.g. searching "Voss" returns "Voss Tower" the location) | **Reuse if relevant**; otherwise treat as no match. |
| No match | **Create**, but only after running the disambiguation pass. |

### Variants to reject outright

Do **not** generate names like:

- `<Name> II`, `<Name> Jr.`, `<Name> the Younger`
- `<Name>'s Daughter`, `<Name>'s Apprentice`
- `<Name> (variant)`, `<Name> (clone)`
- Renamed copies of a known canon NPC (e.g. "Elminster the Lesser")

If the world already has the canonical, the variant is a duplicate. Either reuse the canonical or rename the new entity to something genuinely different (and then check *that* name too).

## Emitting @UUID Cross-References

When the agent mentions a person, place, faction, or quest that already exists in the world, the page HTML must use Foundry's `@UUID` link syntax. Plain-text names break the link graph.

### The @UUID syntax

```
@UUID[<document-uuid>]{<display text>}
```

Examples:

```html
<!-- Person -->
<a>@UUID[JournalEntry.uuid-of-vaelen]{Vaelen Kett}</a>

<!-- Location -->
<a>@UUID[JournalEntry.uuid-of-saltcliff]{Saltcliff}</a>

<!-- Quest -->
<a>@UUID[JournalEntry.uuid-of-quest-rats]{The Rat Catcher}</a>

<!-- Compendium (dnd5e monster) -->
<a>@UUID[Compendium.dnd5e.monsters.Item.Demon.glasya]{Glasya}</a>
```

When rendered in Foundry, these become clickable links that open the target document.

### The linkify helper (JS)

When generating page content, sweep every named entity and convert it to an `@UUID` link if a match exists in the world.

```js
// Build a name -> doc map once per generation
const nameIndex = new Map();
for (const j of game.journal) {
  if (j.name) nameIndex.set(j.name.toLowerCase(), j);
}
for (const a of game.actors) {
  if (a.name) nameIndex.set(a.name.toLowerCase(), a);
}

const linkifyName = (name) => {
  const existing = nameIndex.get(name.toLowerCase());
  if (existing) {
    return `@UUID[${existing.uuid}]{${name}}`;
  }
  return name;  // leave as plain text if no match
};

// Use it on a body of text
const html = body.replace(/\[name:([^\]]+)\]/g, (_, n) => linkifyName(n));
```

### Conversions between formats

```js
// Inline link in JSX/HTML output
const link = `@UUID[${doc.uuid}]{${doc.name}}`;

// Inline link in a markdown-ish context where @UUID is allowed by Foundry
const text = `The party met ${doc.name} in the ${parent.name}.`;
// → "The party met @UUID[JournalEntry.x]{Vaelen Kett} in the @UUID[JournalEntry.y]{Saltcliff}."
```

### Resolving @UUID links at write time

If the new content *receives* an `@UUID` and the agent needs to verify the target exists:

```js
const m = html.match(/@UUID\[([^\]]+)\]\{([^}]+)\}/g);
for (const tok of m ?? []) {
  const [, uuid, label] = tok.match(/@UUID\[([^\]]+)\]\{([^}]+)\}/);
  const target = await fromUuid(uuid);
  if (!target) console.warn(`Broken @UUID: ${label} -> ${uuid}`);
}
```

## Parent-Child Linking

Most locations sit *inside* a parent. A tavern lives in a district; a district lives in a city; a city lives in a region. The CC `parentLocation` field is a string that holds the parent's **name** (resolved on commit). Storing the parent as a name (not a UUID) is a CC convention — it survives the doc being moved or its ID regenerating.

### Reading the parent

```js
const loc = game.journal.getName('The Black Tankard');
const parentName = loc.flags?.['campaign-codex']?.parentLocation;
// 'parentName' may be: a name string, '' (top-level), or undefined.
```

### Resolving the parent to a doc

```js
function resolveParent(childDoc) {
  const parentName = childDoc.flags?.['campaign-codex']?.parentLocation;
  if (!parentName) return null;  // top-level location
  return (
    game.journal.getName(parentName) ??
    game.journal.find(j => j.name?.toLowerCase() === parentName.toLowerCase())
  );
}

const parent = resolveParent(loc);
const parentUuid = parent?.uuid ?? null;
```

### Setting the parent on a new doc

When the agent creates a new location that should be a child of an existing one:

```js
const newLoc = await JournalEntry.create({
  name: 'The Black Tankard',
  flags: {
    'campaign-codex': {
      sheetType: 'location',
      type: 'tavern',
      parentLocation: 'Saltcliff',  // NAME, not UUID
      tags: ['tavern', 'coastal']
    }
  }
  // ... pages, etc.
});
```

### Discovering potential parents

If the user does not specify a parent, the agent should *ask* or *infer* from the world's hierarchy:

```js
// List all CC locations that have no parent (candidates for being the parent of a new sub-location)
const topLevelLocations = (ccIndex.location ?? []).filter(l =>
  !l.flags['campaign-codex'].parentLocation
);

// List all regions (CC's "region" type is for top-level geographic containers)
const regions = ccIndex.region ?? [];
```

Infer with a heuristic: if the new location's name contains a known region/district/city name, propose that as the parent. **Always confirm with the user** when ambiguity is high.

## Common Pitfalls

1. **Creating a duplicate NPC.** Searching by exact name only is not enough — also search for last-name-only, title+name, and known aliases. The Captain Voss rule: do not create "Captain Voss II".
2. **Failing to emit `@UUID` even when the UUID is known.** If the agent looked up the doc to confirm it exists, it must wire the link in the new content. Plain text is a bug.
3. **Wrong UUID format.** `@UUID[JournalEntry.abc]` is invalid because the ID is a 16-char hex (e.g. `JournalEntry.abc123def456ghij`). Always use `doc.uuid`, never hand-typed shorthand.
4. **Linking to a compendium UUID when a world doc exists.** `@UUID[Compendium.dnd5e.monsters.Item.Goblin]` is fine for an SRD goblin, but if the world has its own "Goblin King" NPC, you must link to *that* doc, not the SRD one. Always prefer world → compendium.
5. **Assuming `getName()` is fast on large worlds.** It is `O(n)` and is called for every linkify. Build a name index once and reuse it (see the `linkifyName` helper above).
6. **Confusing CC sheets with raw journals.** A `JournalEntry` with no `flags['campaign-codex']` flag is *not* a CC sheet. The agent must check the flag before assuming type-specific fields (`parentLocation`, `linkedNpcs`, etc.) are populated.
7. **Storing names in CC structured fields instead of UUIDs.** The `linkedNpcs`, `linkedShops`, `linkedQuests`, and `linkedJournals.linkedNpcId` fields expect **UUIDs** (e.g. `JournalEntry.abc123`). Storing `"Vaelen Kett"` there is a bug — the link won't resolve.
8. **Confusing `parentLocation` (a name) with `linkedNpcs` (a UUID array).** CC's convention is that `parentLocation` is a *name* string, while `linkedNpcs` etc. are *UUID* arrays. Do not flip them.
9. **Generating content that orphans existing docs.** If the world has a "Saltcliff" location, the new tavern inside Saltcliff must `parentLocation: 'Saltcliff'`. If the world has a "Vaelen Kett" NPC, the new quest mentioning him must put his UUID in `linkedNpcs[]`. Forgetting either leaves the new content detached from the world.
10. **Skipping `await` on `fromUuid()`.** It is async in v14. `const doc = fromUuid(uuid)` returns a `Promise`, not a `Document`. Always `await` and always check for `null` (broken links return `null`).
11. **Assuming `flags['campaign-codex']` exists.** Raw journals have no CC flag. Always use `?.` and provide a fallback (`?? []`, `?? ''`) — never assume the flag is populated.
12. **Renaming canonical NPCs to dodge the collision check.** Searching for "Voss" and finding "Voss Tower" (a location) does not mean "Captain Voss" is free. Search exhaustively, including by tags and linked docs.

## Verification Checklist

Before the agent commits a new sheet, page, or journal, confirm:

- [ ] **Searched** `game.journal` and `game.actors` for the proposed name and obvious variants.
- [ ] **Decided** reuse / extend / create. No silent duplicates.
- [ ] **No name collision** with an existing canonical entity. Variants ("II", "Jr.", "the Younger") rejected.
- [ ] **CC flag set** with `sheetType` (if authoring a CC sheet) and the correct type.
- [ ] **`parentLocation` set** to the parent doc's *name* (string), not UUID.
- [ ] **Structured cross-refs are UUIDs**: `linkedNpcs[]`, `linkedShops[]`, `linkedQuests[]` contain `JournalEntry.<id>` strings.
- [ ] **Every mentioned person/place/quest** in the new content is wrapped in `@UUID[...]{...}` if a world doc exists for it. No plain-text names for known entities.
- [ ] **All `@UUID` targets resolve** — `fromUuid(uuid)` returns a non-null document.
- [ ] **`@UUID` format is correct** — uses full ID (`JournalEntry.abc123def456ghij`), not shorthand.
- [ ] **Preferred world doc over compendium** — if the world has its own NPC, that NPC's UUID is used, not the SRD's.
- [ ] **`flags['campaign-codex']` accesses use optional chaining** — `flags?.['campaign-codex']?.tags` — because raw journals exist.
- [ ] **Tag overlap is intentional** — new tags should not collide with existing canonical tags for a *different* meaning. If the world uses `"coastal"` for one specific region, do not apply it broadly.
- [ ] **`linkedJournals` flag** (the legacy field) is only set when the typed fields (`linkedNpcs` etc.) do not apply, or in addition to them per CC convention.
- [ ] **Page content uses HTML @UUID**, not markdown `[name](uuid)` — Foundry renders only the former.
- [ ] **Await every `fromUuid()`** and check for `null` before dereferencing.

## Related Skills

- **`campaign-codex-sheets`** — the schema reference for the 6 CC sheet types and their flag fields (`sheetType`, `parentLocation`, `linkedNpcs`, `denizens`, `tags`, `linkedJournals`). Read this to know what fields exist; this skill teaches how to populate them from world context.
- **`dnd5e-content-authoring`** — pure D&D 5e mechanics/statblock/rule knowledge. Use when filling in *content* (AC, HP, CR, conditions); use this skill when wiring *cross-references* to the world.
- **`compendium-search-first`** — querying the SRD compendia (`game.packs`, `Compendium.dnd5e.*`). Different problem: SRD vs. world. The agent should still prefer world content over compendium content when both exist.
