import { describe, expect, it } from "bun:test";

import { normaliseConsoleUrl } from "./host-api";

describe("normaliseConsoleUrl", () => {
  it("accepts an https console and drops a trailing slash", () => {
    expect(normaliseConsoleUrl("https://console.nufi.me/")).toBe("https://console.nufi.me");
  });

  it("accepts http, so a laptop and an on-prem install both work", () => {
    expect(normaliseConsoleUrl("http://localhost:5173")).toBe("http://localhost:5173");
  });

  it("keeps a base path when the console is mounted under one", () => {
    expect(normaliseConsoleUrl("https://nufi.me/console")).toBe("https://nufi.me/console");
  });

  /**
   * This value is handed to `window.open`, where a `javascript:` URL runs in
   * this origin. Only an instance admin can write the config, but refusing the
   * shape is a stronger guarantee than trusting the writer.
   */
  it.each([
    ["a javascript: URL", "javascript:alert(document.cookie)"],
    ["a data: URL", "data:text/html,<script>1</script>"],
    ["a file: URL", "file:///etc/passwd"],
    ["something that is not a URL", "console.nufi.me"],
    ["an empty string", ""],
    ["whitespace", "   "],
    ["a non-string", 42],
    ["nothing", undefined],
    ["null", null],
  ])("refuses %s", (_label, value) => {
    expect(normaliseConsoleUrl(value)).toBeNull();
  });
});
