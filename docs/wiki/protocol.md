# WebSocket Protocol

The Foundry module and `fab-agent` speak a small JSON-over-WebSocket protocol. This page is the reference; **[Architecture](./architecture.md)** is the high-level "why".

## Endpoint

```
ws://127.0.0.1:7777/ws/v1
```

The host and port are configurable in the agent's `.env` (`AGENT_HOST`, `AGENT_PORT`) and in the Foundry module's settings (**Agent Host**, **Agent Port**).

## Authentication

Authentication is a shared secret passed in the `Sec-WebSocket-Protocol` header on the WebSocket upgrade. The Foundry module sets it; the agent validates it on every connection.

```
Sec-WebSocket-Protocol: fab.v1.token=<AGENT_TOKEN>
```

- The literal `fab.v1` is the protocol name (versioned so we can introduce `fab.v2` without colliding).
- The token after `=` must match `AGENT_TOKEN` in the agent's `.env`.
- Default token in v1: `change-me-in-module-settings`. **Change it for any non-loopback setup.**

The agent replies with the same `Sec-WebSocket-Protocol` value on a successful upgrade, and closes with code `4401` if the token doesn't match.

## Message envelope

Every message — client-to-server or server-to-client — is a single JSON object with the same shape:

```json
{
  "v": "1",
  "id": "<uuid-or-msgid>",
  "type": "<message-type>",
  "ts": 1718000000000,
  "data": { ... }
}
```

| Field | Type | Notes |
| --- | --- | --- |
| `v` | string | Protocol version. Always `"1"` in v1. |
| `id` | string | Message id. The client assigns it for client-to-server; the server copies it for the matching server-to-client event. |
| `type` | string | One of the message types below. |
| `ts` | number | Unix-millisecond timestamp, set by the sender. |
| `data` | object | Payload. Shape depends on `type`. |

The `id` field is what links a `design.start` to its eventual `design.preview` (or `design.error`).

## Client-to-server message types

### `hello`

Sent immediately after the WebSocket opens. The server replies with `hello.ok` (a server-pushed event).

```json
{
  "v": "1",
  "id": "h-1",
  "type": "hello",
  "ts": 1718000000000,
  "data": {
    "client": "fvtt-cc-generator",
    "clientVersion": "0.1.0",
    "foundryVersion": "14.321",
    "system": "dnd5e",
    "systemVersion": "4.0.0",
    "campaignCodexVersion": "3.8.0"
  }
}
```

### `design.start`

Begins a new design session. The server replies with a stream of `design.thinking` events, then either a `design.preview` or a `design.error`.

```json
{
  "v": "1",
  "id": "d-7",
  "type": "design.start",
  "ts": 1718000000000,
  "data": {
    "sheetType": "location",
    "prompt": "a small coastal inn run by a retired pirate",
    "links": [
      { "role": "parentRegion", "uuid": "JournalEntry.abc123" }
    ],
    "worldContext": {
      "region": "Saltmarsh",
      "tags": ["coastal", "dockside"]
    }
  }
}
```

| Field | Type | Notes |
| --- | --- | --- |
| `sheetType` | enum | `location`, `npc`, `region`, `shop`, `group`, `quest`. |
| `prompt` | string | The user's natural-language prompt. |
| `links` | array? | Optional pre-attached links. Same format as the **Link to existing** UI. |
| `worldContext` | object? | Optional hints the Foundry module has already gathered (current scene region, etc.). |

### `design.refine`

Re-runs the LLM against the previous draft plus a user instruction. Same reply shape as `design.start`.

```json
{
  "v": "1",
  "id": "d-7-r1",
  "type": "design.refine",
  "ts": 1718000050000,
  "data": {
    "sessionId": "d-7",
    "instruction": "add a rumor table and a hidden cellar description"
  }
}
```

The server keeps the session alive for a configurable window (default 5 minutes) after the last event, so a refine can reference a prior preview.

### `design.commit`

Finalises the accepted draft. The Foundry module is the one that does the actual write — this message tells the agent *"this draft is now in the world, you can drop the session"*. The server replies with `design.committed`.

```json
{
  "v": "1",
  "id": "d-7-c",
  "type": "design.commit",
  "ts": 1718000060000,
  "data": {
    "sessionId": "d-7",
    "acceptedDraft": { ...the full draft JSON... }
  }
}
```

### `design.cancel`

Client-initiated cancellation of an in-flight session. Server replies with `design.error { code: "cancelled" }` and tears down the session.

## Server-pushed events

### `hello.ok`

Reply to `hello`. The connection is ready for `design.start`.

```json
{
  "v": "1",
  "id": "h-1",
  "type": "hello.ok",
  "ts": 1718000000001,
  "data": {
    "server": "fab-agent",
    "serverVersion": "0.1.0",
    "skills": [
      "campaign-codex-sheets",
      "dnd5e-content-authoring",
      "compendium-search-first",
      "world-context-linking"
    ]
  }
}
```

