/**
 * Commit flow: take a designed draft from the agent and write it to the world
 * as a `JournalEntry` with the Campaign Codex flag payload.
 *
 * Exposed via:
 *   - `game.modules.get('fvtt-cc-generator').api.commit(draft, options)` (set up in main.js)
 *   - `Commit.commitDraft(draft, options)` (direct import)
 */

import { SHEET_TYPES } from "./constants.js";

/** Convert a draft's freeform text into the v13/14 `JournalEntryPage` shape. */
function buildPages(draft) {
  if (Array.isArray(draft.pages) && draft.pages.length) {
    return draft.pages.map((p, i) => ({
      name: String(p.name ?? `${draft.name ?? "Page"} ${i + 1}`),
      type: "text",
      text: {
        content: String(p.content ?? p.text ?? ""),
        format: Number(p.format ?? 1), // 1 = HTML in Foundry v13/14
      },
    }));
  }
  if (typeof draft.pageHtml === "string" && draft.pageHtml.length) {
    return [{
      name: draft.name ?? "Notes",
      type: "text",
      text: { content: draft.pageHtml, format: 1 },
    }];
  }
  // Default: a single page containing any freeform description.
  const desc = String(draft.description ?? "");
  return [{
    name: draft.name ?? "Notes",
    type: "text",
    text: { content: desc, format: 1 },
  }];
}

/** Normalise a denizen/linkedNpc entry to `{uuid, name?}`. Accepts string or object. */
function resolveRef(ref) {
  if (!ref) return null;
  if (typeof ref === "string") return { uuid: ref };
  if (typeof ref === "object" && ref.uuid) return { uuid: ref.uuid, name: ref.name ?? null };
  return null;
}

