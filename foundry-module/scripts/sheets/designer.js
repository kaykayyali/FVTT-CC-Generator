/**
 * AI Designer — a Foundry ApplicationV2 popout that drives the
 * "design -> preview -> refine -> commit" loop with the local Hermes agent.
 *
 * Template: `modules/fvtt-cc-generator/templates/designer.hbs`
 */

import { getSettings } from "../lib/settings.js";
import { WsClient } from "../lib/ws-client.js";
import { WorldContext } from "../lib/world-context.js";
import { Commit } from "../lib/commit.js";
import {
  MODULE_ID,
  SHEET_TYPES,
  SHEET_TYPE_LABELS,
  SHEET_TYPE_ICONS,
} from "../lib/constants.js";

const { HandlebarsApplicationMixin } = foundry.applications.api;

export class DesignerApp extends HandlebarsApplicationMixin(foundry.applications.api.ApplicationV2) {
  // ---------------------------------------------------------------------------
  // Static config
  // ---------------------------------------------------------------------------

  static DEFAULT_OPTIONS = {
    id: "fvtt-cc-designer",
    classes: ["fvtt-cc-designer", "application"],
    window: {
      title: "AI Designer (Campaign Codex)",
      icon: "fa-wand-magic-sparkles",
    },
    position: { width: 480, height: 760 },
    resizable: true,
  };

  static PARTS = {
    form: { template: "modules/fvtt-cc-generator/templates/designer.hbs" },
  };

  // ---------------------------------------------------------------------------
  // Instance state
  // ---------------------------------------------------------------------------

  /** @type {?WsClient} */
  _client = null;
  /** @type {?string} */
  currentSessionId = null;
  /** @type {?object} */
  currentDraft = null;
  /** @type {Array<() => void>} */
  _unsubs = [];
  /** @type {string} */
  _thinkingText = "";
  /** @type {boolean} */
  _clientInitStarted = false;

  // ---------------------------------------------------------------------------
  // Context
  // ---------------------------------------------------------------------------

  _prepareContext(_options) {
    const sheetTypes = SHEET_TYPES.map((value) => ({
      value,
      label:
        (typeof game.i18n?.localize === "function"
          ? game.i18n.localize(`FAB.SheetType.${value}`)
          : null) ??
        SHEET_TYPE_LABELS[value] ??
        value,
      icon: SHEET_TYPE_ICONS[value] ?? "fa-file",
    }));

    const settings = getSettings();
    const cache = WorldContext.snapshot?.() ?? null;
    const hasContext = !!(
      cache &&
      ((cache.npcActors?.length ?? 0) > 0 ||
        Object.values(cache.sheets ?? {}).some((b) => (b?.length ?? 0) > 0))
    );

    let agentStatus = "disconnected";
    if (this._client?.ws) {
      if (this._client.ws.readyState === WebSocket.OPEN) agentStatus = "connected";
      else if (this._client.ws.readyState === WebSocket.CONNECTING) agentStatus = "connecting";
    }

    return {
      sheetTypes,
      defaults: { sheetType: SHEET_TYPES[0], prompt: "" },
      agentStatus,
      hasContext,
      sheetTypeLabel: SHEET_TYPE_LABELS,
      sheetTypeIcon: SHEET_TYPE_ICONS,
      agentUrl: settings.url,
    };
  }

  // ---------------------------------------------------------------------------
  // Render lifecycle
  // ---------------------------------------------------------------------------

  _onRender(_context, _options) {
    const root = this.element;
    if (!root) return;

    // Lazily connect to the agent the first time we render.
    this._ensureClient().catch((err) =>
      console.warn("fvtt-cc-generator | designer client init:", err)
    );

    this._wireSheetType(root);
    this._wireDesign(root);
    this._wireRefine(root);
    this._wireCommit(root);
    this._wireLink(root);
    this._wirePromptBox(root);

    // Re-render the preview pane if we already have a draft in memory.
    if (this.currentDraft) this._renderPreview();
  }

  _wireSheetType(root) {
    const select = root.querySelector("#fab-sheet-type");
    if (!select) return;
    select.addEventListener("change", (ev) => {
      this.currentDraft = {
        ...(this.currentDraft ?? {}),
        sheetType: ev.target.value,
      };
    });
  }

  _wirePromptBox(root) {
    const ta = root.querySelector("#fab-prompt");
    if (!ta) return;
    ta.addEventListener("input", () => {
      ta.style.height = "auto";
      ta.style.height = `${Math.min(ta.scrollHeight, 320)}px`;
    });
  }