### `design.thinking`

A streaming chunk of the LLM's reasoning. The client renders it in the **thinking** indicator. Many of these per session.

```json
{
  "v": "1",
  "id": "d-7",
  "type": "design.thinking",
  "ts": 1718000001234,
  "data": {
    "sessionId": "d-7",
    "chunk": "Considering the Saltmarsh region first..."
  }
}
```

### `design.preview`

The LLM has finished. The draft passed schema validation. Render the preview.

```json
{
  "v": "1",
  "id": "d-7",
  "type": "design.preview",
  "ts": 1718000009876,
  "data": {
    "sessionId": "d-7",
    "draft": {
      "sheetType": "location",
      "name": "The Rusted Anchor",
      "tags": ["tavern", "smuggling", "saltmarsh", "dockside"],
      "description": "...",
      "parentRegion": { "uuid": "JournalEntry.abc123", "name": "Saltmarsh" }
    },
    "reuse": [
      {
        "matchType": "item",
        "label": "Sailor's lodging (SRD)",
        "uuid": "Item.def456",
        "confidence": 0.82
      }
    ]
  }
}
```

| Field | Type | Notes |
| --- | --- | --- |
| `draft` | object | The validated CC sheet, ready to commit. |
| `reuse` | array | Compendium entries the search-first guarantee surfaced. Optional; absent if the draft made no claims. |

### `design.committed`

The Foundry module has written the documents. The agent releases the session. The `data` mirrors the user's commit but adds the live UUIDs of the created documents.

```json
{
  "v": "1",
  "id": "d-7",
  "type": "design.committed",
  "ts": 1718000060123,
  "data": {
    "sessionId": "d-7",
    "uuid": "JournalEntry.xyz789",
    "linkedDocs": [
      { "type": "Actor", "uuid": "Actor.aaa111" }
    ]
  }
}
```

### `design.error`

Something went wrong. The client should render the error in the preview pane.

```json
{
  "v": "1",
  "id": "d-7",
  "type": "design.error",
  "ts": 1718000009000,
  "data": {
    "sessionId": "d-7",
    "code": "schema_invalid",
    "message": "draft.tags[2] is not a string",
    "recoverable": true
  }
}
```

#### Error codes

| Code | Recoverable | Meaning |
| --- | --- | --- |
| `cancelled` | n/a | Sent in reply to `design.cancel`. |
| `llm_timeout` | yes | The LLM call exceeded the configured timeout. Suggest a smaller prompt or a faster model. |
| `llm_rate_limited` | yes | The LLM provider returned 429. Agent retries with exponential backoff; this fires only on hard failure. |
| `llm_auth` | no | `LLM_API_KEY` rejected. Check `.env`. |
| `schema_invalid` | yes | The LLM produced JSON but it didn't match the CC sheet schema. The user is shown the **Reuse suggestions** panel. |
| `uuid_unresolved` | yes | The draft references a UUID that doesn't exist in the world. Common after a world was reset. |
| `compendium_search_failed` | yes | The search-first step couldn't read the compendia (locked world, missing pack). |
| `internal` | no | Anything else. Check `fab-agent` stderr. |

## Worked example — full design session

```text
client → server  hello           { client, version, ... }
client ← server  hello.ok        { server, skills: [...] }
client → server  design.start    { sheetType: "location", prompt: "..." }
client ← server  design.thinking { chunk: "Considering the Saltmarsh..." }
client ← server  design.thinking { chunk: "The Rusted Anchor is a..." }
client ← server  design.thinking { chunk: "Searching compendia for taverns..." }
client ← server  design.thinking { chunk: "Found SRD 'Sailor's lodging'." }
client ← server  design.preview  { draft: {...}, reuse: [{...}] }
client → server  design.refine   { sessionId, instruction: "add a rumor table" }
client ← server  design.thinking { chunk: "Adding 3 rumors..." }
client ← server  design.preview  { draft: {...} (newer version) }
client → server  design.commit   { sessionId, acceptedDraft }
client ← server  design.committed{ uuid, linkedDocs }
```

## Error handling

The client should treat the WebSocket connection as **best-effort**:

- On disconnect, the sidebar shows **Disconnected** and stops accepting new prompts.
- The client auto-reconnects with exponential backoff (1s, 2s, 4s, 8s, capped at 30s).
- On reconnect, the client resends `hello`. In-flight sessions (a refine mid-stream) are **lost**; the user is shown a small toast and prompted to retry.
- `design.error { recoverable: true }` should be rendered as a soft warning with a **Retry** button.
- `design.error { recoverable: false }` should be rendered as a hard error with a link to **[Troubleshooting](./troubleshooting.md)**.

The server's contract is simpler: every client-to-server message gets **exactly one** terminal event (`design.preview` or `design.error`). A `design.start` followed by silence is a server bug — log it and force a reconnect.
