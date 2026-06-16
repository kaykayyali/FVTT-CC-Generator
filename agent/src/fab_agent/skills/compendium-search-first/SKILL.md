---
name: compendium-search-first
description: "Use when generating any item, equipment, or actor reference for Foundry VTT v14 content — always search dnd5e SRD compendia first and link to existing entries (e.g., 'iron sword') rather than inventing duplicates. Compendium query patterns, search-by-name, by-type, by-rarity, the fromUuid workflow, and when it's appropriate to create new items. Load this whenever the agent is producing inventory, loot, or actor JSON that should link to existing world data."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [foundry, vtt, compendium, dnd5e, search, reuse, link, fromUuid, items]
    related_skills: [campaign-codex-sheets, dnd5e-content-authoring, world-context-linking]
---

# Compendium Search First

## Overview

This skill is the **link-to-data, don't-invent-data** rule. Foundry VTT ships with the dnd5e System Reference Document (SRD) compendia — thousands of items, spells, monsters, and equipment entries that are part of every dnd5e world. They are the canonical, balanced, art-illustrated, mechanically-correct versions of "a longsword," "a healing potion," "a goblin," and "plate armor."

When you (the agent) need to reference one of these things in a Campaign Codex shop inventory, NPC sheet, or quest reward, you have two options:

1. **Create a new world document** with your own name, your own price, your own description. This is the *easy* path and the *wrong* default. The world now has "Sturdy Longsword #47" that has no art, no mechanical link, doesn't show up in a search for "longsword," and breaks every roll table and macro that filters by item type.
2. **Link to the existing SRD entry** by UUID. The world gets the proper longsword, with its art, its damage die, its price, its rarity tag — and the inventory entry is one click away from a fully-functional item sheet.

This skill teaches option 2. Always.

## When to Use

Load this skill whenever the agent is about to emit any of the following into a CC sheet flag, a Foundry macro, or a structured JSON payload:

- A `shop` sheet's `inventory[]` entries (the most common case)
- A `npc` sheet's `gear` array
- A `quest` sheet's `rewards` array
- An `actorUuid` reference on an NPC that the user names (e.g. "spawn the goblin scout")
- A `treasure` or loot drop in an encounter payload
- Anything where the JSON has a field that *could* hold a UUID pointing at an existing document

**Don't use for:** freeform descriptive text in journal pages, original lore descriptions, flavor-only references ("a faded portrait of a long-dead queen"). Those are words, not data.

## The Rule

> **Always search dnd5e SRD compendia before creating a new item, equipment, monster, or actor. If it exists, link to it. If it doesn't, then you may create it.**

Read that twice. It is the entire skill in one sentence.

The corollary is the failure mode this skill exists to prevent:

> **A "Generic Sword" is never the right answer.** "Generic Sword" is what you write when you skipped the search step. Every SRD item the user might want is already there. Search, find, link.

This is not a soft suggestion. The user has been emphatic: **"if an iron sword exists in compendia, use that — don't make a unique sword every time."** A world full of "Brand New Iron Sword #47" entries is a world that does not function as a tabletop RPG. The economy breaks, the search breaks, the art is missing, and the GM has hundreds of duplicate items to clean up. The agent's job is to prevent that outcome on every shop, every NPC, every quest.

When the rule conflicts with the temptation to be "creative" (e.g., the LLM wants to invent a sword with a clever name), the rule wins. Get the creative text into the *description* field of an SRD link, not into a *new document*.

## Compendium Search Workflow

The agent runs in the browser context of Foundry VTT. `game`, `fromUuid`, and the entire `CompendiumPacks` collection are available globals. Treat the workflow below as a recipe — use it every time, in order.

### Step 1: Identify the dnd5e SRD compendium

Common dnd5e pack IDs you'll query:

