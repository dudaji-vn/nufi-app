import {
  getNufiEnterUrl,
  isLoginPath,
  isLogoutPath,
  isSessionDiscoveryPath,
  shouldReenter,
} from "../urls";

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

describe("isSessionDiscoveryPath", () => {
  it("matches the two endpoints that answer whether a session exists", () => {
    // /auto_login is the one a cold load actually fails on -- measured, not
    // assumed: it is the single 403 a deep route produces with no identity.
    expect(isSessionDiscoveryPath("/api/v1/auto_login")).toBe(true);
    expect(isSessionDiscoveryPath("/api/v1/refresh")).toBe(true);
    expect(isSessionDiscoveryPath("https://studio.nufi.me/api/v1/refresh?x=1")).toBe(true);
  });

  it("never matches login or logout", () => {
    // Answering a sign-out by signing the member back in would make Log out
    // impossible, so these two must stay out of the set.
    expect(isSessionDiscoveryPath("/api/v1/logout")).toBe(false);
    expect(isSessionDiscoveryPath("/api/v1/login")).toBe(false);
  });

  it("does not match a business endpoint that shares a prefix", () => {
    expect(isSessionDiscoveryPath("/api/v1/refresh_tokens")).toBe(false);
    expect(isSessionDiscoveryPath("/api/v1/flows")).toBe(false);
    expect(isSessionDiscoveryPath(undefined)).toBe(false);
  });
});

describe("isLogoutPath", () => {
  it("matches a logout request in the forms axios produces", () => {
    expect(isLogoutPath("/api/v1/logout")).toBe(true);
    expect(isLogoutPath("https://studio.nufi.me/api/v1/logout")).toBe(true);
  });

  it("does not match a lookalike", () => {
    expect(isLogoutPath("/api/v1/logout_sessions")).toBe(false);
    expect(isLogoutPath("/api/v1/auto_login")).toBe(false);
    expect(isLogoutPath(undefined)).toBe(false);
  });
});