export const Commit = {
  // ---------------------------------------------------------------------------
  // Validation
  // ---------------------------------------------------------------------------

  /**
   * Validate a draft shape before writing.
   * @param {?object} draft
   * @returns {{ valid:boolean, errors:string[] }}
   */
  _validateDraft(draft) {
    const errors = [];
    if (!draft || typeof draft !== "object") {
      return { valid: false, errors: ["draft is not an object"] };
    }
    if (!draft.name || typeof draft.name !== "string" || !draft.name.trim()) {
      errors.push("draft.name is required");
    }
    if (!draft.sheetType) {
      errors.push("draft.sheetType is required");
    } else if (!SHEET_TYPES.includes(draft.sheetType)) {
      errors.push(`draft.sheetType must be one of: ${SHEET_TYPES.join(", ")}`);
    }
    if (draft.tags && !Array.isArray(draft.tags)) {
      errors.push("draft.tags must be an array of strings");
    } else if (Array.isArray(draft.tags)) {
      for (const t of draft.tags) {
        if (typeof t !== "string") { errors.push("draft.tags entries must be strings"); break; }
      }
    }
    if (draft.ownership && typeof draft.ownership !== "object") {
      errors.push("draft.ownership, if present, must be an object");
    }
    return { valid: errors.length === 0, errors };
  },

  // ---------------------------------------------------------------------------
  // Flag payload
  // ---------------------------------------------------------------------------

  /**
   * Build the `flags['campaign-codex']` payload from a draft.
   * @param {object} draft
   * @returns {object}
   */
  _buildFlagPayload(draft) {
    return {
      sheetType: draft.sheetType,
      type: draft.type ?? null,
      tags: Array.isArray(draft.tags)
        ? draft.tags.filter((t) => typeof t === "string")
        : [],
      parentLocation: draft.parentLocation ?? null,
      description: draft.description ?? "",
      denizens: Array.isArray(draft.denizens)
        ? draft.denizens.map(resolveRef).filter(Boolean)
        : [],
      linkedNpcs: Array.isArray(draft.linkedNpcs)
        ? draft.linkedNpcs.map(resolveRef).filter(Boolean)
        : [],
      relatedItems: Array.isArray(draft.relatedItems) ? draft.relatedItems : [],
      hidden: Boolean(draft.hidden),
      journalType: draft.journalType ?? null,
      // Tiny audit trail.
      _generatedBy: "fvtt-cc-generator",
      _generatedAt: Date.now(),
    };
  },

  // ---------------------------------------------------------------------------
  // Public entry
  // ---------------------------------------------------------------------------

  /**
   * Write a designed draft to the world.
   *
   * @param {object} draft  the agent's structured draft
   * @param {{
   *   openInSheet?: boolean,
   *   linkToTOC?: boolean,
   *   autoCreateActors?: boolean,
   *   defaultOwnership?: number,
   * }} [options]
   * @returns {Promise<
   *   | { ok:true,  doc: JournalEntry, uuid:string }
   *   | { ok:false, error:string, errors?:string[] }
   * >}
   */
  async commitDraft(draft, options = {}) {
    try {
      const v = this._validateDraft(draft);
      if (!v.valid) {
        const msg = `Invalid draft: ${v.errors.join("; ")}`;
        try { ui.notifications?.error?.(`FVTT-CC-Generator: ${msg}`); } catch (_) { /* ignore */ }
        return { ok: false, error: msg, errors: v.errors };
      }

      const flagPayload = this._buildFlagPayload(draft);
      const pages = buildPages(draft);

      /** @type {object} */
      const createData = {
        name: String(draft.name).trim(),
        pages,
        flags: { "campaign-codex": flagPayload },
        // Default to GM-only ownership; the user can adjust in the sheet.
        ownership: { default: options.defaultOwnership ?? 0 },
        // Imported / AI-generated entries start hidden until the user reveals them.
        hidden: flagPayload.hidden === true,
      };

      // Allow the draft to override ownership or visibility explicitly.
      if (draft.ownership && typeof draft.ownership === "object") {
        createData.ownership = draft.ownership;
      }
      if (typeof draft.hidden === "boolean") {
        createData.hidden = draft.hidden;
      }

      const doc = await JournalEntry.create(createData);
      if (!doc) throw new Error("JournalEntry.create returned no document");

      // Optional: open the CC sheet for this entry.
      if (options.openInSheet) {
        try {
          const cc = game.modules?.get("campaign-codex");
          const api = cc?.api ?? cc?.public?.api;
          if (api && typeof api.openJournalEntrySheet === "function") {
            await api.openJournalEntrySheet(doc);
          } else if (typeof doc.sheet?.render === "function") {
            doc.sheet.render(true);
          }
        } catch (err) {
          console.warn("fvtt-cc-generator | openInSheet failed:", err);
        }
      }

      // Optional: link to the Campaign Codex TOC.
      if (options.linkToTOC) {
        try {
          const cc = game.modules?.get("campaign-codex");
          const api = cc?.api ?? cc?.public?.api;
          if (api && typeof api.addToTOC === "function") {
            await api.addToTOC(doc, draft.sheetType);
          }
        } catch (err) {
          console.warn("fvtt-cc-generator | linkToTOC failed:", err);
        }
      }

      // Optional: auto-create NPC actors for denizens that don't yet exist.
      // We do NOT silently spawn malformed actors — the lightweight pass below
      // only logs missing references so the user can flesh them out in Foundry.
      if (options.autoCreateActors && Array.isArray(draft.denizens)) {
        for (const ref of draft.denizens) {
          const uuid = typeof ref === "string" ? ref : ref?.uuid;
          if (!uuid) continue;
          try {
            const existing = await fromUuid(uuid);
            if (existing) continue;
            console.log(
              `fvtt-cc-generator | denizen ${uuid} does not exist; ` +
              `create it manually in Foundry to link it to ${doc.name}.`
            );
          } catch (_) { /* not found — that's expected */ }
        }
      }

      try {
        ui.notifications?.info?.(
          `FVTT-CC-Generator: Created "${doc.name}" (${draft.sheetType}).`
        );
      } catch (_) { /* ignore */ }

      return { ok: true, doc, uuid: doc.uuid };
    } catch (err) {
      const msg = err?.message ?? String(err);
      console.error("fvtt-cc-generator | commitDraft failed:", err);
      try {
        ui.notifications?.error?.(`FVTT-CC-Generator: Commit failed — ${msg}`);
      } catch (_) { /* ignore */ }
      return { ok: false, error: msg };
    }
  },
};