| Pack ID              | Contents                                       |
| -------------------- | ---------------------------------------------- |
| `dnd5e.items`        | All items (weapons, equipment, consumables, tools, loot, magic items, containers) |
| `dnd5e.weapons`      | Weapons (Martial + Simple, both melee and ranged) |
| `dnd5e.equipment`    | Adventuring gear, armor, packs, mounts, vehicles |
| `dnd5e.consumables`  | Potions, scrolls, food, ammo                   |
| `dnd5e.loot`         | Gems, art objects, trade goods                 |
| `dnd5e.monsters`     | All bestiary creatures (goblin through dragon) |
| `dnd5e.spells`       | Every SRD spell                                |
| `dnd5e.classes`      | Class items (fighter, wizard, etc.)            |
| `dnd5e.races`        | Race items                                     |
| `dnd5e.feats`        | Feats                                          |
| `dnd5e.backgrounds`  | Backgrounds                                   |

Get a pack and check it exists:

```javascript
// Idiomatic existence check
if (!game.packs.has("dnd5e.items")) {
  console.warn("dnd5e.items pack not present in this world");
  return;
}

const itemPack = game.packs.get("dnd5e.items");
```

### Step 2: Search the index by name (case-insensitive, partial match)

The pack `index` is an array of light-weight entries. **Search the index first** — fetching the full document is expensive, and the index has every field you need to decide whether a link is a match.

```javascript
// Always lowercase both sides for case-insensitive partial match
function findInPack(pack, query) {
  const q = query.toLowerCase();
  return pack.index.find(e => e.name.toLowerCase().includes(q));
}

const hit = findInPack(itemPack, "longsword");
// hit = { _id: "abc123", name: "Longsword", type: "weapon", img: "...", system: {...} }
```

For multiple matches (e.g. "potion" matches Healing Potion, Potion of Climbing, etc.):

```javascript
function findAllInPack(pack, query) {
  const q = query.toLowerCase();
  return pack.index.filter(e => e.name.toLowerCase().includes(q));
}

const potions = findAllInPack(itemPack, "healing potion");
// Pick the best one (lowest rarity, common variant, etc.) for a mundane shop
```

Search the right pack. **Longsword is in `dnd5e.weapons` AND `dnd5e.items`; the weapons pack is the canonical source.** If you're not sure which pack, start with `dnd5e.items` — it has everything.

### Step 3: Get the full document (when you need its data, not just the link)

```javascript
// From an index entry's _id
const doc = await itemPack.getDocument(hit._id);
// doc is a full Item document with .system, .effects, etc.

// Same call, by ID directly
const doc2 = await itemPack.getDocument("abc123");
```

You almost never need step 3 for the *search-first* workflow. You only need the full document if you're copying fields (price, damage) into the CC sheet. Usually the UUID is enough.

### Step 4: Get the UUID for linking

Every document in a compendium has a `.uuid` of the form `Compendium.<packId>.<docId>`:

```javascript
const uuid = doc.uuid;
// "Compendium.dnd5e.items.abc123"
```

This is the string you write into the CC sheet's `compendiumUuid` field. **Always use `Compendium.dnd5e.items.abc123`, not `abc123` alone** — bare IDs do not resolve across worlds.

### Step 5: Resolve a UUID back to a document (`fromUuid`)

The reverse direction. Used to verify a link works, and used by every other Foundry macro that touches the entry:

```javascript
const resolved = await fromUuid("Compendium.dnd5e.items.abc123");
// resolved is the full Item document, or null if the link is broken

if (!resolved) {
  console.error("Compendium link is broken — the pack may be disabled or the entry was renamed.");
}
```

### Putting it together: a one-call "search-or-null" helper

```javascript
async function srdLookup(query, packId = "dnd5e.items") {
  if (!game.packs.has(packId)) return null;

  const pack = game.packs.get(packId);
  const q = query.toLowerCase();

  const hit = pack.index.find(e => e.name.toLowerCase().includes(q));
  if (!hit) return null;

  const doc = await pack.getDocument(hit._id);
  return { uuid: doc.uuid, name: doc.name, id: doc.id, doc };
}

// Usage in a macro or generator
const sword = await srdLookup("longsword", "dnd5e.weapons");
// sword.uuid === "Compendium.dnd5e.items.abc123"
```

