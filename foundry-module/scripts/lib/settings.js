/**
 * Module settings for FVTT-CC-Generator.
 *
 * Registers the five configuration entries used by the rest of the module and
 * exposes a single `getSettings()` getter for ergonomic reads.
 *
 * i18n keys (translation file should provide these):
 *   FAB.Settings.agentPort.Name
 *   FAB.Settings.agentPort.Hint
 *   FAB.Settings.agentToken.Name
 *   FAB.Settings.agentToken.Hint
 *   FAB.Settings.autoCommit.Name
 *   FAB.Settings.autoCommit.Hint
 *   FAB.Settings.defaultModel.Name
 *   FAB.Settings.defaultModel.Hint
 *   FAB.Settings.sidebarOpened.Name
 *   FAB.Settings.sidebarOpened.Hint
 */

import { MODULE_ID, AGENT_DEFAULT_PORT, AGENT_DEFAULT_TOKEN } from "./constants.js";

/**
 * Register all module settings. Call once from the `init` hook.
 */
export function registerSettings() {
  // --- agentPort -------------------------------------------------------------
  // WebSocket port the local agent listens on. World-scope so all clients
  // agree on the same endpoint.
  game.settings.register(MODULE_ID, "agentPort", {
    name: "FAB.Settings.agentPort.Name",
    hint: "FAB.Settings.agentPort.Hint",
    scope: "world",
    config: true,
    type: Number,
    default: AGENT_DEFAULT_PORT,
    range: { min: 1024, max: 65535, step: 1 },
    requiresReload: false,
  });

  // --- agentToken ------------------------------------------------------------
  // Shared secret. Must match the value the agent validates against
  // `Sec-WebSocket-Protocol: fab.v1.token=<token>`.
  game.settings.register(MODULE_ID, "agentToken", {
    name: "FAB.Settings.agentToken.Name",
    hint: "FAB.Settings.agentToken.Hint",
    scope: "world",
    config: true,
    type: String,
    default: AGENT_DEFAULT_TOKEN,
  });

  // --- autoCommit ------------------------------------------------------------
  // Per-user toggle: if true, the designer skips the preview step and
  // auto-commits the first draft the agent produces.
  game.settings.register(MODULE_ID, "autoCommit", {
    name: "FAB.Settings.autoCommit.Name",
    hint: "FAB.Settings.autoCommit.Hint",
    scope: "client",
    config: true,
    type: Boolean,
    default: false,
  });

  // --- defaultModel ----------------------------------------------------------
  // Optional LLM model override. Empty string = "use the agent's default".
  game.settings.register(MODULE_ID, "defaultModel", {
    name: "FAB.Settings.defaultModel.Name",
    hint: "FAB.Settings.defaultModel.Hint",
    scope: "world",
    config: true,
    type: String,
    default: "",
  });

  // --- sidebarOpened ---------------------------------------------------------
  // Internal state: whether the AI Designer sidebar tab is currently shown.
  // Not shown in the settings UI (config: false).
  game.settings.register(MODULE_ID, "sidebarOpened", {
    name: "FAB.Settings.sidebarOpened.Name",
    hint: "FAB.Settings.sidebarOpened.Hint",
    scope: "client",
    config: false,
    type: Boolean,
    default: false,
  });
}

/**
 * Read all module settings as a single ergonomic object.
 *
 * @returns {{
 *   port: number,
 *   token: string,
 *   autoCommit: boolean,
 *   model: string,
 *   sidebarOpened: boolean
 * }}
 */
export function getSettings() {
  return {
    port: Number(game.settings.get(MODULE_ID, "agentPort")) || AGENT_DEFAULT_PORT,
    token: String(game.settings.get(MODULE_ID, "agentToken") ?? AGENT_DEFAULT_TOKEN),
    autoCommit: Boolean(game.settings.get(MODULE_ID, "autoCommit")),
    model: String(game.settings.get(MODULE_ID, "defaultModel") ?? ""),
    sidebarOpened: Boolean(game.settings.get(MODULE_ID, "sidebarOpened")),
  };
}