  _wireDesign(root) {
    const btn = root.querySelector("#fab-design-btn");
    if (!btn) return;
    btn.addEventListener("click", async (ev) => {
      ev.preventDefault();
      const prompt = root.querySelector("#fab-prompt")?.value?.trim() ?? "";
      const sheetType =
        root.querySelector("#fab-sheet-type")?.value ?? SHEET_TYPES[0];
      if (!prompt) {
        ui.notifications?.warn?.("FVTT-CC-Generator: Please enter a prompt first.");
        return;
      }
      try {
        const client = await this._ensureClient();
        // Clean up any prior session listeners.
        this._dropHandlers();

        const ctx = WorldContext.toPayload();
        const { sessionId } = await client.design({
          docType: sheetType,
          prompt,
          context: ctx,
        });
        this.currentSessionId = sessionId;
        this.currentDraft = { sheetType, name: "", description: prompt };

        this._thinkingText = "";
        this._setThinking("Designing…");
        this._setPreview("<p class='fab-pending'>Waiting for the agent's first draft…</p>");

        this._unsubs.push(
          client.on("design.thinking", (msg) => this._onThinking(msg))
        );
        this._unsubs.push(
          client.on("design.preview", (msg) => this._onPreview(msg))
        );
        this._unsubs.push(
          client.on("design.error", (msg) => this._onDesignError(msg))
        );
        this._unsubs.push(
          client.on("design.committed", (msg) => this._onCommitted(msg))
        );

        ui.notifications?.info?.(
          `FVTT-CC-Generator: Design session started (${sessionId ?? "—"}).`
        );
      } catch (err) {
        const msg = err?.message ?? String(err);
        console.error("fvtt-cc-generator | design.start failed:", err);
        ui.notifications?.error?.(`FVTT-CC-Generator: Design failed — ${msg}`);
      }
    });
  }

  _wireRefine(root) {
    const btn = root.querySelector("#fab-refine-btn");
    if (!btn) return;
    btn.addEventListener("click", async (ev) => {
      ev.preventDefault();
      if (!this.currentSessionId) {
        ui.notifications?.warn?.(
          "FVTT-CC-Generator: No active session. Click Design first."
        );
        return;
      }
      const feedback =
        root.querySelector("#fab-refine-input")?.value?.trim() ?? "";
      if (!feedback) {
        ui.notifications?.warn?.("FVTT-CC-Generator: Please describe what to change.");
        return;
      }
      try {
        const client = await this._ensureClient();
        await client.refine({ sessionId: this.currentSessionId, feedback });
        this._setThinking("Refining…");
        const ri = root.querySelector("#fab-refine-input");
        if (ri) ri.value = "";
      } catch (err) {
        ui.notifications?.error?.(
          `FVTT-CC-Generator: Refine failed — ${err?.message ?? err}`
        );
      }
    });
  }

  _wireCommit(root) {
    const btn = root.querySelector("#fab-commit-btn");
    if (!btn) return;
    btn.addEventListener("click", async (ev) => {
      ev.preventDefault();
      if (!this.currentDraft) {
        ui.notifications?.warn?.("FVTT-CC-Generator: Nothing to commit yet.");
        return;
      }
      try {
        const result = await Commit.commitDraft(this.currentDraft, {
          openInSheet: true,
        });
        if (result.ok) {
          // Tell the agent we're done so it can clean up server-side state.
          try {
            const client = await this._ensureClient();
            if (this.currentSessionId) {
              await client.commit({
                sessionId: this.currentSessionId,
                options: { uuid: result.uuid },
              });
            }
          } catch (_err) { /* non-fatal */ }
          // Reset the in-progress state so the user can design again.
          this._dropHandlers();
          this.currentSessionId = null;
          this.currentDraft = null;
          this._setThinking("");
          this._setPreview(
            `<p class="fab-done">Committed as <code>${this._escapeHtml(result.uuid)}</code>.</p>`
          );
          const pi = root.querySelector("#fab-prompt");
          if (pi) pi.value = "";
        }
      } catch (err) {
        ui.notifications?.error?.(
          `FVTT-CC-Generator: Commit failed — ${err?.message ?? err}`
        );
      }
    });
  }

  _wireLink(root) {
    const btn = root.querySelector("#fab-link-existing-btn");
    if (!btn) return;
    btn.addEventListener("click", async (ev) => {
      ev.preventDefault();
      try {
        const sheetType = root.querySelector("#fab-sheet-type")?.value ?? null;
        const picked = await this._openLinkPicker(sheetType);
        if (picked) {
          this.currentDraft = this.currentDraft ?? {};
          this.currentDraft.parentLocation = picked.uuid;
          this.currentDraft.parentLocationName = picked.name;
          const display = root.querySelector("#fab-parent-display");
          if (display) display.textContent = `↳ ${picked.name}`;
        }
      } catch (err) {
        ui.notifications?.error?.(
          `FVTT-CC-Generator: Link picker failed — ${err?.message ?? err}`
        );
      }
    });
  }