This is the function the agent should call mentally on every item reference.

## When to Search vs When to Create

The rule is "search first." The follow-up question is "and when do I get to *create*?" The decision tree:

### Search (link to existing)

- **Mundane weapons**: longsword, shortsword, dagger, rapier, greataxe, mace, javelin, hand crossbow, longbow, shortbow, warhammer, spear
- **Mundane armor**: leather, studded leather, chain shirt, scale mail, breastplate, half plate, plate, shield (any variant)
- **Adventuring gear**: rope (hempen/silk), lantern (hooded/bullseye), bedroll, backpack, crowbar, grappling hook, mirror (steel), tinderbox, rations, waterskin, manacles
- **Potions and scrolls**: potion of healing (all four rarities), potion of climbing, potion of water breathing, scroll of identify, scroll of detect magic
- **Common loot (DMG tables)**: gem of value X, art object Y, all the `dnd5e.loot` entries
- **SRD monsters**: goblin, hobgoblin, orc, kobold, gnoll, lizardfolk, ogre, troll, hill giant, manticore, owlbear, wyvern, all dragon variants up to adult
- **Standard humanoid NPCs**: bandit, bandit captain, guard, knight, veteran, spy, priest, acolyte, druid, mage, thug
- **Common spells**: fire bolt, magic missile, cure wounds, healing word, shield, misty step, fireball, counterspell

If the user says "the bandit captain," the entry exists in `dnd5e.monsters`. Don't write "Brigand Leader" from scratch — link to `Bandit Captain`.

### Create (it's not in the SRD — make it fresh)

- **Named magical artifacts of the campaign**: "the Blade of the Sea-King," "Vaelen's Ledger," "the Sunken Crown"
- **Custom magic items with bespoke lore**: items whose description references campaign-specific events, NPCs, or places
- **Named villains and unique monsters**: a goblin king who has a name, a stat block the LLM designed, and three signature abilities
- **Variant creatures with custom stat blocks**: a "plague ogre" with disease mechanics the SRD doesn't have
- **User explicitly asks for invention**: "make up a magic item for the pirate captain" — the user is requesting an act of creation, link to nothing
- **Player-character specific items**: "Thalindra's moonblade" — clearly tied to a PC, no SRD analog
- **Factions, vehicles, buildings as documents**: the SRD doesn't have these, so creation is the only option

### Decision table

| Item class                                       | Action                                    |
| ------------------------------------------------ | ----------------------------------------- |
| Iron sword, longsword, dagger                    | Search `dnd5e.weapons` → link            |
| Healing potion, gem, art object                  | Search `dnd5e.items` → link               |
| Goblin, orc, ogre, adult red dragon              | Search `dnd5e.monsters` → link            |
| Bandit captain, knight, spy, priest              | Search `dnd5e.monsters` (humanoid) → link |
| "The Blade of the Sea-King"                      | **Create** new `Item` with `type: weapon` |
| "Vaelen's Ledger" (plot item)                    | **Create** new `Item` with `type: loot`   |
| Named villain with bespoke stat block            | **Create** new `Actor` with `type: npc`   |
| "A goblin who commands the bridge"               | **Create** variant Actor (link SRD goblin as `prototypeToken` or just create fresh — see Linking in NPC Sheets) |
| Generic "rope"                                   | Search `dnd5e.items` → link               |
| User: "invent a magic sword for the sea-king"    | **Create** (user-requested invention)     |

When in doubt: **search first. If you found it, link it. If you didn't find it, create it.** That is the only order of operations.

## Linking in Shop Inventory

The Campaign Codex `shop` sheet's inventory array lives at `flags.campaign-codex.custom.inventory[]`. Each entry references a line item the shop stocks. **The correct shape uses `compendiumUuid`.** The incorrect shape invents a duplicate.

### Right way — link to SRD entry

```json
{
  "name": "Longsword",
  "qty": 3,
  "price": "15 gp",
  "linkToCompendium": true,
  "compendiumUuid": "Compendium.dnd5e.items.abc123"
}
```

