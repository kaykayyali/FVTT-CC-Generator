/**
 * Module-level constants for FVTT-CC-Generator.
 * Centralized so the rest of the module references one place.
 */

export const MODULE_ID = "fvtt-cc-generator";

/**
 * Default WebSocket URL the module tries on first launch.
 *
 * Loopback (127.0.0.1) only works when the agent runs on the same
 * machine as the browser. For remote Foundry (Docker, VPS, The Forge)
 * operators set the URL to something their browser can reach — e.g.
 * a Tailscale IP (`ws://100.x.y.z:7777`) or a tunnel.
 */
export const AGENT_DEFAULT_URL = "ws://127.0.0.1:7777/ws/v1";

/** WebSocket path on the agent server (must match the agent's listener). */
export const WS_PATH = "/ws/v1";

/** Sheet types the agent can generate. Must match campaign-codex-sheets. */
export const SHEET_TYPES = ["location", "npc", "region", "shop", "group", "quest"];

/** UI labels for sheet types. */
export const SHEET_TYPE_LABELS = {
  location: "Location",
  npc: "NPC",
  region: "Region",
  shop: "Shop",
  group: "Group / Faction",
  quest: "Quest",
};

/** UI icons (FontAwesome class names). */
export const SHEET_TYPE_ICONS = {
  location: "fa-map-marker-alt",
  npc: "fa-user",
  region: "fa-globe-europe",
  shop: "fa-store",
  group: "fa-users",
  quest: "fa-scroll",
};

/**
 * Default auto-reconnect interval (ms) when the WebSocket drops.
 * Set high enough that we don't busy-loop on a dead endpoint.
 */
export const WS_RECONNECT_DELAY_MS = 3000;
