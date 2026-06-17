/**
 * Module settings for FVTT-CC-Generator.
 *
 * v0.2.x: collapsed `agentPort` + `agentToken` into a single `agentUrl`
 * setting. The agent has no auth in this version (security is deferred
 * per the project roadmap), so the module only needs the URL.
 *
 * i18n keys:
 *   FAB.Settings.agentUrl.Name
 *   FAB.Settings.agentUrl.Hint
 *   FAB.Settings.autoCommit.Name
 *   FAB.Settings.autoCommit.Hint
 *   FAB.Settings.defaultModel.Name
 *   FAB.Settings.defaultModel.Hint
 *   FAB.Settings.sidebarOpened.Name
 *   FAB.Settings.sidebarOpened.Hint
 */

import { MODULE_ID, AGENT_DEFAULT_URL } from "./constants.js";

/**
 * Register all module settings. Call once from the `init` hook.
 */
export function registerSettings() {
  // --- agentUrl -------------------------------------------------------------
  // Full WebSocket URL the browser should connect to. The operator
  // (typically a GM) sets this. For local-only setups the default
  // (ws://127.0.0.1:7777/ws/v1) works. For remote Foundry (Docker,
  // VPS, The Forge) the operator points it at something the browser
  // can actually reach — e.g. a Tailscale IP, a tunnel, etc.
  game.settings.register(MODULE_ID, "agentUrl", {
    name: "FAB.Settings.agentUrl.Name",
    hint: "FAB.Settings.agentUrl.Hint",
    scope: "world",
    config: true,
    type: String,
    default: AGENT_DEFAULT_URL,
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
 *   url: string,
 *   autoCommit: boolean,
 *   model: string,
 *   sidebarOpened: boolean
 * }}
 */
export function getSettings() {
  return {
    url: String(game.settings.get(MODULE_ID, "agentUrl") ?? AGENT_DEFAULT_URL),
    autoCommit: Boolean(game.settings.get(MODULE_ID, "autoCommit")),
    model: String(game.settings.get(MODULE_ID, "defaultModel") ?? ""),
    sidebarOpened: Boolean(game.settings.get(MODULE_ID, "sidebarOpened")),
  };
}

/**
 * Validate that a string looks like a WebSocket URL we can connect to.
 * @param {string} url
 * @returns {boolean}
 */
export function isValidAgentUrl(url) {
  if (typeof url !== "string") return false;
  const trimmed = url.trim();
  if (!trimmed) return false;
  if (!/^wss?:\/\//i.test(trimmed)) return false;
  return true;
}