Fields:

- `name` — copy of the SRD name, for display before the link resolves
- `qty` — integer, how many in stock
- `price` — string with denomination (e.g. `"15 gp"`, `"50 sp"`, `"3 pp"`)
- `linkToCompendium: true` — flag for the CC renderer to show the link
- `compendiumUuid` — the full `Compendium.<packId>.<docId>` string

### Right way — multiple SRD weapons in a smithy

```json
[
  { "name": "Longsword",            "qty": 3, "price": "15 gp", "linkToCompendium": true, "compendiumUuid": "Compendium.dnd5e.items.ls001" },
  { "name": "Shortsword",           "qty": 5, "price": "10 gp", "linkToCompendium": true, "compendiumUuid": "Compendium.dnd5e.items.ss002" },
  { "name": "Dagger",               "qty": 12,"price": "2 gp",  "linkToCompendium": true, "compendiumUuid": "Compendium.dnd5e.items.dg003" },
  { "name": "Chain Mail",           "qty": 1, "price": "75 gp", "linkToCompendium": true, "compendiumUuid": "Compendium.dnd5e.items.cm004" },
  { "name": "Shield",               "qty": 4, "price": "10 gp", "linkToCompendium": true, "compendiumUuid": "Compendium.dnd5e.items.sh005" },
  { "name": "Healing Potion",       "qty": 8, "price": "50 gp", "linkToCompendium": true, "compendiumUuid": "Compendium.dnd5e.items.hp006" }
]
```

### Right way — mixed inventory with one custom item

```json
[
  { "name": "Longsword",            "qty": 3, "price": "15 gp", "linkToCompendium": true,  "compendiumUuid": "Compendium.dnd5e.items.ls001" },
  { "name": "Healing Potion",       "qty": 8, "price": "50 gp", "linkToCompendium": true,  "compendiumUuid": "Compendium.dnd5e.items.hp006" },
  { "name": "The Blade of the Sea-King", "qty": 1, "price": "3000 gp", "linkToCompendium": false }
]
```

The custom item has `linkToCompendium: false` and no `compendiumUuid` — it will be created as a fresh world Item when the sheet is committed.

### Wrong way — duplicate, no link

```json
{
  "name": "Sturdy Longsword",       // ← made up, not in compendia
  "qty": 3,
  "price": "15 gp"
}
```

**This is the failure mode.** No `compendiumUuid` means the world gets a new "Sturdy Longsword" with no art, no link, no mechanical source, and no way to find it via compendium search. The user explicitly forbade this pattern.

### Wrong way — bare ID

```json
{
  "name": "Longsword",
  "qty": 3,
  "price": "15 gp",
  "compendiumUuid": "abc123"          // ← WRONG: missing Compendium.dnd5e.items. prefix
}
```

The `Compendium.<pack>.<id>` form is required. `fromUuid("abc123")` returns null.

## Linking in NPC Sheets

The Campaign Codex `npc` sheet's `flags.campaign-codex.custom.actorUuid` field is the canonical link to an Actor document. The two cases:

### Case 1: The Actor already exists in the world

The user says "Brennan the Innkeeper is the barkeep at the Saltcliff Arms." If Brennan already exists as an Actor in the world, the sheet should reference him by UUID:

```json
{
  "name": "Brennan the Innkeeper",
  "actorUuid": "Actor.abc123def456"
}
```

How to find that UUID:

```javascript
const actor = game.actors.getName("Brennan the Innkeeper");
const uuid = actor?.uuid ?? null;
// "Actor.abc123def456"
```

If the agent has world-context search via the `world-context-linking` skill, prefer that path — it searches the world, not compendia.

### Case 2: The Actor doesn't exist yet

If the user says "add a goblin scout to the encounter," the goblin doesn't exist as a world Actor. The workflow is:

1. **Search the SRD first** — `dnd5e.monsters` has `Goblin`. Link to that as a *prototype*.
2. **If the creature is custom** — there's no SRD analog — create a new world Actor, then store its UUID in the NPC sheet.

