/**
 * FVTT-CC-Generator — main entry.
 *
 * Registers:
 *  - Settings (agentUrl, model, autoCommit)
 *  - The ApplicationV2 sidebar ("AI Designer")
 *  - The WebSocket client that talks to the agent
 *  - The world-context preloader (existing CC sheets, NPCs, etc.)
 *  - The commit flow that creates JournalEntries with CC flag payload
 *
 * v0.2.x: the agent URL is operator-configurable (no more hardcoded
 * 127.0.0.1). On first run the module prompts a GM for the URL. The
 * connection has no auth — security is deferred, the agent is meant
 * to run behind a firewall or overlay network.
 */

import { DesignerApp } from "./sheets/designer.js";
import { WsClient } from "./lib/ws-client.js";
import { WorldContext } from "./lib/world-context.js";
import { Commit } from "./lib/commit.js";
import { registerSettings, getSettings, isValidAgentUrl } from "./lib/settings.js";
import { MODULE_ID } from "./lib/constants.js";

/* -------------------------------------------- */
/*  Module init                                  */
/* -------------------------------------------- */

Hooks.once("init", () => {
  registerSettings();
  console.log(`${MODULE_ID} | Initialized.`);
});

/* -------------------------------------------- */
/*  Module ready — register the sidebar          */
/* -------------------------------------------- */

Hooks.once("ready", async () => {
  // Soft dependency check on Campaign Codex
  if (!game.modules.get("campaign-codex")?.active) {
    ui.notifications.warn(
      `${MODULE_ID} | Campaign Codex module is not enabled. The AI Designer requires it. ` +
      `Install and enable Campaign Codex, then reload.`
    );
  }

  // Add a sidebar tab
  game.settings.set(MODULE_ID, "sidebarOpened", false);
  const app = new DesignerApp();
  if (ui.sidebar && typeof ui.sidebar.render === "function") {
    game.fab_designer = app;
  }

  // Preload world context for the agent
  await WorldContext.refresh();

  // Try the agent. If the URL is empty/invalid, only GMs get prompted.
  // Players just see a warning that the AI Designer is not connected.
  await testAgentConnection({ allowPrompt: true });

  console.log(`${MODULE_ID} | Ready. Open the "AI Designer" tab in the sidebar.`);
});

/* -------------------------------------------- */
/*  URL prompt (GMs only)                        */
/* -------------------------------------------- */

/**
 * Show a small dialog asking for the agent's WebSocket URL.
 * Resolves with the entered URL (string) or null if cancelled.
 * Only GMs should call this — players don't need to know the URL.
 *
 * @returns {Promise<?string>}
 */
async function promptForAgentUrl() {
  // Prefer DialogV2 (v12+), fall back to classic Dialog.
  if (foundry?.applications?.api?.DialogV2) {
    return new Promise((resolve) => {
      let resolved = false;
      const finish = (val) => {
        if (resolved) return;
        resolved = true;
        resolve(val);
      };
      const dlg = new foundry.applications.api.DialogV2({
        window: { title: "FVTT-CC-Generator — Agent URL" },
        content: `
          <form>
            <p style="margin:0 0 0.5em 0;">
              The local AI agent's WebSocket URL. Examples:
            </p>
            <ul style="margin:0 0 0.5em 1.5em; padding:0;">
              <li><code>ws://127.0.0.1:7777/ws/v1</code> — agent on the browser's machine</li>
              <li><code>ws://100.x.y.z:7777/ws/v1</code> — agent on a Tailscale IP</li>
              <li><code>wss://agent.example.com/ws/v1</code> — agent behind a tunnel</li>
            </ul>
            <div class="form-group">
              <label>WebSocket URL</label>
              <input type="text" name="url" autofocus
                     value="${(getSettings().url || "").replace(/"/g, "&quot;")}"
                     placeholder="ws://100.x.y.z:7777/ws/v1"/>
            </div>
          </form>
        `,
        buttons: [
          {
            action: "save",
            label: "Save & Connect",
            default: true,
            callback: (event, button) => {
              const form = button.form;
              const val = form?.elements?.url?.value?.trim() ?? "";
              return val;
            },
          },
          {
            action: "skip",
            label: "Skip for now",
            callback: () => null,
          },
        ],
        submit: (result) => {
          if (result === "save") {
            // The callback above returns the URL via button.form, but DialogV2
            // wraps the return value. Re-read from the DOM to be safe.
            const input = dlg.element?.querySelector('input[name="url"]');
            const val = input?.value?.trim() ?? "";
            finish(isValidAgentUrl(val) ? val : null);
          } else {
            finish(null);
          }
        },
        close: () => finish(null),
      });
      dlg.render({ force: true });
    });
  }

  // Fallback: classic Dialog.
  return new Promise((resolve) => {
    let resolved = false;
    const finish = (val) => {
      if (resolved) return;
      resolved = true;
      resolve(val);
    };
    new Dialog({
      title: "FVTT-CC-Generator — Agent URL",
      content: `
        <form>
          <p>WebSocket URL for the local agent.</p>
          <div class="form-group">
            <label>WebSocket URL</label>
            <input type="text" name="url" value="${(getSettings().url || "").replace(/"/g, "&quot;")}"/>
          </div>
        </form>
      `,
      buttons: {
        save: {
          icon: '<i class="fas fa-plug"></i>',
          label: "Save & Connect",
          callback: (html) => {
            const val = html.find('input[name="url"]').val()?.trim() ?? "";
            finish(isValidAgentUrl(val) ? val : null);
          },
        },
        skip: {
          icon: '<i class="fas fa-times"></i>',
          label: "Skip for now",
          callback: () => finish(null),
        },
      },
      default: "save",
      close: () => finish(null),
    }).render(true);
  });
}

