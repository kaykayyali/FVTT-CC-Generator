/**
 * WebSocket client for the local Hermes-powered agent.
 *
 * v0.2.x: takes a full WebSocket URL (no port+token, no auth header).
 * Any client that can complete the WS handshake is accepted by the agent.
 * The URL is operator-configurable so the browser can reach an agent
 * running on a different machine over a Tailscale / tunnel / LAN.
 *
 * Provides:
 *   - request/response correlation via per-call IDs
 *   - pub/sub for server-pushed events (design.thinking, design.preview, ...)
 *   - automatic single-shot reconnection if the socket drops unexpectedly
 *
 * Protocol:
 *   client -> server (request):   { id, type, payload }
 *   server -> client (response):  { id, type, ok, result, error? }
 *   server -> client (push):      { type, sessionId?, ... }
 */

import { WS_RECONNECT_DELAY_MS } from "./constants.js";

export class WsClient {
  /**
   * @param {{ url: string }} options
   */
  constructor({ url } = {}) {
    this.url = String(url ?? "");
    /** @type {?WebSocket} */
    this.ws = null;
    this._idCounter = 0;
    /** @type {Map<string, {resolve:Function, reject:Function}>} */
    this._pending = new Map();
    /** @type {Map<string, Set<Function>>} */
    this._handlers = new Map();
    this._wantOpen = false;
    this._reconnectTried = false;
    /** @type {?object} Cached hello response. */
    this._helloInfo = null;
  }

  // ---------------------------------------------------------------------------
  // Connection lifecycle
  // ---------------------------------------------------------------------------

  /**
   * Open the WebSocket. Resolves when the socket is fully open.
   * Idempotent: if a connection is already open or in-flight, awaits it.
   *
   * @returns {Promise<void>}
   */
  connect() {
    this._wantOpen = true;

    if (!this.url) {
      return Promise.reject(new Error("No agent URL configured"));
    }

    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      return Promise.resolve();
    }
    if (this.ws && this.ws.readyState === WebSocket.CONNECTING) {
      return new Promise((resolve, reject) => {
        const ws = this.ws;
        ws.addEventListener("open", () => resolve(), { once: true });
        ws.addEventListener("error", () => reject(new Error("WebSocket error")), { once: true });
      });
    }

