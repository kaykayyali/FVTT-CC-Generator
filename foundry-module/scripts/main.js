/**
 * FVTT-CC-Generator — main entry.
 *
 * Registers:
 *  - Settings (port, token, model name)
 *  - The ApplicationV2 sidebar ("AI Designer")
 *  - The WebSocket client that talks to the local Hermes agent
 *  - The world-context preloader (existing CC sheets, NPCs, etc.)
 *  - The commit flow that creates JournalEntries with CC flag payload
 */

import { DesignerApp } from "./sheets/designer.js";
import { WsClient } from "./lib/ws-client.js";
import { WorldContext } from "./lib/world-context.js";
import { Commit } from "./lib/commit.js";
import { registerSettings, getSettings } from "./lib/settings.js";
import { MODULE_ID, AGENT_DEFAULT_PORT } from "./lib/constants.js";

const FLAG_KEY = "fvtt-cc-generator";

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
  // Foundry's sidebar apps registry is module-aware in v14
  if (ui.sidebar && typeof ui.sidebar.render === "function") {
    // We attach as a tab below the chat log
    game.fab_designer = app;
  }

  // Test connection to the local agent
  await testAgentConnection();

  // Preload world context for the agent
  await WorldContext.refresh();

  console.log(`${MODULE_ID} | Ready. Open the "AI Designer" tab in the sidebar.`);
});

/* -------------------------------------------- */
/*  Connection test                              */
/* -------------------------------------------- */

async function testAgentConnection() {
  const { port, token } = getSettings();
  const client = new WsClient({ port, token });
  try {
    const info = await client.hello();
    if (info.ok) {
      console.log(`${MODULE_ID} | Agent connected: ${info.agent} v${info.version}`);
      ui.notifications.info(`FVTT-CC-Generator: Connected to local agent (${info.model ?? "default model"}).`);
    } else {
      throw new Error(info.error ?? "unknown");
    }
  } catch (err) {
    const msg = String(err?.message ?? err);
    console.warn(`${MODULE_ID} | Agent not reachable at ws://127.0.0.1:${port} — ${msg}`);
    ui.notifications.warn(
      `FVTT-CC-Generator: Could not reach local agent on port ${port}. ` +
      `Start the agent with: uv run fab-agent  (see INSTALL.md). Error: ${msg}`
    );
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
      const { port, token } = getSettings();
      const client = new WsClient({ port, token });
      return client.design({ docType, prompt, context: ctx });
    },
    /** Commit a designed draft to the world */
    commit: Commit.commitDraft,
    /** Refresh the cached world context */
    refreshContext: () => WorldContext.refresh(),
  };
});
