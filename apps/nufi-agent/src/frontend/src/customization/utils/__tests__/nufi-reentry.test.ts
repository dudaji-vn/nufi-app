import { getNufiEnterUrl, shouldReenter } from "../urls";

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
