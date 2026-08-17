/**
 * The only two SDK symbols the worker needs, taken from their own modules
 * rather than the package barrel.
 *
 * `@paperclipai/plugin-sdk`'s index re-exports `zod`, the test harness, the dev
 * server and the bundler presets. Bundling through it drags in `zod` and
 * `@paperclipai/shared`, which resolve only when Paperclip's own workspace has
 * been installed — true on a developer machine, false on a clean checkout, so
 * the build passed locally and failed in CI on the first run.
 *
 * This subgraph (define-plugin → worker-rpc-host → protocol) imports nothing
 * but Node builtins and types, so the worker bundle is self-contained and this
 * package needs no third-party dependency at all.
 *
 * The `.js` specifiers are TypeScript's NodeNext convention; esbuild resolves
 * them to the neighbouring `.ts` sources.
 */
export { definePlugin } from "../../packages/plugins/sdk/src/define-plugin.js";
export { runWorker } from "../../packages/plugins/sdk/src/worker-rpc-host.js";
