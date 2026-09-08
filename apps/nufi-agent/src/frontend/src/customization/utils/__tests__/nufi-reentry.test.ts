import { getNufiEnterUrl, isLoginPath, shouldReenter } from "../urls";

describe("getNufiEnterUrl", () => {
  it("carries the current location back as ?next=", () => {
    expect(getNufiEnterUrl("/flow/abc", "?tab=1")).toBe(
      "https://console.nufi.me/enter/studio?next=%2Fflow%2Fabc%3Ftab%3D1",
    );
  });

  it("works from the root with no query", () => {
    expect(getNufiEnterUrl("/", "")).toBe(
      "https://console.nufi.me/enter/studio?next=%2F",
    );
  });
});

describe("shouldReenter", () => {
  it("allows a first re-entry", () => {
    expect(shouldReenter(1_000_000, null)).toBe(true);
  });

  it("refuses a second one inside the cooldown", () => {
    // The loop this prevents: console mints a token, Studio rejects it, the
    // frontend bounces back to the console, forever.
    expect(shouldReenter(1_000_000, String(1_000_000 - 5_000))).toBe(false);
  });

  it("allows one again after the cooldown", () => {
    expect(shouldReenter(1_000_000, String(1_000_000 - 31_000))).toBe(true);
  });

  it("allows one when the stamp is garbage", () => {
    expect(shouldReenter(1_000_000, "not-a-number")).toBe(true);
  });
});

describe("isLoginPath", () => {
  it("matches the upstream login route", () => {
    expect(isLoginPath("/login")).toBe(true);
    expect(isLoginPath("/login/")).toBe(true);
  });

  it("does not match a page that merely mentions login", () => {
    // The interceptor's own `isLoginPage` uses includes("login"), which is
    // true for these. The boot handoff must be stricter: bouncing a member
    // off a settings page because of its name would be worse than the form.
    expect(isLoginPath("/settings/login-history")).toBe(false);
    expect(isLoginPath("/flows/login-flow")).toBe(false);
    expect(isLoginPath("/auto_login")).toBe(false);
  });

  it("does not match the routes a signed-in member actually uses", () => {
    expect(isLoginPath("/")).toBe(false);
    expect(isLoginPath("/flows")).toBe(false);
    expect(isLoginPath("/flow/abc")).toBe(false);
  });
});
