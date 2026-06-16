/**
 * World context: in-memory snapshot of all Campaign Codex sheets and NPC actors
 * in the current world. Used as context for the AI agent, and as the source
 * for the "link to existing" picker in the designer UI.
 *
 * Refreshed:
 *   - on the `ready` hook (self-registered when this module loads)
 *   - on journal/actor create/update/delete (debounced 5s)
 */

import { SHEET_TYPES } from "./constants.js";

const REFRESH_DEBOUNCE_MS = 5000;
/** Soft payload cap. Above this we trim fields and warn. */
const PAYLOAD_BUDGET_BYTES = 50 * 1024;

function debounce(fn, wait) {
  let t = null;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), wait);
  };
}

function makeEmptySheets() {
  const o = {};
  for (const t of SHEET_TYPES) o[t] = [];
  return o;
}

export const WorldContext = {
  /** @type {?{ sheets:object, npcActors:object[], scannedAt:number }} */
  cache: null,

  // ---------------------------------------------------------------------------
  // Scanning
  // ---------------------------------------------------------------------------

  /**
   * Re-scan the world and rebuild the cache. Safe to call repeatedly.
   * @returns {Promise<{sheets:object, npcActors:object[], scannedAt:number}>}
   */
  async refresh() {
    const sheets = makeEmptySheets();
    const npcActors = [];

    try {
      // Campaign Codex sheets — journals with flags['campaign-codex']?.sheetType
      const journals = (game.journal?.contents ?? []);
      for (const j of journals) {
        const st = j.flags?.["campaign-codex"]?.sheetType;
        if (!st) continue;
        if (!sheets[st]) sheets[st] = []; // unknown sheet types get their own bucket
        sheets[st].push({
          uuid: j.uuid,
          id: j.id,
          name: j.name,
          type: j.flags["campaign-codex"]?.type ?? null,
          sheetType: st,
          tags: Array.from(j.flags["campaign-codex"]?.tags ?? []),
          parentLocation: j.flags["campaign-codex"]?.parentLocation ?? null,
          denizens: Array.from(j.flags["campaign-codex"]?.denizens ?? []),
          linkedNpcs: Array.from(j.flags["campaign-codex"]?.linkedNpcs ?? []),
          img: j.img ?? null,
          updatedTime: j._stats?.modifiedTime ?? null,
        });
      }

      // NPC actors
      const actors = (game.actors?.contents ?? []).filter((a) => a.type === "npc");
      for (const a of actors) {
        npcActors.push({
          uuid: a.uuid,
          id: a.id,
          name: a.name,
          level: a.system?.details?.level?.value ?? null,
          race: a.system?.details?.race ?? null,
          img: a.img ?? null,
        });
      }
    } catch (err) {
      console.warn("fvtt-cc-generator | WorldContext.refresh failed:", err);
    }

    this.cache = { sheets, npcActors, scannedAt: Date.now() };
    return this.cache;
  },

  /** Return the cached snapshot, refreshing if it has never been built. */
  snapshot() {
    if (!this.cache) return this.refresh();
    return this.cache;
  },

  // ---------------------------------------------------------------------------
  // Search
  // ---------------------------------------------------------------------------

  /**
   * Case-insensitive partial match on name (and tags for CC sheets).
   *
   * @param {string} query
   * @param {?string} typeFilter  sheet type, "actor"/"npc", or null for all
   * @returns {Array<{uuid:string, name:string, type:?string, sheetType:string, tags:Array<string>}>}
   */
  search(query, typeFilter = null) {
    const cache = this.snapshot();
    const q = String(query ?? "").trim().toLowerCase();
    if (!q) return [];

    const matches = (text) => String(text ?? "").toLowerCase().includes(q);
    const tagMatches = (tags) => Array.isArray(tags) && tags.some((t) => matches(t));

    /** @type {Array<{uuid:string,name:string,type:?string,sheetType:string,tags:Array<string>}>} */
    const out = [];

    // NPC actors
    if (!typeFilter || typeFilter === "actor" || typeFilter === "npc") {
      for (const a of cache.npcActors) {
        if (matches(a.name)) {
          out.push({ uuid: a.uuid, name: a.name, type: "npc", sheetType: "npc", tags: [] });
        }
      }
    }

    // CC sheets
    if (typeFilter !== "actor" && typeFilter !== "npc") {
      const buckets = (typeFilter && cache.sheets[typeFilter])
        ? [cache.sheets[typeFilter]]
        : Object.values(cache.sheets);
      for (const bucket of buckets) {
        for (const s of bucket) {
          if (matches(s.name) || tagMatches(s.tags)) {
            out.push({
              uuid: s.uuid,
              name: s.name,
              type: s.type,
              sheetType: s.sheetType,
              tags: s.tags ?? [],
            });
          }
        }
      }
    }

    return out;
  },

  // ---------------------------------------------------------------------------
  // Payload (token-budgeted for the agent)
  // ---------------------------------------------------------------------------

  /**
   * Build a JSON-friendly, token-budgeted payload suitable for sending to the
   * agent. Trims low-value fields if the total exceeds ~50KB.
   *
   * @returns {{ sheets:object, npcActors:object[] }}
   */
  toPayload() {
    const cache = this.snapshot();

    /** @type {Record<string, Array<object>>} */
    const sheets = {};
    for (const t of SHEET_TYPES) {
      sheets[t] = (cache.sheets[t] ?? []).map((s) => ({
        uuid: s.uuid,
        name: s.name,
        type: s.type,
        sheetType: s.sheetType,
        tags: (s.tags ?? []).slice(0, 16),
        parentLocation: s.parentLocation ?? null,
      }));
    }
    const npcActors = (cache.npcActors ?? []).map((a) => ({
      uuid: a.uuid,
      name: a.name,
      level: a.level,
      race: a.race,
    }));

    let payload = { sheets, npcActors };

    const json = JSON.stringify(payload);
    if (json.length > PAYLOAD_BUDGET_BYTES) {
      console.warn(
        `fvtt-cc-generator | WorldContext payload ${json.length} bytes exceeds ` +
        `${PAYLOAD_BUDGET_BYTES}-byte budget. Trimming tags and dropping low-priority fields.`
      );
      // Drop tags from the payload to save space.
      for (const t of SHEET_TYPES) {
        sheets[t] = sheets[t].map((s) => ({
          uuid: s.uuid,
          name: s.name,
          type: s.type,
          sheetType: s.sheetType,
        }));
      }
      payload = { sheets, npcActors };

      const json2 = JSON.stringify(payload);
      if (json2.length > PAYLOAD_BUDGET_BYTES) {
        // Hard cap: keep only uuid + name on sheets.
        for (const t of SHEET_TYPES) {
          sheets[t] = sheets[t].map((s) => ({ uuid: s.uuid, name: s.name }));
        }
        payload = { sheets, npcActors };
        console.warn(
          `fvtt-cc-generator | WorldContext payload still ` +
          `${JSON.stringify(payload).length} bytes after aggressive trim.`
        );
      }
    }
    return payload;
  },

  // ---------------------------------------------------------------------------
  // Hook registration
  // ---------------------------------------------------------------------------

  /**
   * Install debounced auto-refresh hooks. Called automatically on first
   * `ready`; can also be called manually.
   */
  registerHooks() {
    const debouncedRefresh = debounce(() => {
      this.refresh().catch((err) =>
        console.warn("fvtt-cc-generator | debounced WorldContext refresh failed:", err)
      );
    }, REFRESH_DEBOUNCE_MS);

    Hooks.on("createJournalEntry", debouncedRefresh);
    Hooks.on("updateJournalEntry", debouncedRefresh);
    Hooks.on("deleteJournalEntry", debouncedRefresh);
    Hooks.on("createActor", debouncedRefresh);
    Hooks.on("updateActor", debouncedRefresh);
    Hooks.on("deleteActor", debouncedRefresh);
  },
};

// Self-register: when Foundry is ready, install the hooks and do an initial scan.
// We defer to the `ready` hook so `game.journal` / `game.actors` are populated.
Hooks.once("ready", () => {
  try {
    WorldContext.registerHooks();
    WorldContext.refresh().catch((err) =>
      console.warn("fvtt-cc-generator | initial WorldContext refresh failed:", err)
    );
  } catch (err) {
    console.warn("fvtt-cc-generator | WorldContext init failed:", err);
  }
});