  // ---------------------------------------------------------------------------
  // Agent event handlers
  // ---------------------------------------------------------------------------

  _onThinking(msg) {
    if (!msg) return;
    if (
      msg.sessionId &&
      this.currentSessionId &&
      msg.sessionId !== this.currentSessionId
    ) {
      return; // not our session
    }
    const delta = msg.delta ?? msg.text ?? "";
    this._thinkingText = (this._thinkingText ?? "") + String(delta);
    this._setThinking(this._thinkingText);
  }

  _onPreview(msg) {
    if (!msg) return;
    if (
      msg.sessionId &&
      this.currentSessionId &&
      msg.sessionId !== this.currentSessionId
    ) {
      return;
    }
    const draft = msg.draft ?? msg.payload ?? null;
    if (!draft) return;
    this.currentDraft = { ...(this.currentDraft ?? {}), ...draft };
    this._thinkingText = "";
    this._setThinking("Draft ready.");
    this._renderPreview();
  }

  _onDesignError(msg) {
    const text = msg?.error ?? "unknown error from agent";
    this._thinkingText = "";
    this._setThinking("");
    this._setPreview(`<p class="fab-error">Agent error: ${this._escapeHtml(text)}</p>`);
    ui.notifications?.error?.(`FVTT-CC-Generator: ${text}`);
  }

  _onCommitted(_msg) {
    // The agent confirms the commit; we already showed the Foundry doc to the user.
    this._setThinking("");
  }

  // ---------------------------------------------------------------------------
  // DOM helpers
  // ---------------------------------------------------------------------------

  _setThinking(text) {
    const el = this.element?.querySelector("#fab-thinking");
    if (el) el.textContent = text ?? "";
  }

  _setPreview(html) {
    const el = this.element?.querySelector("#fab-preview-pane");
    if (el) el.innerHTML = html;
  }

  _renderPreview() {
    const pane = this.element?.querySelector("#fab-preview-pane");
    if (!pane) return;
    const d = this.currentDraft;
    if (!d) { pane.innerHTML = ""; return; }
    const name = this._escapeHtml(d.name ?? "") || "<em>(unnamed)</em>";
    const desc = this._escapeHtml(d.description ?? "");
    const tags = Array.isArray(d.tags) && d.tags.length
      ? `<div class="fab-tags">${d.tags
          .map((t) => `<span class="fab-tag">${this._escapeHtml(t)}</span>`)
          .join(" ")}</div>`
      : "";
    const denizens = Array.isArray(d.denizens) && d.denizens.length
      ? `<div class="fab-denizens"><strong>Denizens:</strong> ${d.denizens.length}</div>`
      : "";
    const parent = d.parentLocationName
      ? `<div class="fab-parent">Parent: <em>${this._escapeHtml(d.parentLocationName)}</em></div>`
      : "";
    pane.innerHTML = `
      <h3>${name}</h3>
      ${tags}
      ${parent}
      <div class="fab-desc">${desc}</div>
      ${denizens}
    `;
  }

  _escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  // ---------------------------------------------------------------------------
  // Client lifecycle
  // ---------------------------------------------------------------------------

  async _ensureClient() {
    if (this._client && this._client.ws?.readyState === WebSocket.OPEN) {
      return this._client;
    }
    const { url } = getSettings();
    if (this._client) this._client.close();
    this._client = new WsClient({ url });
    this._clientInitStarted = true;
    await this._client.connect();
    try {
      await this._client.hello();
    } catch (err) {
      console.warn("fvtt-cc-generator | hello failed:", err);
    }
    return this._client;
  }

  _dropHandlers() {
    for (const off of this._unsubs) {
      try { off(); } catch (_) { /* ignore */ }
    }
    this._unsubs = [];
    this._thinkingText = "";
  }

  // ---------------------------------------------------------------------------
  // Link picker dialog
  // ---------------------------------------------------------------------------

