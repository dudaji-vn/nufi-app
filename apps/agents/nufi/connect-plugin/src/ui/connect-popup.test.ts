import { describe, expect, it } from "bun:test";

import { ConnectCancelled, requestKey, type ConnectWindow, type OpenedWindow } from "./connect-popup";

const CONSOLE = "https://console.nufi.me";

function fakeWindow(popup: OpenedWindow | null) {
  const listeners: Array<(e: { origin: string; data: unknown }) => void> = [];
  let openedUrl = "";
  const win: ConnectWindow = {
    origin: "https://agents.nufi.me",
    open(url) {
      openedUrl = url;
      return popup;
    },
    addEventListener(_type, listener) {
      listeners.push(listener);
    },
    removeEventListener(_type, listener) {
      const i = listeners.indexOf(listener);
      if (i >= 0) listeners.splice(i, 1);
    },
  };
  return {
    win,
    get openedUrl() {
      return openedUrl;
    },
    get listenerCount() {
      return listeners.length;
    },
    post(event: { origin: string; data: unknown }) {
      for (const l of [...listeners]) l(event);
    },
  };
}

function openPopup(): OpenedWindow & { closeCalls: number } {
  return { closed: false, closeCalls: 0, close() { this.closeCalls += 1; this.closed = true; } };
}

/** Read the nonce back off the URL, since only the caller knows it. */
function stateOf(url: string): string {
  return new URL(url).searchParams.get("state") ?? "";
}

describe("requestKey", () => {
  it("resolves with the key the console delivers, then closes the window", async () => {
    const popup = openPopup();
    const host = fakeWindow(popup);
    const pending = requestKey({ consoleUrl: CONSOLE, workspaceId: "co_1", win: host.win, pollMs: 5 });

    await Promise.resolve();
    host.post({
      origin: CONSOLE,
      data: {
        source: "nufi-console",
        type: "nufi.connect.key",
        state: stateOf(host.openedUrl),
        key: "sk-abc",
      },
    });

    expect(await pending).toBe("sk-abc");
    expect(popup.closeCalls).toBe(1);
    expect(host.listenerCount).toBe(0);
  });

  /**
   * Pop-up blockers are common and silent. Saying so beats a button that looks
   * broken.
   */
  it("explains itself when the browser blocks the window", async () => {
    const host = fakeWindow(null);
    await expect(
      requestKey({ consoleUrl: CONSOLE, workspaceId: "co_1", win: host.win, pollMs: 5 }),
    ).rejects.toBeInstanceOf(ConnectCancelled);
  });

  it("gives up when the member closes the window without approving", async () => {
    const popup = openPopup();
    const host = fakeWindow(popup);
    const pending = requestKey({ consoleUrl: CONSOLE, workspaceId: "co_1", win: host.win, pollMs: 5 });

    popup.closed = true;
    await expect(pending).rejects.toBeInstanceOf(ConnectCancelled);
    expect(host.listenerCount).toBe(0);
  });

  it("ignores unrelated messages and keeps waiting for the real one", async () => {
    const popup = openPopup();
    const host = fakeWindow(popup);
    const pending = requestKey({ consoleUrl: CONSOLE, workspaceId: "co_1", win: host.win, pollMs: 5 });

    await Promise.resolve();
    host.post({ origin: "https://evil.example", data: { source: "nufi-console", type: "nufi.connect.key", state: stateOf(host.openedUrl), key: "sk-evil" } });
    host.post({ origin: CONSOLE, data: { source: "nufi-console", type: "nufi.connect.key", state: "wrong", key: "sk-stale" } });
    host.post({ origin: CONSOLE, data: { source: "nufi-console", type: "nufi.connect.key", state: stateOf(host.openedUrl), key: "sk-real" } });

    expect(await pending).toBe("sk-real");
  });

  it("passes this app's origin and the workspace to the console", async () => {
    const popup = openPopup();
    const host = fakeWindow(popup);
    const pending = requestKey({ consoleUrl: CONSOLE, workspaceId: "co_42", win: host.win, pollMs: 5 });

    const url = new URL(host.openedUrl);
    expect(url.searchParams.get("origin")).toBe("https://agents.nufi.me");
    expect(url.searchParams.get("workspace")).toBe("co_42");

    popup.closed = true;
    await pending.catch(() => {});
  });
});