Right way — link to SRD monster (when the NPC is a stock creature):

```json
{
  "name": "Goblin Scout",
  "actorUuid": "Compendium.dnd5e.monsters.goblinXYZ",
  "compendiumLink": true
}
```

Right way — create new world Actor for a unique creature:

```javascript
// 1. Create the Actor in the world
const created = await Actor.create({
  name: "Vaelen the Pale",
  type: "npc",
  img: "icons/svg/mystery-man.svg",
  system: {
    abilities: { /* full stat block */ },
    details: { biography: { value: "..." } }
  }
});

// 2. Use the resulting UUID in the CC sheet
const npcPayload = {
  name: "Vaelen the Pale",
  actorUuid: created.uuid   // "Actor.zyx987"
};
```

Wrong way — store a compendium ID as if it were a world Actor:

```json
{
  "name": "Goblin",
  "actorUuid": "Compendium.dnd5e.monsters.goblinXYZ"  // ← won't drag onto a scene
}
```

A `Compendium.dnd5e.monsters.*` UUID **can** be linked for reference/display, but if the user will drag the NPC onto a map, you need a *world* Actor (created with `Actor.create()`) and its `Actor.<id>` UUID. **For NPCs that will appear on a scene: create a world Actor, link to the world Actor.**

Rule of thumb:
- **Reference / lore / "read about"** → `Compendium.dnd5e.monsters.*` is fine
- **Will be dropped on a scene, drawn into combat, given items** → must be a world `Actor.<id>`

## Common Pitfalls

The ways the rule gets broken. Every one of these is a real failure mode the agent has hit, or is likely to hit. Read them.

1. **"I'll just write a generic 'sword' since I don't have time to search."** NO. You have time. Searching `dnd5e.weapons` for "sword" returns 12+ SRD weapons in milliseconds. The "no time" excuse is the LLM pattern that creates "Brand New Sword #47."

2. **Searching only by exact name.** `pack.index.find(e => e.name === "Longsword")` misses "Longsword +1," "Greatsword," "Longsword of Sharpness," and the dozens of magical longsword variants. Use `.toLowerCase().includes(query)` and rank by relevance.

3. **Assuming the compendium is loaded.** In v14, compendia are *indexed* at world boot but not fully *loaded*. `getDocument()` works without explicit `pack.getDocuments()`, but if the user disabled a module, the pack may not exist. Always check `game.packs.has("dnd5e.items")` before searching.

4. **Linking to compendium items the world doesn't have enabled.** The world may not have the `dnd5e.items` pack enabled (rare but possible on locked-down worlds). Always verify the pack is in `game.packs` before committing the link.

5. **Forgetting to verify the link resolves.** Just because you wrote `Compendium.dnd5e.items.abc123` doesn't mean the UUID is real. Before committing inventory, run:
   ```javascript
   const doc = await fromUuid("Compendium.dnd5e.items.abc123");
   if (!doc) { /* broken link, fall back to creating the item */ }
   ```
   This is non-negotiable for production-quality output.

6. **Creating a new item when an SRD one is a 95% match.** The LLM invents "Sunset Shortsword — a blade forged in the dying light of the western sea, +1 to attack rolls." The right move is **link to SRD Shortsword** and put the flavor in the *description* of the inventory entry, not in a brand-new item document. The world doesn't need a duplicate Shortsword; it needs a Shortsword with a pretty description.

7. **Looking in the wrong pack.** `dnd5e.items` is the universal pack. `dnd5e.weapons` is the weapons-only pack. `dnd5e.loot` is gems/art. If you search `dnd5e.weapons` for "healing potion" you'll find nothing — it's a consumable in `dnd5e.items`. When unsure, **start with `dnd5e.items`**, then narrow.

8. **Bypassing search for "obvious" items.** "It's just rope, I know it's in there." Yes, and so is the broken `compass`, the `hempen rope` (50 ft), and the `silk rope` (50 ft). Search anyway, every time, because the agent's memory of what's in the SRD is unreliable and stale.

