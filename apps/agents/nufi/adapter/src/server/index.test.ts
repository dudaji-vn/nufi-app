import { describe, expect, it } from "bun:test";

import { createServerAdapter } from "./index";

describe("createServerAdapter", () => {
  /**
   * The control plane mints a run JWT only for adapters that ask for one:
   *
   *     const authToken = adapter.supportsLocalAgentJwt ? createLocalAgentJwt(...) : null;
   *
   * Without the flag `ctx.authToken` is undefined, the adapter sends
   * `Authorization: Bearer ` with nothing after it, and the server resolves an
   * actor of type "none" — which has access to no company. Every control-plane
   * call then comes back 404 "Issue not found", because the existence check and
   * the access check deliberately share one response so issue ids cannot be
   * enumerated across tenants.
   *
   * That failure is invisible in local development: `local_trusted` mode grants
   * `local_implicit` access to everything, so an adapter with no token works
   * perfectly on a laptop and dies on any authenticated deployment. This test is
   * the only thing standing between the two.
   */
  it("asks the control plane for a run token", () => {
    expect(createServerAdapter().supportsLocalAgentJwt).toBe(true);
  });
});