  async _openLinkPicker(typeFilter) {
    const cache = WorldContext.snapshot();
    /** @type {Array<{uuid:string,name:string,sheetType:string}>} */
    const options = [];
    for (const t of SHEET_TYPES) {
      for (const s of cache.sheets[t] ?? []) {
        if (typeFilter && t !== typeFilter) continue;
        options.push({ uuid: s.uuid, name: s.name, sheetType: t });
      }
    }

    if (!options.length) {
      try {
        ui.notifications?.info?.(
          "FVTT-CC-Generator: No existing CC sheets to link."
        );
      } catch (_) { /* ignore */ }
      return null;
    }

    // Prefer DialogV2 (v12+), fall back to legacy Dialog.
    const DlgV2 = foundry.applications?.api?.DialogV2;
    if (DlgV2) return this._openLinkPickerV2(DlgV2, options);
    return this._openLinkPickerLegacy(options);
  }

  _openLinkPickerV2(DlgV2, options) {
    return new Promise((resolve) => {
      let chosen = options[0];
      let resolved = false;
      const finish = (v) => { if (resolved) return; resolved = true; resolve(v); };

      const content = `
        <div class="fab-link-picker">
          <input type="search" id="fab-link-search" placeholder="Search existing sheets…" />
          <div class="fab-link-options">
            ${options.slice(0, 100).map((o, i) => `
              <label class="fab-link-option">
                <input type="radio" name="fab-link" value="${this._escapeHtml(o.uuid)}" ${i === 0 ? "checked" : ""} />
                <i class="fas ${SHEET_TYPE_ICONS[o.sheetType] ?? "fa-file"}"></i>
                ${this._escapeHtml(o.name)} <small>(${this._escapeHtml(o.sheetType)})</small>
              </label>
            `).join("")}
          </div>
        </div>
      `;

      const dlg = new DlgV2({
        window: { title: "Link to existing sheet" },
        content,
        buttons: [
          {
            action: "select",
            label: "Select",
            default: true,
            callback: () => finish(chosen),
          },
          { action: "cancel", label: "Cancel", callback: () => finish(null) },
        ],
      });

      dlg.addEventListener?.("render", () => {
        const root = dlg.element;
        if (!root) return;
        root.querySelectorAll('input[name="fab-link"]').forEach((r) => {
          r.addEventListener("change", (ev) => {
            const uuid = ev.target.value;
            chosen = options.find((o) => o.uuid === uuid) ?? chosen;
          });
        });
        const search = root.querySelector("#fab-link-search");
        if (search) {
          search.addEventListener("input", (ev) => {
            const q = String(ev.target.value ?? "").toLowerCase();
            root.querySelectorAll(".fab-link-option").forEach((lab) => {
              lab.hidden = !lab.textContent.toLowerCase().includes(q);
            });
          });
        }
      });
      dlg.addEventListener?.("close", () => finish(null));
      dlg.render({ force: true });
    });
  }

  _openLinkPickerLegacy(options) {
    return new Promise((resolve) => {
      let chosen = options[0];
      let resolved = false;
      const finish = (v) => { if (resolved) return; resolved = true; resolve(v); };

      const dlg = new Dialog({
        title: "Link to existing sheet",
        content: `
          <div class="fab-link-picker">
            <input type="search" id="fab-link-search" placeholder="Search existing sheets…" />
            <div class="fab-link-options">
              ${options.slice(0, 100).map((o, i) => `
                <label class="fab-link-option">
                  <input type="radio" name="fab-link" value="${this._escapeHtml(o.uuid)}" ${i === 0 ? "checked" : ""} />
                  <i class="fas ${SHEET_TYPE_ICONS[o.sheetType] ?? "fa-file"}"></i>
                  ${this._escapeHtml(o.name)} <small>(${this._escapeHtml(o.sheetType)})</small>
                </label>
              `).join("")}
            </div>
          </div>
        `,
        buttons: {
          select: { label: "Select", callback: () => finish(chosen) },
          cancel: { label: "Cancel", callback: () => finish(null) },
        },
        close: () => finish(null),
        render: (html) => {
          // Foundry v14 may pass an HTMLElement or a jQuery object depending on version.
          const root =
            html instanceof HTMLElement
              ? html
              : (html && typeof html[0] !== "undefined" ? html[0] : null);
          if (!root) return;
          root.querySelectorAll('input[name="fab-link"]').forEach((r) => {
            r.addEventListener("change", (ev) => {
              const uuid = ev.target.value;
              chosen = options.find((o) => o.uuid === uuid) ?? chosen;
            });
          });
          const search = root.querySelector("#fab-link-search");
          if (search) {
            search.addEventListener("input", (ev) => {
              const q = String(ev.target.value ?? "").toLowerCase();
              root.querySelectorAll(".fab-link-option").forEach((lab) => {
                lab.hidden = !lab.textContent.toLowerCase().includes(q);
              });
            });
          }
        },
      });
      dlg.render(true);
    });
  }
}
