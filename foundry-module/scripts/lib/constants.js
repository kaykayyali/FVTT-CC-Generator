/**
 * Module-level constants for FVTT-CC-Generator.
 * Centralized so the rest of the module references one place.
 */

export const MODULE_ID = "fvtt-cc-generator";

/** Default port the local agent listens on (must match agent's default). */
export const AGENT_DEFAULT_PORT = 7777;

/** Default shared-secret token. Users change this in module settings. */
export const AGENT_DEFAULT_TOKEN = "change-me-in-module-settings";

/** WebSocket protocol identifier (used in Sec-WebSocket-Protocol). */
export const WS_PROTOCOL_PREFIX = "fab.v1.token=";

/** WebSocket path on the agent server. */
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
