import { buildConnectUrl, newState, readConnectMessage } from "./protocol.js";

/**
 * Drive one connect attempt: open the console, wait for the reply, clean up.
 *
 * The window is injected rather than reached for so the failure paths — popup
 * blocked, member closes the window, a message from somewhere else — are
 * testable. Those are the paths that decide whether this feels like a product
 * or like something that silently does nothing.
 */

export interface OpenedWindow {
  closed: boolean;
  close(): void;
}

export interface ConnectWindow {
  origin: string;
  open(url: string, target: string, features: string): OpenedWindow | null;
  addEventListener(type: "message", listener: (event: { origin: string; data: unknown }) => void): void;
  removeEventListener(
    type: "message",
    listener: (event: { origin: string; data: unknown }) => void,
  ): void;
}

export class ConnectCancelled extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ConnectCancelled";
  }
}

const POPUP_FEATURES = "width=520,height=760,menubar=no,toolbar=no,location=yes";

export async function requestKey(options: {
  consoleUrl: string;
  workspaceId: string;
  win: ConnectWindow;
  /** How often to notice the member closed the window. Small in tests. */
  pollMs?: number;
}): Promise<string> {
  const { consoleUrl, workspaceId, win, pollMs = 500 } = options;
  const state = newState();
  const consoleOrigin = new URL(consoleUrl).origin;
  const url = buildConnectUrl(consoleUrl, { origin: win.origin, state, workspaceId });

  const popup = win.open(url, "nufi-connect", POPUP_FEATURES);
  if (!popup) {
    throw new ConnectCancelled(
      "The browser blocked the NUFI sign-in window. Allow pop-ups for this site and try again.",
    );
  }

  return await new Promise<string>((resolve, reject) => {
    let settled = false;

    const finish = (fn: () => void) => {
      if (settled) return;
      settled = true;
      win.removeEventListener("message", onMessage);
      clearInterval(timer);
      fn();
    };

    const onMessage = (event: { origin: string; data: unknown }) => {
      // Anything that is not our reply is ignored, not treated as a failure:
      // other frames and extensions post to this window too, and one of their
      // messages must not end an attempt the member is still working through.
      const key = readConnectMessage(event, { origin: consoleOrigin, state });
      if (!key) return;
      finish(() => {
        popup.close();
        resolve(key);
      });
    };

    /**
     * A closed window is the only signal we get when someone changes their mind
     * or the console refuses. Without this the page waits forever on a spinner.
     */
    const timer = setInterval(() => {
      if (!popup.closed) return;
      finish(() => reject(new ConnectCancelled("The NUFI window closed before a key was issued.")));
    }, pollMs);

    win.addEventListener("message", onMessage);
  });
}
