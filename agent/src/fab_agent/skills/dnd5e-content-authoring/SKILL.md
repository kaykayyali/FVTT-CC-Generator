---
name: dnd5e-content-authoring
description: "Use when generating D&D 5e (5.1e/2024) campaign content — NPCs, locations, shops, encounters, items. Naming conventions by culture/region, settlement scaling, encounter CR/level math, item rarity/pricing, NPC stat blocks. Load this when the agent needs domain knowledge for 5e-flavored content authoring, not raw schema knowledge."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [foundry, vtt, dnd5e, content-authoring, npc, location, shop, encounter, item]
    related_skills: [campaign-codex-sheets, compendium-search-first, world-context-linking]
---

# D&D 5e Content Authoring

## Overview

This is the **lore and mechanics** skill. It teaches the agent how to *think* like a tabletop RPG game-master so the content it produces — NPCs, settlements, shops, encounters, items — is internally consistent, mechanically sound, and feels like it belongs at a real 5e table.

It is deliberately decoupled from Foundry's data model. Foundry-specific shapes (CC flag schemas, `convertJournalToCCSheet`, compendium UUIDs) live in the `campaign-codex-sheets` and `compendium-search-first` skills. **This skill is the pure 5e knowledge layer.** When the agent composes a sheet, it draws on both: this skill says *what* a Blacksmith in a Large Town ought to charge and *what* a CR 5 bandit captain looks like; the schema skills say *how* to write that into a `JournalEntry.flag.campaign-codex` payload.

Two guiding principles run through every section:

1. **Use SRD-licensed standards.** The 5e System Reference Document is the rulebook for published material. Reference its numbers (XP tables, item prices, CR-to-stat-block) as defaults unless the user's world says otherwise.
2. **Lean toward concrete detail over abstraction.** A "tavern" is forgettable; "a low-beamed dockside tavern lit by bioluminescent jellyfish tanks, run by a one-handed ex-watch officer" is a place players remember. Always trade the generic for the specific.

## When to Use

Load this skill when **any** of the following is true:

- Generating or revising an NPC sheet (stat block, motivation, personality, voice, secret).
- Generating or revising a location or region (settlement size, what buildings exist, what goods are stocked).
- Generating or revising a shop (inventory, prices, magic items for sale, opening hours).
- Generating or revising a quest that includes an encounter (how many monsters of what CR, expected party difficulty).
- Generating or revising an item (rarity, price, attunement, mechanical effect).
- Naming an NPC, settlement, faction, or item with cultural flavor.
- Sanity-checking user-supplied content (e.g., "is this NPC's CR right for a level 4 party?").

**Don't use this skill for:** rules disputes between 5.1e (2024) and 5.0e (2014) — defer to whatever the user's world is using; Foundry VTT API questions; Campaign Codex flag schemas; how to write a `convertJournalToCCSheet` call. The other skills in the family own those.

If you're unsure which skill to load, **load this one alongside `campaign-codex-sheets`**. They are the two foundational skills; the other two (`compendium-search-first`, `world-context-linking`) are workflow accelerators.

## NPC Generation

NPCs are the heart of any campaign. The default failure mode is **generic**: "Brennan the Innkeeper, age 42, likes ale, has a daughter." Players forget Brennan by the next town. The cure is specific, grounded detail plus a **functional purpose** in the world.

### The Three-Trait Rule

Every NPC gets **two to three memorable traits**, not ten. Pick from:

- **A physical tic** — a missing finger, a habit of cracking knuckles, an old burn scar.
- **A verbal habit** — always says "aye," ends sentences with "...eh?", quotes a dead spouse.
- **A contradiction** — cheerful gravedigger, soft-spoken assassin, kindly loan shark.
- **An object** — a locket they never open, a sword they won't sell, a pipe that's always lit.

Two-to-three is the sweet spot. One is forgettable; four and the player can't remember which is which.

### Role → Stat Block

