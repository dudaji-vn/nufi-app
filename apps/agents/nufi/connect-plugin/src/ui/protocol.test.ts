import { describe, expect, it } from "bun:test";

import { buildConnectUrl, readConnectMessage } from "./protocol";

const CONSOLE = "https://console.nufi.me";

describe("buildConnectUrl", () => {
  it("carries the opener's origin, the nonce, and the workspace", () => {
    const url = new URL(
      buildConnectUrl(CONSOLE, {
        origin: "https://agents.nufi.me",
        state: "n1",
        workspaceId: "co_123",
      }),
    );
    expect(url.origin).toBe(CONSOLE);
    expect(url.pathname).toBe("/connect");
    expect(url.searchParams.get("origin")).toBe("https://agents.nufi.me");
    expect(url.searchParams.get("state")).toBe("n1");
    expect(url.searchParams.get("workspace")).toBe("co_123");
  });

  it("tolerates a console URL written with a trailing slash", () => {
    const url = new URL(
      buildConnectUrl("https://console.nufi.me/", {
        origin: "https://agents.nufi.me",
        state: "n1",
        workspaceId: "co_123",
      }),
    );
    expect(url.pathname).toBe("/connect");
  });

  it("keeps a base path when the console is mounted under one", () => {
    const url = new URL(
      buildConnectUrl("https://nufi.me/console", {
        origin: "https://agents.nufi.me",
        state: "n1",
        workspaceId: "co_123",
      }),
    );
    expect(url.pathname).toBe("/console/connect");
  });
});

describe("readConnectMessage", () => {
  const expected = { origin: CONSOLE, state: "n1" };
  const valid = {
    origin: CONSOLE,
    data: { source: "nufi-console", type: "nufi.connect.key", state: "n1", key: "sk-abc" },
  };

  it("returns the key when everything matches", () => {
    expect(readConnectMessage(valid, expected)).toBe("sk-abc");
  });

  /**
   * Every rejection below is a message this window can genuinely receive.
   * `window.addEventListener("message")` hears from every frame, extension, and
   * opened window on the page — accepting on shape alone would let any of them
   * feed us a credential, or read one meant for someone else.
   */
  it.each([
    ["a different origin", { ...valid, origin: "https://evil.example" }],
    ["a lookalike origin", { ...valid, origin: "https://console.nufi.me.evil.example" }],
    ["a stale or forged nonce", { ...valid, data: { ...valid.data, state: "n2" } }],
    ["a missing nonce", { ...valid, data: { ...valid.data, state: undefined } }],
    ["another app's message", { ...valid, data: { ...valid.data, source: "something-else" } }],
    ["a different message type", { ...valid, data: { ...valid.data, type: "nufi.connect.ping" } }],
    ["a non-string key", { ...valid, data: { ...valid.data, key: 42 } }],
    ["an empty key", { ...valid, data: { ...valid.data, key: "  " } }],
    ["a payload that is not an object", { ...valid, data: "sk-abc" }],
    ["a null payload", { ...valid, data: null }],
  ])("refuses %s", (_label, event) => {
    expect(readConnectMessage(event as never, expected)).toBeNull();
  });

  it("trims the delivered key", () => {
    expect(readConnectMessage({ ...valid, data: { ...valid.data, key: " sk-abc " } }, expected)).toBe(
      "sk-abc",
    );
  });
});
