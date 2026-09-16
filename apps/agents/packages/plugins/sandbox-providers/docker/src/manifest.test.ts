import { describe, expect, it } from "vitest";
import manifest from "./manifest.js";

describe("manifest", () => {
  it("registers exactly one sandbox provider, keyed docker", () => {
    expect(manifest.capabilities).toContain("environment.drivers.register");
    expect(manifest.environmentDrivers).toHaveLength(1);
    const driver = manifest.environmentDrivers![0];
    expect(driver.driverKey).toBe("docker");
    expect(driver.kind).toBe("sandbox_provider");
  });

  it("exposes only what an operator may change — never the runtime", () => {
    const props = Object.keys(manifest.environmentDrivers![0].configSchema!.properties ?? {});
    expect(props).toEqual(expect.arrayContaining(["image", "memory", "cpus", "pidsLimit", "egressProxy", "timeoutMs"]));
    // A schema with a runtime field is a provider one config line away from runc.
    expect(props).not.toContain("runtime");
    expect(props).not.toContain("network");
    expect(props).not.toContain("privileged");
  });
});