/* -------------------------------------------- */
/*  Connection test                              */
/* -------------------------------------------- */

/**
 * Test the connection to the agent. If `allowPrompt` is true and the
 * current user is a GM, prompt for the URL when it's missing or the
 * connection fails.
 *
 * @param {{ allowPrompt?: boolean }} opts
 */
async function testAgentConnection({ allowPrompt = false } = {}) {
  let { url } = getSettings();

  if (!isValidAgentUrl(url)) {
    if (allowPrompt && game.user?.isGM) {
      url = await promptForAgentUrl();
      if (url) {
        await game.settings.set(MODULE_ID, "agentUrl", url);
        ui.notifications.info(`FVTT-CC-Generator: agent URL set to ${url}`);
      } else {
        console.warn(`${MODULE_ID} | No agent URL set; the AI Designer will not connect.`);
        return;
      }
    } else {
      console.warn(`${MODULE_ID} | No agent URL configured; skipping connection test.`);
      return;
    }
  }

  const client = new WsClient({ url });
  try {
    const info = await client.hello();
    if (info.ok) {
      console.log(`${MODULE_ID} | Agent connected: ${info.agent} v${info.version}`);
      ui.notifications.info(`FVTT-CC-Generator: Connected to agent (${info.model ?? "default model"}).`);
    } else {
      throw new Error(info.error ?? "unknown");
    }
  } catch (err) {
    const msg = String(err?.message ?? err);
    console.warn(`${MODULE_ID} | Agent not reachable at ${url} — ${msg}`);
    ui.notifications.warn(
      `FVTT-CC-Generator: Could not reach agent at ${url}. ` +
      `Start the agent with: uv run fab-agent. Error: ${msg}`
    );

    // Re-prompt the GM if allowed.
    if (allowPrompt && game.user?.isGM) {
      const newUrl = await promptForAgentUrl();
      if (newUrl && newUrl !== url) {
        await game.settings.set(MODULE_ID, "agentUrl", newUrl);
        ui.notifications.info(`FVTT-CC-Generator: agent URL updated. Reload the world to retry.`);
      }
    }
  }
}

/* -------------------------------------------- */
/*  Public API (for other modules)               */
/* -------------------------------------------- */

Hooks.on("ready", () => {
  // Expose a small API for macro / module authors
  game.modules.get(MODULE_ID).api = {
    /** Open the AI Designer sidebar */
    openDesigner: () => game.fab_designer?.render(true),
    /** Get the current world context (existing CC sheets, etc.) */
    getWorldContext: () => WorldContext.snapshot(),
    /** Submit a design request programmatically (returns a sessionId) */
    design: async (docType, prompt, ctx = {}) => {
      const { url } = getSettings();
      const client = new WsClient({ url });
      await client.connect();
      return client.design({ docType, prompt, context: ctx });
    },
    /** Commit a designed draft to the world */
    commit: Commit.commitDraft,
    /** Refresh the cached world context */
    refreshContext: () => WorldContext.refresh(),
    /** Manually re-test the connection (e.g. after editing agentUrl) */
    reconnect: () => testAgentConnection({ allowPrompt: game.user?.isGM }),
  };
});
