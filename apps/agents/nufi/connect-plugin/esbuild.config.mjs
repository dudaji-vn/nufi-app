import { build } from "esbuild";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));

/**
 * Build the three artefacts the host loads: manifest, worker, UI bundle.
 *
 * Two things here are deliberate.
 *
 * **The SDK is bundled into the worker, not imported.** The host `fork()`s the
 * worker with plain Node, so a bare `@paperclipai/plugin-sdk` specifier is
 * resolved against this directory — and this package lives outside Paperclip's
 * pnpm workspace on purpose (the fork guard rejects additions under
 * `packages/`, and keeping NuFi code in `nufi/` is what keeps
 * `git subtree pull` a merge rather than a conflict). Bundling makes the worker
 * self-contained, so it behaves the same in the repo and in a built image.
 * The alias below is the one place that knows where upstream keeps the SDK; if
 * upstream moves it, this fails at build time rather than at plugin load.
 *
 * **The UI bundle keeps three bare specifiers.** The host fetches the bundle,
 * rewrites `react`, `react/jsx-runtime`, and `@paperclipai/plugin-sdk/ui` to
 * blob URLs backed by its own modules, then imports it. Bundling React instead
 * would give the page a second React and break hooks. Everything else must be
 * inlined: the rewritten module is imported from a blob URL, which has no base
 * for resolving a relative path.
 */
const SDK_ENTRY = path.resolve(here, "../../packages/plugins/sdk/src/index.ts");

const common = { bundle: true, format: "esm", logLevel: "info" };

await build({
  ...common,
  entryPoints: [path.join(here, "src/manifest.ts")],
  platform: "node",
  outfile: path.join(here, "dist/manifest.js"),
});

await build({
  ...common,
  entryPoints: [path.join(here, "src/worker.ts")],
  platform: "node",
  alias: { "@paperclipai/plugin-sdk": SDK_ENTRY },
  outfile: path.join(here, "dist/worker.js"),
});

await build({
  ...common,
  entryPoints: [path.join(here, "src/ui/index.tsx")],
  platform: "browser",
  jsx: "automatic",
  external: ["react", "react/jsx-runtime", "react-dom", "react-dom/client", "@paperclipai/plugin-sdk/ui"],
  outfile: path.join(here, "dist/ui/index.js"),
});