9. **Saving the *name* as if it were a UUID.** `"compendiumUuid": "Longsword"` is a string that `fromUuid()` cannot resolve. The `Compendium.<pack>.<id>` format is mandatory. If the agent finds itself emitting a plain English name in a UUID field, it has skipped a step.

10. **Forgetting `linkToCompendium: true` on inventory entries.** The CC renderer uses the boolean flag to decide whether to render the entry as a clickable link or as plain text. Omitting it (or setting `false` on an SRD-linked item) breaks the click-to-open behavior. The default should be `true` for any entry with a `compendiumUuid`.

11. **Creating monsters as items.** When the user says "the goblin scout," the right document type is `Actor` (with the `goblin` Actor type), not `Item`. Search `dnd5e.monsters` for monsters, `dnd5e.items` for items. The pack ID tells you the document type.

12. **Storing the `name` field with editor commentary.** `"name": "Longsword (very common)"` is noise. The `name` is for display; commentary belongs in a `notes` or `description` field. CC expects clean names to match against compendium indexes.

## Verification Checklist

Before the agent commits a `shop` (or any sheet) with linked inventory, walk this list. Every box must be checked, in order.

- [ ] **Pack exists.** `game.packs.has("dnd5e.items")` returns `true`. (If false, the world has the dnd5e system disabled or filtered — abort and warn.)
- [ ] **Each inventory entry has been searched** in the appropriate dnd5e pack before being added.
- [ ] **Each `compendiumUuid` resolves.** Run `fromUuid(uuid)` for every entry; confirm non-null. Broken links are not acceptable.
- [ ] **`linkToCompendium: true` is set** for every entry that has a `compendiumUuid`.
- [ ] **Custom items have `linkToCompendium: false`** and no `compendiumUuid` — they will be created fresh on commit.
- [ ] **No near-duplicate of an SRD item is being created.** If a custom item's mechanical profile matches an SRD item, the SRD item should be linked and the flavor moved to description.
- [ ] **The right pack was used.** Weapons searched in `dnd5e.weapons` (or `dnd5e.items`). Potions in `dnd5e.items`. Monsters in `dnd5e.monsters`. Gems in `dnd5e.loot`.
- [ ] **Partial-match search was used** (`.includes()`), not exact match, to catch variants.
- [ ] **NPC `actorUuid` values resolve** to a real `Actor` document (world or compendium). If the NPC will appear on a scene, the UUID must be a world Actor UUID, not a `Compendium.dnd5e.monsters.*` UUID.
- [ ] **Custom actors were created via `Actor.create()`** before the CC sheet references them; the sheet stores the resulting `.uuid`, not a name or an intention.
- [ ] **Prices match rarity tier.** A "healing potion" linked from SRD costs 50 gp; if your inventory says 5 gp, either the link is wrong or you're pricing the wrong item.
- [ ] **No invented "unique" versions of stock items.** No "Sturdy Longsword," "Fine Dagger," "Quality Rope." The user banned this pattern. If the item is stock, link it. If it's truly custom, name it for its lore, not its quality.

If any checkbox fails, **fix the JSON, do not commit the sheet.** A clean sheet is one where every link resolves and every non-link is genuinely bespoke.

## Related Skills

- **`campaign-codex-sheets`** — the schema reference for the `shop`, `npc`, and other CC sheet types this skill produces JSON for. The `flags.campaign-codex.custom.inventory[]` and `actorUuid` shapes live there.
- **`dnd5e-content-authoring`** — the 5e mechanics and lore layer. Use it to decide *what* a Blacksmith in a Large Town ought to stock; this skill decides *how* to link those items to compendium UUIDs.
- **`world-context-linking`** — the parallel skill for searching the *user's world* (not compendia). When the user says "Brennan the Innkeeper" and Brennan is a world Actor, that skill owns the lookup. This skill owns compendium lookups. Together they form the full search-first toolkit.
