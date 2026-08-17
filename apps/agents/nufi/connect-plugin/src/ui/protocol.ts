/**
 * The popup handshake between this app and the NUFI console.
 *
 * Kept separate from the React component because this is the part that has to
 * be right: a `message` listener hears from every frame, browser extension, and
 * opened window on the page, so "a message arrived" says nothing about who sent
 * it. Both halves of the check — origin and nonce — live here with tests.
 */

export interface ConnectRequest {
  /** This app's origin, which the console matches against its allow-list. */
  origin: string;
  /** One-time nonce, echoed back so a reply can be tied to this request. */
  state: string;
  /** Names the key on the console side; one key per member per workspace. */
  workspaceId: string;
}

/**
 * Where to send the user to approve.
 *
 * Built relative to the configured console URL so an install mounted under a
 * base path still works; `new URL("/connect", base)` would silently drop it.
 */
export function buildConnectUrl(consoleUrl: string, request: ConnectRequest): string {
  const base = consoleUrl.endsWith("/") ? consoleUrl : `${consoleUrl}/`;
  const url = new URL("connect", base);
  url.searchParams.set("origin", request.origin);
  url.searchParams.set("state", request.state);
  url.searchParams.set("workspace", request.workspaceId);
  return url.toString();
}

/** A nonce for one connect attempt. */
export function newState(): string {
  return crypto.randomUUID();
}

/** The subset of `MessageEvent` this needs, so the logic is testable as data. */
export interface IncomingMessage {
  origin: string;
  data: unknown;
}

/**
 * Return the delivered key, or null if this message is not the reply we are
 * waiting for.
 *
 * Null is the answer for anything unexpected — never a throw, because this runs
 * inside an event listener that also sees unrelated traffic, and never a
 * fallback that accepts on partial evidence.
 */
export function readConnectMessage(
  event: IncomingMessage,
  expected: { origin: string; state: string },
): string | null {
  if (event.origin !== expected.origin) return null;

  const data = event.data;
  if (!data || typeof data !== "object" || Array.isArray(data)) return null;

  const payload = data as Record<string, unknown>;
  if (payload.source !== "nufi-console") return null;
  if (payload.type !== "nufi.connect.key") return null;
  if (payload.state !== expected.state) return null;

  const key = payload.key;
  if (typeof key !== "string" || !key.trim()) return null;
  return key.trim();
}