Most NPCs you generate are **conversational** (don't need combat stats), and those should be a `commoner`, `noble`, or `bandit` — or just a `personality + motivation` block with no stat block at all. Only spend the tokens on a full stat block if the NPC will be **drawn into initiative**.

When you do need a stat block, the SRD provides these standard NPC stat blocks you can use as-is or scale:

| Role | SRD Stat Block | Approx. CR | Notes |
|------|----------------|-----------|-------|
| Commoner | `commoner` | 0 | Unarmed, AC 10, 4 HP. Background flavor only. |
| Guard | `guard` | 1/8 (1/4 in 5.1e) | Light armor, spear, 11 HP. Town watch, escort. |
| Bandit | `bandit` | 1/8 (1/4 in 5.1e) | Leather, scimitar, 11 HP. Roadside, gang. |
| Thug | `thug` | 1/2 | Multiattack, 32 HP. Enforcer, brute. |
| Bandit Captain | `bandit captain` | 2 | Multiattack, 65 HP. Mid-fight leader. |
| Veteran | `veteran` | 3 | Heavy armor, 2 attacks, 58 HP. Trained soldier. |
| Knight | `knight` | 3 (5.1e) | Plate, 3 attacks (with reaction), 75 HP. |
| Gladiator | `gladiator` | 5 | Arena, parry, 126 HP. |
| Mage | `mage` | 6 | 18th-level caster, 40 HP. |
| Assassin | `assassin` | 8 | Sneak attack 4d6, 78 HP. |
| Veteran (reskinned) | scaled `veteran` | varies | "Elite" — see scaling below. |

### Minion / Standard / Elite / Boss

For custom stat blocks, scale the four "tiers" like this (party of 4 baseline):

| Tier | HP Multiplier | To-Hit Bonus | Damage per Attack | Suggested CR for L5 party |
|------|---------------|--------------|-------------------|--------------------------|
| **Minion** | 1× | +0 to +2 | 1d6+0 to 1d8+2 | 0 to 1/4 |
| **Standard** | 2× to 3× | +3 to +5 | 1d8+2 to 2d6+3 | 1/2 to 2 |
| **Elite** | 4× to 6× | +6 to +8 | 2d8+3 to 3d6+4 | 3 to 7 |
| **Boss** | 8× to 12× | +9 to +12 | 3d8+5 to 4d10+6 | 8 to 12 |

**Rule of thumb:** the party of 4 should defeat **2× minions**, **1 standard**, **1 elite** (with resource spend), or **1 boss** (long, hard fight) in one medium-length combat. The **Encounter Scaling** section below has the XP math.

### Ability Score Priorities by Archetype

If the user wants a fresh stat block, use these priorities (15-point-buy / standard array — 5.1e uses a slightly different array but the priorities hold):

- **Brute (barbarian, thug, ogre):** STR highest, CON second, then DEX. Dump INT, WIS, CHA.
- **Skirmisher (rogue, bandit captain, scout):** DEX highest, then CON, then WIS (perception). CHA is fine.
- **Soldier (guard, veteran, knight):** CON highest, then STR or DEX, then WIS. Plate-armor builds want STR 15 for plate's 65 lbs.
- **Archer (hunter, bandit archer):** DEX highest, then WIS, then CON.
- **Sniper/spellcaster (mage, warlock, sorcerer):** INT or CHA highest, then DEX (AC), then CON. Dump STR.
- **Healer/cleric:** WIS highest, then CON, then STR (heavy armor).
- **Social (noble, spymaster, smooth-talker):** CHA highest, then WIS, then CON.

### Motivation

Every NPC wants something. Pick from these classic 5e motivations, then make it specific:

- **Survival** — "Keep my family fed through the winter."
- **Wealth** — "Pay off the loan I took to bury my husband."
- **Status** — "Be recognized as the best smith in the duchy, even if I have to sabotage the others."
- **Revenge** — "Find the man who killed my brother — and ruin him slowly."
- **Love** — "Win back the curate who spurned me, even though I've turned to smuggling to do it."
- **Knowledge** — "Find the lost library my grandfather died searching for."
- **Redemption** — "Make up for the patrol I led into the ambush that killed them."
- **Faith** — "See the old temple rebuilt before I die."
- **Fear** — "Stay out of the cult's sight by being useful to someone else."

Combine two at most: a primary + a hidden. The hidden motivation is what `secret` is for.

### Worked Example NPC

**Vaelen Kett — the one-handed innkeeper.**

- **Sheet type:** `npc` (type: `neutral`)
- **Description:** Sharp-featured half-elf, mid-40s, with a leather glove over the right hand that isn't there. Wears a watch-captain's pin on a cord around her neck but never pinned to her coat.
- **Personality (the three traits):** Wry, watchful, fast with a joke but slow with trust. Remembers every drink she's poured and the face of everyone who ordered one. (Three traits: wry-but-watchful demeanor, perfect memory for faces/orders, slow to trust.)
- **Motivation:** Keep the Lantern running and her crew fed; never owe anyone a debt again.
- **Secret:** "Vaelen" is not her real name. She was once a lieutenant in the city's night-watch, dismissed after she refused an order to burn a smuggler's ship with crew still aboard. The missing hand is from the same night — punishment, not combat.
- **Voice:** Slight coastal drawl; drops articles ("seen the tide come in, I have"); calls most patrons "friend" or "captain"; never raises her voice.
- **Stat block (if drawn into a fight):** Use `spy` (CR 1, light armor, short sword + shortbow, sneak attack +2d6). She is **not** a frontline combatant — she fights only if cornered, and only to escape, not to win.

That NPC tells the GM everything they need: where the scene plays out, what hooks to dangle, what happens if the players push her, and why she's a smuggler without ever saying "smuggler" in the description.

## Location Generation

A location is more than a name on a map. It is a **set of expectations** — what you can buy, who lives here, what the watch is like, what time the gates close, and what secrets the alleys hold. Generate a location by working from the outside in: settlement size → local economy → notable buildings → interior layout.

### Settlement Sizes (5e standard)

| Size | Population | In-world Services |
|------|-----------|-------------------|
| **Thorp** | ~20 | Single farmstead, no real services. Possibly a shrine. |
| **Hamlet** | ~80 | One inn, one shrine, maybe a general store. Two or three dozen buildings. |
| **Village** | ~200 | Inn, smithy, temple, general store, possibly an alchemist or healer. |
| **Small town** | ~900 | Multiple inns, two or three temples, smithy, market, possibly a small magic-shop (apothecary-tier). |
| **Large town** | ~2,000 | All the above plus jeweler, magic-shop (common-to-uncommon items), guild halls, temple of choice. |
| **Small city** | ~9,000 | District structure, multiple magic-shops (including rare items), universities, full temple pantheon, dedicated thieves' quarter. |
| **Large city** | ~25,000 | Above plus high-tier magic-shops, arcane academies, noble quarters, organized guilds, working sewers. |
| **Metropolis** | ~100,000+ | Above plus planar enclaves, dragon-towers, guild armies, district governments. |

If the user doesn't specify a size, **default to a small town or village** for new content. Most adventuring happens there; cities should feel like a destination.

### Building Types and What's Inside

Every CC location sheet should answer: **what's inside this building?** Use these as scaffolding.

#### Tavern / Inn

- **Common room** — main hall, hearth, bar, tables, possibly a stage.
- **Kitchen** — back of house, pantry, cellar with ale/wine.
- **Private rooms** — 1 to 10, scale with inn size. Rent by the night: 2 cp (common) to 2 gp (luxury suite) per person.
- **Stable** — usually attached; 5 cp per mount per night.
- **Cellar** — always ask "what's in the cellar?" It's a smuggler tunnel, a hidden shrine, a flooded passage, or a captured monster. Don't leave it empty.

#### Temple / Shrine

- **Sanctum / main hall** — pews, altar, holy symbol, possibly a statue of the deity.
- **Vestry / back room** — where the clergy prepare ceremonies, store robes, sleep.
- **Shrine to allied deity** — temples dedicated to one god often have a small alcove for allied gods.
- **Reliquary** — temple's holiest object, usually locked, often the MacGuffin.
- **Cloister / living quarters** — for the clergy and novices.
- **Crypt / catacomb** — older temples always have one. Ask "what's buried here?"

#### Smithy / Forge

- **Forge room** — the fire, anvil, bellows, water barrel. Always hot, always loud.
- **Showroom / sales floor** — finished weapons, tools, and armor on racks.
- **Work area** — half-finished projects, raw materials, scrap.
- **Living quarters** — usually the smith and family live above or behind.
- **Back room** — where the smith hides the good stuff or takes payment in kind.

#### Wizard's Tower / Arcane Study

- **Study** — desk, books, the wizard's ongoing project.
- **Library** — possibly trapped, possibly sentient (a mimic as a bookshelf is a classic).
- **Laboratory** — alchemical gear, possibly a familiar's roost.
- **Summoning chamber** — warded circle, possibly a bound outsider.
- **Bedroom** — surprisingly spartan. Wizards don't sleep much.

#### Generic

Every building has a **front of house** (where customers/clients see) and a **back of house** (where the business actually happens). Always describe both.

### Worked Example Location

**The Drowned Lantern — a dockside tavern.**

- **Sheet type:** `location` (type: `structure`, subtype: `tavern`)
- **Parent location:** `Saltcliff - Dock Ward`
- **Tags:** `tavern`, `smuggler`, `port`, `lawless`
- **Description (1-3 sentences):** A low-beamed dockside tavern lit by bioluminescent jellyfish tanks. The owner lost a hand to the city guard and now runs a smuggling operation out of the cellar.
- **Layout (body prose):**
  - **Common room** — twelve tables, sanded floor that still smells of brine. The bar is a salvaged ship's bow. Two jellyfish tanks behind it, casting a greenish glow. A small stage in the corner for a fiddler most nights.
  - **Kitchen** — smoke-blackened, run by Old Maren's daughter. Serves fish stew (3 cp a bowl), bread (1 cp), black ale (2 cp a tankard).
  - **Six private rooms** upstairs — 8 cp a night for a common pallet, 5 sp for a room with a real bed, 2 gp for the corner room with a view of the dock and a lock that actually works.
  - **Cellar** — barrels of ale, a cask of black-market salt pork, and behind a false back wall, a tide-tunnel that surfaces in a sea cave a half-mile down the coast.
- **Denizens:** Vaelen Kett (innkeeper, smuggler); Old Maren (bouncer, ex-naval); the fiddler.
- **Rumors:**
  - "The lanterns in the cellar never go out, even when you snuff them."
  - "Vaelen pays the guard captain in gold, not coin."
- **Secrets:**
  - The cellar connects to a sea cave via an old smuggler's tunnel — known only to Vaelen and one of the watch captains.
  - The fiddler is a deserter from the city's mage-watch, hiding behind a glamour.

That single CC sheet gives the GM **four scenes** (common room, kitchen, upstairs, cellar), **two NPCs** (plus a secret one), **two rumors** to dangle, and **two secrets** to reveal. It will run three to four sessions by itself.

## Shop & Inventory

A shop sheet lives or dies by its **price list**. A general store in a village should *not* stock the same items as a magic-shop in a metropolis, and a village smithy should *not* sell plate armor for the same price as a city smithy. Get the economy right and the world feels real; get it wrong and players game the system.

### Pricing by Settlement Size

Apply a **settlement multiplier** to the base SRD price. The base price assumes a small town or large town. Village prices are higher (less supply, less competition), city prices are lower (more supply, more competition).

| Settlement | Buy Price Multiplier | Sell Price Multiplier |
|------------|---------------------|----------------------|
| Thorp / Hamlet | ×2.0 | ×0.3 |
| Village | ×1.5 | ×0.4 |
| Small town | ×1.0 | ×0.5 |
| Large town | ×1.0 | ×0.5 |
| Small city | ×0.8 | ×0.55 |
| Large city | ×0.7 | ×0.6 |
| Metropolis | ×0.6 | ×0.65 |

**Rule of thumb:** a village blacksmith has *less selection* (basic tools, daggers, hand-axes, maybe a couple of swords) and charges *more* (1.5× base). A city smithy has *full selection* and charges *less* (0.7× base).

### Magic Item Pricing by Rarity (SRD)

These are the standard 5e SRD-listed price ranges for magic items. Use them as the **base**; actual prices in-world are negotiated, and rare items are often *unobtainable* at any price (you have to quest for them).

| Rarity | Base Price Range | Notes |
|--------|------------------|-------|
| **Common** | 50–100 gp | Frequently available in any town of 2,000+. |
| **Uncommon** | 200–500 gp | Available in large towns and cities, often "by special order." |
| **Rare** | 2,000–5,000 gp | Available in cities, but typically requires a quest hook or favor. |
| **Very rare** | 20,000–50,000 gp | Almost never on shelves; find a collector, an auction, or a dragon's hoard. |
| **Legendary** | 100,000+ gp | Quest rewards, divine gifts, or patronage. Never sold. |
| **Artifact** | Priceless | Plot device, not merchandise. |

**Always use the SRD item if it exists.** Don't invent "+1 longsword" — that's `Compendium.dnd5e.items.Weapon.+1Longsword` (or the equivalent in the user's world). The `compendium-search-first` skill covers how to look these up.

### Mundane Gear Pricing (SRD reference)

These are the standard 5e SRD base prices for common gear. Apply the settlement multiplier above.

| Item | Base Price | Item | Base Price |
|------|-----------|------|-----------|
| Backpack | 2 gp | Bedroll | 1 gp |
| Rations (1 day) | 2 sp | Waterskin | 2 sp |
| Torch (6 pack) | 1 cp | Hooded lantern | 5 gp |
| Oil (flask) | 1 sp | Rope, hempen (50 ft) | 1 gp |
| Rope, silk (50 ft) | 10 gp | Manacles | 2 gp |
| Crowbar | 2 gp | Mirror, steel | 5 gp |
| Spellbook | 50 gp | Component pouch | 25 gp |
| Holy symbol | 5 gp | Healer's kit (10 uses) | 50 gp |
| Studded leather | 45 gp | Chain shirt | 50 gp |
| Chain mail | 75 gp | Plate | 1,500 gp |
| Shield (steel) | 10 gp | Shield, wooden | 5 gp |
| Dagger | 2 gp | Handaxe | 5 gp |
| Shortsword | 10 gp | Longsword | 15 gp |
| Greatsword | 50 gp | Rapier | 25 gp |
| Mace | 10 gp | Warhammer | 15 gp |
| Light crossbow | 25 gp | Heavy crossbow | 50 gp |
| Hand crossbow | 75 gp | Longbow | 50 gp |
| 20 arrows | 1 gp | 20 crossbow bolts | 1 gp |
| Healer's kit (10 uses) | 50 gp | Antitoxin (vial) | 50 gp |
| Alchemist's fire | 50 gp | Acid (vial) | 25 gp |

Mounts and vehicles: donkey 8 gp, mule 8 gp, horse (riding) 75 gp, horse (war) 400 gp, saddle (riding) 10 gp, saddle (war) 60 gp, carriage 100 gp, cart 15 gp, wagon 35 gp, ship (galley) 30,000 gp, ship (keelboat) 3,000 gp.

**Services:** inn common 2 cp, inn private 5 cp to 2 gp, bath (public) 2 cp, bath (private) 1 sp, hireling (untrained) 2 sp/day, hireling (trained) 2 gp/day, scribe 2 gp/day, lawyer 10 gp/day.

**A skilled hireling is the most expensive "item" in the game for low-level parties.** A 1st-level party trying to hire a 1st-level wizard for a day (2 gp) will think twice.

### Shop Types — What They Stock

- **General store:** Rations, rope, lanterns, oil, bedrolls, backpacks, basic tools, soap. Maybe one or two common magic items (potion of healing, driftglobe).
- **Weaponsmith:** All SRD martial and simple weapons, possibly masterwork versions of common ones, arrows/bolts in bulk. Rare: 1 to 3 uncommon weapons (a +1 dagger, a +1 longsword, sun blade) behind the counter.
- **Armorsmith:** All SRD armor types, shields. Rare: 1 to 2 uncommon items (a +1 shield, a suit of elven chain). Plate is always expensive and sometimes requires an order.
- **Alchemist / Apothecary:** Potion of healing (common), potion of climbing (common), potion of greater healing (uncommon), alchemist's fire, acid, antitoxin, healing kits. A city alchemist might have a couple of rare potions.
- **Magic shop (small town):** Common potions, possibly 1 to 2 uncommon scrolls or wands.
- **Magic shop (city):** Common and uncommon, plus 1 to 3 rare items (with quest hooks attached). May have 1 very rare item "for the right buyer."
- **Black market:** Anything, but prices are ×2 to ×5 SRD and the shop is in a hidden location with multiple exits.

### Worked Example Shop

**Old Maren's Chandlery & Sundries** (general store, village of Saltcliff).

- **Sheet type:** `shop` (type: `general`)
- **Linked location:** `Saltcliff - Village Square`
- **Linked NPC:** `Old Maren` (owner, gruff ex-fisherman)
- **Settlement multiplier:** ×1.5 (village)
- **Inventory:** Use `linkToCompendium: true` and the SRD UUIDs (the `compendium-search-first` skill does the lookup). Sample:
  - Rope, hempen (50 ft) — 1 gp, ×1.5 = 1 gp 5 sp
  - Rations (1 day) — 2 sp, ×1.5 = 3 sp
  - Torch (6 pack) — 1 cp, ×1.5 = 2 cp
  - Hooded lantern — 5 gp, ×1.5 = 7 gp 5 sp
  - Oil (flask) — 1 sp, ×1.5 = 2 sp
  - Bedroll — 1 gp, ×1.5 = 1 gp 5 sp
  - Backpack — 2 gp, ×1.5 = 3 gp
  - Antitoxin (vial) — 50 gp, ×1.5 = 75 gp
  - Potion of healing — 50 gp, ×1.5 = 75 gp
- **Special items:** None — this is a village chandlery. Anything more interesting is "in town" (the next settlement over).
- **Open hours:** Dawn to dusk. Closed on high-tide mornings (Maren fishes).
- **House rule:** "If you break it, you buy it. If you steal it, Maren knows before you reach the door."

## Encounter Scaling

Encounter scaling in 5e is **XP-based, not CR-based**. CR is a quick proxy; XP is the actual math. Use the XP tables to size encounters before you size monsters.

### XP by Monster CR (SRD)

| CR | XP | CR | XP | CR | XP |
|----|----|----|----|----|-----|
| 0 | 10 | 6 | 2,300 | 16 | 15,000 |
| 1/8 | 25 | 7 | 2,900 | 17 | 18,000 |
| 1/4 | 50 | 8 | 3,900 | 18 | 20,000 |
| 1/2 | 100 | 9 | 5,000 | 19 | 22,000 |
| 1 | 200 | 10 | 5,900 | 20 | 25,000 |
| 2 | 400 | 11 | 7,200 | 21 | 33,000 |
| 3 | 700 | 12 | 8,400 | 22 | 41,000 |
| 4 | 1,100 | 13 | 10,000 | 23 | 50,000 |
| 5 | 1,800 | 14 | 11,500 | 24 | 62,000 |
| | | 15 | 13,000 | 25-30 | 75,000-155,000 |

**Adjust for monster count:** the encounter's "effective XP" is `base XP × multiplier` where the multiplier depends on how many monsters the party faces:

| Number of Monsters | XP Multiplier |
|-------------------|---------------|
| 1 | ×1.0 |
| 2 | ×1.5 |
| 3-6 | ×2.0 |
| 7-10 | ×2.5 |
| 11-14 | ×3.0 |
| 15+ | ×4.0 |

So **four CR 1 monsters (4 × 200 = 800 XP) actually count as 1,600 XP adjusted** against the party's threshold.

### XP Thresholds by Party Level (4 PCs)

These are the SRD thresholds for a **party of 4**. For a different party size, multiply each threshold by `party_size / 4`.

| Party Level | Easy | Medium | Hard | Deadly |
|-------------|------|--------|------|--------|
| 1 | 250 | 500 | 750 | 1,000 |
| 2 | 250 | 500 | 750 | 1,000 |
| 3 | 350 | 700 | 1,050 | 1,400 |
| 4 | 500 | 1,000 | 1,500 | 2,100 |
| 5 | 600 | 1,200 | 1,800 | 2,500 |
| 6 | 800 | 1,600 | 2,400 | 3,200 |
| 7 | 1,000 | 2,000 | 3,000 | 4,200 |
| 8 | 1,200 | 2,400 | 3,600 | 4,800 |
| 9 | 1,400 | 2,800 | 4,200 | 5,400 |
| 10 | 1,600 | 3,200 | 4,800 | 6,400 |
| 11 | 1,800 | 3,600 | 5,400 | 7,200 |
| 12 | 2,000 | 4,000 | 6,000 | 8,000 |
| 13 | 2,200 | 4,400 | 6,600 | 8,800 |
| 14 | 2,500 | 5,000 | 7,500 | 10,000 |
| 15 | 2,800 | 5,600 | 8,400 | 11,200 |
| 16 | 3,200 | 6,400 | 9,600 | 12,800 |
| 17 | 3,600 | 7,200 | 10,800 | 14,400 |
| 18 | 4,000 | 8,000 | 12,000 | 16,000 |
| 19 | 4,500 | 9,000 | 13,500 | 18,000 |
| 20 | 5,000 | 10,000 | 15,000 | 20,000 |

For 5 PCs, multiply each threshold by 1.25. For 3 PCs, multiply by 0.75.

### How to Build a "Deadly" Encounter

For a **party of 4 at level 5**, the deadly threshold is **2,500 XP**. To hit it:

- **One big monster:** 1 × CR 5 (1,800 XP × 1.0 = 1,800 — too soft). 1 × CR 6 (2,300 × 1.0 = 2,300 — close, but soft). 1 × CR 7 (2,900 × 1.0 = 2,900 — *deadly*). The classic "boss fight."
- **Two mid monsters:** 2 × CR 5 (1,800 × 1.5 = 2,700 — *deadly*).
- **Four small monsters:** 4 × CR 3 (2,800 × 2.0 = 5,600 — *way over deadly*). A "deadly swarm."
- **Mixed:** 1 × CR 5 (1,800) + 2 × CR 2 (400 × 1.5 = 600) = 2,400 — *medium*. Or 1 × CR 7 (2,900) + 2 × CR 1 (400 × 1.5 = 600) = 3,500 — *deadly, with minions*.

**Rule of thumb for "deadly":** 1 monster at the party's level + 2 = a clean deadly fight. 1 monster at level + 4 = a TPK risk.

### 5.1e (2024) Note: Encounter Math Changes

The 2024 / 5.1e rules tweaked encounter math slightly:

- **CR → XP** is unchanged.
- **Creature count multiplier** is unchanged.
- **Party thresholds** shifted a small amount in both directions depending on the level (e.g., level 5 deadly is 2,500 in 2014 and 2,400 in 5.1e, level 10 deadly is 6,400 in 2014 and 5,900 in 5.1e — small shifts, no redesigns needed).
- **The "six encounters per long rest" guideline** is gone in 5.1e; encounters are budgeted per long rest still, but the explicit 6/day heuristic was dropped.

When in doubt, **defer to the SRD 5.1e values** (which is what the Foundry `dnd5e` system v3+ ships with).

## Item Rarity & Pricing

5e uses a five-tier rarity system (plus **artifact** as a sixth). Each tier implies a level of power, a price range, and a narrative weight.

### Rarity Tiers (5e standard)

| Rarity | Power | Price Range | Where It Shows Up |
|--------|-------|-------------|-------------------|
| **Common** | Slight, utility | 50–100 gp | Town shops, loot drops, starting gear. |
| **Uncommon** | Solid, +1, single useful ability | 200–500 gp | City shops, level 1+ treasure, quest rewards. |
| **Rare** | Powerful, +2, two abilities | 2,000–5,000 gp | Level 5+ treasure, requires a quest hook. |
| **Very rare** | Strong, +3, multi-ability | 20,000–50,000 gp | Level 11+ treasure, end of campaign milestones. |
| **Legendary** | Defining, +3, multiple abilities | 100,000+ gp | Endgame, dragon hoards, divine gifts. |
| **Artifact** | World-altering | Priceless | Plot device. |

### Attunement

A magic item may require **attunement** (a short ritual). A character can be attuned to at most **three magic items** at a time (5.1e). When generating items:

- Common items usually don't require attunement.
- Uncommon items sometimes do (about 30%).
- Rare and above almost always do.

### Common SRD Magic Items (Reference)

- **Potion of healing** — 2d4+2 HP, common, 50 gp.
- **Potion of greater healing** — 4d4+4 HP, uncommon, 200 gp.
- **Potion of superior healing** — 8d4+8 HP, rare, 2,000 gp.
- **Potion of supreme healing** — 10d4+20 HP, very rare, 22,000 gp.
- **Scroll of *identify*** — common, 75 gp.
- **Scroll of *fireball*** — rare, 2,500 gp.
- **+1 weapon** — uncommon, 500 gp typical.
- **+2 weapon** — rare, 4,000 gp typical.
- **+3 weapon** — very rare, 25,000 gp typical.
- **Bag of holding** — uncommon, 500 gp.
- **Cloak of protection** — uncommon, 500 gp.
- **Gauntlets of ogre power** — uncommon, 500 gp.
- **Headband of intellect** — uncommon, 500 gp.
- **Boots of elvenkind** — uncommon, 500 gp.
- **Wand of magic missiles** — uncommon, 500 gp.
- **Wand of fireballs** — rare, 4,000 gp.
- **Ring of protection** — rare, 4,000 gp.
- **Cloak of displacement** — rare, 4,000 gp.
- **Holy avenger** — legendary (paladin only), 100,000+ gp.
- **Vorpal sword** — legendary, 100,000+ gp.
- **Defender** — legendary, 100,000+ gp.
- **Deck of many things** — legendary (or rare by some readings), 50,000+ gp — and the GM may need to talk the player out of it.

**If the item the user wants is in the SRD, use the SRD version. Don't reskin +1 weapons.** The `compendium-search-first` skill covers how to look up compendium UUIDs.

### Pricing Caveats

- **Negotiation:** the SRD price is a baseline, not a fixed shelf price. Haggling is part of the game.
- **Scarcity:** in a remote village, a single uncommon item might cost 1,000 gp; in a metropolis, the same item might be 250 gp.
- **Reputation:** a PC who saved the merchant's daughter gets the SRD price; a PC who threatened the merchant gets ×3.
- **Genuinely priceless items don't get priced** — they get quested for.

## Voice & Naming

This is the **lore skill**. A well-priced stat block with a generic name still feels like a template. Names and voices are what make a world *felt*.

### Cultural Naming Conventions

#### Dwarvish

- **First names** are 1–2 syllables + 1–2 syllables, often starting with a hard consonant and ending in a vowel or a stop. Examples: *Bardin, Thorin, Kildrak, Helga, Dagnal, Vondal, Harbek.* Male and female names both use these patterns; suffix softens female names slightly (*-ra, -la, -na*).
- **Family names / clan names** are typically **occupation- or place-based**: *Stoneforge, Ironbeard, Goldhand, Hammerhold, Deepdelve, Anvilshade, Wyrmslayer.* Some are epithets earned: *the Black, the Patient, the Twice-Drowned.*
- **Voice pattern:** Measured, formal, values contracts and oaths. Long pauses before answering. Says "I will think on it" instead of "I don't know." Quotes one's ancestors by name. Strongly uses "kin," "clan," "debt."

#### Elven (high / wood / drow, varies)

- **First names** are 2–4 syllables, vowel-heavy, often with apostrophes or soft sibilants. *Elandar, Lirael, Aelwyn, Thalion, Faelyn, Syllin, Vhaeraun.* Drow names have sharper consonants: *Veyl, Phaere, Drizzt, Jarlaxle, Ilphuin.*
- **Family names** are typically **epithets earned by deed or station**: *Sunshadow, Moonwhisper, Starbreeze, Nightbough, Frostpetal.* Drow use House names: *House Do'Urden, House Baenre, House Melarn.*
- **Voice pattern:** High elves speak slowly, with long clauses, in formal cadences. Wood elves use shorter sentences with nature metaphors. Drow use honorifics and house names in every other sentence.

#### Halfling

- **First names** are 1–2 syllables, often ending in a vowel, sound cheerful. *Pip, Merry, Pippin, Roscoe, Belba, Lyle, Cora, Tilly, Milo.*
- **Family names** are **plainly descriptive and often humorous**: *Underhill, Goodbarrel, Tealeaf, Greenbottle, High-hill, Brushgather.* The Tealeafs are openly a thief family.
- **Voice pattern:** Warm, talkative, often tells stories. Asks questions back. Uses food as a metaphor for everything ("that rumor tastes fishy"). Says "I shouldn't say" right before saying it.

#### Human (regional)

- **Coastal / salt folk:** names with hard consonants and sea references. *Vaelen, Korrick, Maren, Darrow.* Family names are occupation or location: *Kett, Saltcliffe, Stormway, Tideborn.*
- **Northern / mountain folk:** Norse-flavored. *Asgeir, Brynja, Eirik, Sigrid, Halvar.* Family names: *Stormbjorn, Ironside, Frostbeard.*
- **Desert / southern:** Arabic-flavored. *Jalil, Farid, Safiya, Rashid, Zaynab.* Family names: *al-Saif, al-Khalil, ibn Harith.*
- **River / heartland:** Anglo-Saxon flavored. *Edwin, Hilde, Aelfric, Godwin, Wynn, Wulfhere.* Family names: *Thornbury, Ashford, Fairchild, Marshwell.*

#### Other Races

- **Dragonborn:** First names are a single clan name in full: *Dremasu, Kava, Korin, Vezzri, Nala.* Last name is the clan: *Clethtinthiallor, Daardendrian.* The full name is the clan; the given name is the personal name. Voice pattern: clipped, formal, honor-bound.
- **Tiefling:** Infernal-flavored. *Akmenos, Barakas, Damakos, Iados, Kairon, Melech, Mordai.* Voice pattern: varies, but often sardonic, self-deprecating about horns, low register.
- **Goliath:** Short, hard, ceremonial. *Aukan, Eglath, Gae-Al, Gauthak, Ilikan, Keothi, Kuori, Lo-Kag, Manneo, Nalla, Orilo, Paavu, Pethani, Thalai, Uthgardt, Vola, Volen, Vorkah.* Voice pattern: terse, action-first, names every challenge by its strongest feature.
- **Orc / half-orc:** Guttural. *Dench, Feng, Gell, Henk, Holg, Imsh, Keth, Krull, Mhurren, Ront, Shump, Thokk.* Voice pattern: direct, no euphemism, proud of scars.

### Voice Patterns by NPC Type

These are the **speech tells** — the patterns that make a character sound distinct at the table.

- **Pirate / sailor:** Drops articles. "Seen her off Cape Wrath, I have." Always quoting the ship by name. Uses "aye" as punctuation. "Cap'n" and "mate" for everyone. Refers to the ocean as a person ("she's angry today").
- **Scholar / wizard:** Long subordinate clauses. Precise vocabulary, often mildly off — "the *humoral* balance of the artifact" instead of "the magical thing." Quotes dead authors. Asks the player to repeat themselves, then corrects them.
- **Noble:** "I" replaced with "we." Uses titles even of close friends. Speaks about servants in the third person ("the staff will show you out"). Soft consonants, trailing off at the end of sentences.
- **Commoner:** Direct, often rude. Calls the PC "stranger" or by physical feature ("you, with the shield"). Asks the PC's business in the second sentence. Speaks in concrete nouns — no abstractions.
- **Cultist:** Whispers. Uses "the master" without naming. Speaks in passive voice ("it has been written that..."). Eats sparingly in front of the party.
- **Soldier / veteran:** Terse. Reports before opinions. Says "sir" or "captain" reflexively. Uses military jargon ("in the second watch we had contact").
- **Spy / smuggler:** Friendly, slightly too friendly. Asks questions the PC didn't ask. Calls everyone "friend." Mirrors the PC's last three words back.
- **Clergy:** Formally polite. Quotes scripture. Pauses before answering questions. Uses "child" for everyone. Refers to the deity in the third person ("the goddess teaches us...").

### Worldbuilding Hooks (Taverns, Inns, Roads)

The difference between a forgettable tavern and a memorable one is **three specific, sensory details**. Use this checklist when generating any location:

#### A Tavern Feels Lived-In When...

- The **light source** is specific: a blackened chandelier, a fire in a stone hearth, three candles on every table. "Generic medieval lighting" is not a detail.
- The **smell** is specific: woodsmoke, bread baking, spilled ale, dog, salt air. Pick one and lean in.
- **Something is broken** but still being used: a chair with a different leg, a tankard repaired with wire, a window patched with oiled hide. This is a story.
- **Someone's personal item is on display** behind the bar: a captain's spyglass, a child's shoe, a lock of hair in a locket. The innkeeper is a person with a past.
- **The "regulars" are sketched**: a one-eyed fisherman, a woman in widow's black, two dockhands playing dice. Not by name; by silhouette.
- **The price list is on the wall**, not in a hidden menu. And it has one or two weird items ("fish stew, 3 cp / advice, free / looking at the barmaid, 1 gp").
- **A story is mid-conversation** when the party walks in, and stops. The barkeep answers with "you don't want to know" or "ask him" and points to a corner.

A tavern generated with all of those will outlive the campaign.

## Common Pitfalls

These are the mistakes the agent is most likely to make. Flag them at authoring time.

1. **Over-powered NPCs.** A "town blacksmith" with a +3 warhammer is broken. Use the rarity tiers — uncommon for level 1–4 treasure, rare for 5–10, very rare for 11–16, legendary for 17+. A village blacksmith should have a masterwork longsword at best.
2. **Under-powered encounters.** "Deadly" by the math means the party will likely have one or two characters drop. If the GM wants "challenging but not lethal," target **hard** (75% of deadly) for a boss fight, or **medium** for a random encounter.
3. **Generic names.** "John Smith" is not a 5e NPC. Use the cultural naming conventions above. If you can't decide, pick a culture and lean in: a half-orc pirate named "John Smith" is a bug; a half-orc pirate named "Thokk the Black" is a feature.
4. **Wrong settlement economy.** A village general store stocking a +2 weapon is wrong. A metropolis magic-shop with no rare items is also wrong. Match the shop's stock to the settlement size.
5. **Hoarding magic items.** If every shop has a +1 weapon, the +1 weapon stops feeling special. Most shops should have **one** item of slightly above their station ("for the right buyer"), not a wall of glowy swords.
6. **NPCs with no motivation.** "He's a merchant who sells things" is not a motivation. Every NPC wants something. The motivation is what makes them interesting when the party talks to them for more than thirty seconds.
7. **NPCs with too many traits.** A 12-trait NPC is a protagonist. Stick to two-to-three.
8. **Forgetting `parentLocation`.** The Drowned Lantern should sit inside Saltcliff - Dock Ward. A location without a parent is a floating node — it doesn't connect to anything.
9. **Inventing items that exist in the SRD.** Don't write "a long, two-handed sword that deals 2d6 slashing." That's a greatsword, and the SRD has it with full stats. Use the compendium.
10. **Voice-bleed.** Every pirate doesn't need to say "arr." Every noble doesn't need to drop h's. Pick **one** verbal tic and use it; the rest is just being a person.
11. **Combat-stating non-combatants.** A shopkeeper with a `bandit captain` stat block is either a setup (the shopkeeper is secretly a smuggler-captain) or a bug. Make sure the stat block matches the role.
12. **The 18/00 ability score trap.** A "20 STR" commoner is funny once and then breaks the world. Keep NPCs in the SRD ranges (10–14 common, 14–17 trained, 18 + heroic).
13. **Pricing the unpriced.** A "rare magic item" in a shop needs a price, but a "holy avenger" should not have "100,000 gp" on the menu — it should have "quest required." Use the rarity tier, then override with narrative weight.

## Verification Checklist

Before committing any 5e content to a CC sheet, verify:

- [ ] NPC has a stat block **or** a clear "no combat" note — not both vaguely.
- [ ] NPC has **2–3 memorable traits**, not 1, not 10.
- [ ] NPC has a **primary motivation** and, ideally, a **secret** in the second register.
- [ ] NPC's **voice** is one verbal tic + a baseline speech pattern, not a costume.
- [ ] NPC's **name matches their culture** (use the cultural conventions above).
- [ ] Location's **settlement size** is named and matches the buildings/services listed.
- [ ] Location has a **parent location** unless it's a top-level region.
- [ ] Every building has a **front-of-house and a back-of-house** sketched.
- [ ] Shop's **settlement multiplier** has been applied to all base prices.
- [ ] Shop's stock matches the **shop type and settlement size**.
- [ ] All **magic items** in the shop reference the **SRD compendium** by UUID (use the `compendium-search-first` skill).
- [ ] Encounter's **adjusted XP** is between the **hard** and **deadly** thresholds for the party (for a boss), or **medium** (for a random encounter).
- [ ] Encounter's **monster count** was used to apply the XP multiplier.
- [ ] Item's **rarity tier** matches the campaign level (uncommon for 1–4, rare for 5–10, etc.).
- [ ] Item's **price** is within the SRD range for its rarity (or explicitly justified as a markup).
- [ ] Any **attunement** flag is set if the item requires it.
- [ ] All **names** have been checked against the cultural naming conventions for plausibility.
- [ ] **Sensory details** (light, smell, sound) appear in the prose for any tavern, temple, or major location.

## Related Skills

- **`campaign-codex-sheets`** — the schema for putting the content this skill produces into CC's flag-based sheets. Load this skill **alongside** `dnd5e-content-authoring` whenever generating a sheet.
- **`compendium-search-first`** — how to look up SRD items, monsters, and spells in the Foundry compendium by UUID. Use it whenever a sheet would otherwise reference an item by name; link to the compendium version instead.
- **`world-context-linking`** — how to wire generated content into the user's existing world (linking NPCs to locations, quests to NPCs, etc.) without creating duplicate or orphan nodes.
- **`foundry-vtt-v14-api`** (module-level) — for the `JournalEntry.create()` and `actor.createEmbeddedDocuments()` calls that actually commit sheets to the world.