    return new Promise((resolve, reject) => {
      let ws;
      try {
        ws = new WebSocket(this.url);
      } catch (err) {
        this._wantOpen = false;
        reject(err);
        return;
      }
      this.ws = ws;
      this._wire(ws, resolve, reject);
    });
  }

  /**
   * Close the underlying socket. Idempotent.
   */
  close() {
    this._wantOpen = false;
    if (this.ws) {
      try {
        if (
          this.ws.readyState === WebSocket.OPEN ||
          this.ws.readyState === WebSocket.CONNECTING
        ) {
          this.ws.close(1000, "client closing");
        }
      } catch (_) { /* ignore */ }
      this.ws = null;
    }
    // Reject any in-flight requests so callers don't hang.
    for (const [, p] of this._pending) p.reject(new Error("WebSocket closed"));
    this._pending.clear();
  }

  // ---------------------------------------------------------------------------
  // Wire handlers
  // ---------------------------------------------------------------------------

  _wire(ws, openResolve, openReject) {
    let settled = false;

    ws.addEventListener("open", () => {
      settled = true;
      this._reconnectTried = false;
      try { openResolve?.(); } catch (_) { /* ignore */ }
    });

    ws.addEventListener("error", () => {
      if (!settled) {
        settled = true;
        try { openReject?.(new Error("WebSocket failed to connect")); }
        catch (_) { /* ignore */ }
      }
    });

    ws.addEventListener("close", (ev) => {
      // Reject any pending requests.
      for (const [, p] of this._pending) p.reject(new Error(`WebSocket closed (code ${ev.code})`));
      this._pending.clear();
      this.ws = null;

      if (!this._wantOpen) return;          // user asked to close — no reconnect
      if (this._reconnectTried) return;     // we already tried once

      this._reconnectTried = true;
      console.warn(
        `fvtt-cc-generator | WebSocket closed unexpectedly (code ${ev.code}); attempting one reconnect.`
      );
      this.connect().catch((err) => {
        console.warn(`fvtt-cc-generator | Reconnect failed: ${err?.message ?? err}`);
        try {
          ui.notifications?.warn?.(
            `FVTT-CC-Generator: Lost connection to the agent at ${this.url} (code ${ev.code}). ` +
            `Check that the agent is running and reachable.`
          );
        } catch (_) { /* ignore */ }
      });
    });

    ws.addEventListener("message", (ev) => {
      let msg;
      try { msg = JSON.parse(ev.data); }
      catch (err) {
        console.warn("fvtt-cc-generator | Non-JSON message from agent:", ev.data);
        return;
      }
      this._dispatch(msg);
    });
  }

  // ---------------------------------------------------------------------------
  // Request / response
  // ---------------------------------------------------------------------------

  _nextId() {
    this._idCounter = (this._idCounter + 1) & 0x7fffffff;
    // Sufficient for correlation within a single session.
    return `fab-${Date.now().toString(36)}-${this._idCounter.toString(36)}`;
  }

  /**
   * Send a request and await the matching response.
   *
   * @param {string} type
   * @param {object} payload
   * @returns {Promise<object>} the server response, sans the `id` field.
   */
  _send(type, payload) {
    return new Promise((resolve, reject) => {
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
        reject(new Error("WebSocket is not open"));
        return;
      }
      const id = this._nextId();
      this._pending.set(id, { resolve, reject });
      try {
        this.ws.send(JSON.stringify({ id, type, payload: payload ?? {} }));
      } catch (err) {
        this._pending.delete(id);
        reject(err);
      }
    });
  }

  // ---------------------------------------------------------------------------
  // Event handlers (server-pushed)
  // ---------------------------------------------------------------------------

  /**
   * Register a handler for a server-pushed message type. Returns an unsubscribe fn.
   *
   * @param {string} type
   * @param {(msg:object)=>void} handler
   * @returns {() => void}
   */
  on(type, handler) {
    if (typeof handler !== "function") return () => {};
    let set = this._handlers.get(type);
    if (!set) { set = new Set(); this._handlers.set(type, set); }
    set.add(handler);
    return () => set.delete(handler);
  }

  /**
   * Route an incoming message: pending request vs. event fan-out.
   * @param {object} msg
   */
  _dispatch(msg) {
    if (!msg || typeof msg !== "object") return;

    // Response to a pending request?
    if (msg.id && this._pending.has(msg.id)) {
      const p = this._pending.get(msg.id);
      this._pending.delete(msg.id);
      if (msg.ok === false || msg.error) {
        p.reject(new Error(msg.error || `${msg.type ?? "request"} failed`));
      } else {
        // Return the whole message minus the id, so callers see .ok / .result / etc.
        const { id: _ignored, ...rest } = msg;
        p.resolve(rest);
      }
      return;
    }

    // Otherwise: fan out to event handlers.
    if (msg.type) {
      const set = this._handlers.get(msg.type);
      if (set && set.size) {
        for (const fn of set) {
          try { fn(msg); }
          catch (err) {
            console.error(`fvtt-cc-generator | handler for ${msg.type} threw:`, err);
          }
        }
      }
    }
  }

  // ---------------------------------------------------------------------------
  // High-level convenience
  // ---------------------------------------------------------------------------

  /**
   * Handshake. Returns the server's hello payload as a flat object.
   * @returns {Promise<{ok:boolean, agent:?string, version:?string, model:?string, raw:object}>}
   */
  async hello() {
    await this.connect();
    const res = await this._send("hello", {});
    // Server response shape: { type: "hello.result", ok: true, result: { agent, version, model }, ... }
    const result = res?.result ?? {};
    this._helloInfo = {
      ok: res?.ok !== false,
      agent: result.agent ?? res?.agent ?? null,
      version: result.version ?? res?.version ?? null,
      model: result.model ?? res?.model ?? null,
      raw: res,
    };
    return this._helloInfo;
  }

  /**
   * Start a new design session. The actual generation is delivered via
   * `design.thinking` / `design.preview` events — caller should subscribe
   * BEFORE invoking `design()`.
   *
   * @param {{ docType:string, prompt:string, context?:object, sessionId?:string }} opts
   * @returns {Promise<{ sessionId:?string, raw:object }>}
   */
  async design({ docType, prompt, context, sessionId } = {}) {
    if (!docType) throw new Error("design(): docType is required");
    if (!prompt) throw new Error("design(): prompt is required");
    const res = await this._send("design.start", {
      docType,
      prompt,
      context: context ?? null,
      sessionId: sessionId ?? null,
    });
    const result = res?.result ?? {};
    return {
      sessionId: result.sessionId ?? res?.sessionId ?? null,
      raw: res,
    };
  }

  /**
   * Refine the current draft in an active session.
   * @param {{ sessionId:string, feedback:string }} opts
   */
  async refine({ sessionId, feedback } = {}) {
    if (!sessionId) throw new Error("refine(): sessionId is required");
    if (!feedback) throw new Error("refine(): feedback is required");
    return this._send("design.refine", { sessionId, feedback });
  }

  /**
   * Commit the current draft. The agent confirms via a `design.committed` push.
   * @param {{ sessionId:string, options?:object }} opts
   */
  async commit({ sessionId, options } = {}) {
    if (!sessionId) throw new Error("commit(): sessionId is required");
    return this._send("design.commit", { sessionId, options: options ?? {} });
  }
}
