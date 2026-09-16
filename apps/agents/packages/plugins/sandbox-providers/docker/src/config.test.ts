import { describe, expect, it } from "vitest";
import { ConfigError, DEFAULTS, MIN_MEMORY, memoryBytes, parseConfig, validateConfig } from "./config.js";

describe("parseConfig", () => {
  it("fills every default when given nothing", () => {
    expect(parseConfig({})).toEqual(DEFAULTS);
    expect(DEFAULTS.image).toMatch(/:/);   // the default itself is pinned
    expect(DEFAULTS.egressProxy).toBe("works-egress:3128");
  });

  it("takes what is given and keeps the rest", () => {
    const c = parseConfig({ image: "ghcr.io/dudaji-vn/nufi-sandbox:v1.2", cpus: 4 });
    expect(c.image).toBe("ghcr.io/dudaji-vn/nufi-sandbox:v1.2");
    expect(c.cpus).toBe(4);
    expect(c.memory).toBe(DEFAULTS.memory);
  });

  it("refuses an unpinned image — a bare name is whatever :latest is today", () => {
    expect(() => parseConfig({ image: "ghcr.io/dudaji-vn/nufi-sandbox" })).toThrow(ConfigError);
    expect(() => parseConfig({ image: "ghcr.io/dudaji-vn/nufi-sandbox" })).toThrow(/pinned/);
  });

  it("accepts a digest as pinned", () => {
    expect(parseConfig({ image: "ghcr.io/x/y@sha256:" + "a".repeat(64) }).image).toContain("@sha256:");
  });

  it("refuses limits that do not parse", () => {
    expect(() => parseConfig({ memory: "lots" })).toThrow(/memory/);
    expect(() => parseConfig({ cpus: 0 })).toThrow(/cpus/);
    expect(() => parseConfig({ cpus: "two" })).toThrow(/cpus/);
    expect(() => parseConfig({ pidsLimit: -1 })).toThrow(/pidsLimit/);
  });

  it("refuses a memory limit under Docker's 6 MiB minimum -- \"0\" parses, and means unlimited", () => {
    expect(() => parseConfig({ memory: "0" })).toThrow(/memory/);
    expect(() => parseConfig({ memory: "1m" })).toThrow(/memory/);
    expect(() => parseConfig({ memory: "0" })).toThrow(new RegExp(MIN_MEMORY));
    expect(parseConfig({ memory: "6m" }).memory).toBe("6m");
    expect(MIN_MEMORY).toBe("6m");
  });

  it("refuses a proxy that is not host:port", () => {
    expect(() => parseConfig({ egressProxy: "http://works-egress:3128" })).toThrow(/egressProxy/);
    expect(() => parseConfig({ egressProxy: "works-egress" })).toThrow(/egressProxy/);
  });

  it("ignores keys it does not know, so provider: docker in the stored config is fine", () => {
    expect(parseConfig({ provider: "docker", somethingElse: 1 })).toEqual(DEFAULTS);
  });
});

describe("memoryBytes", () => {
  it("converts each Docker size unit to bytes", () => {
    expect(memoryBytes("512m")).toBe(512 * 1024 ** 2);
    expect(memoryBytes("2g")).toBe(2 * 1024 ** 3);
    expect(memoryBytes("1.5g")).toBe(1.5 * 1024 ** 3);
    expect(memoryBytes("1024k")).toBe(1024 * 1024);
    expect(memoryBytes("100")).toBe(100); // bare number = bytes
    expect(memoryBytes("1B")).toBe(1);
  });
});

describe("validateConfig", () => {
  it("reports every problem at once, as errors, not by throwing", () => {
    const r = validateConfig({ image: "bare", cpus: 0 });
    expect(r.ok).toBe(false);
    expect(r.errors).toHaveLength(2);
    expect(r.errors.join(" ")).toMatch(/pinned/);
    expect(r.errors.join(" ")).toMatch(/cpus/);
  });
  it("is ok for the defaults", () => {
    expect(validateConfig({})).toEqual({ ok: true, errors: [], warnings: [] });
  });
});
