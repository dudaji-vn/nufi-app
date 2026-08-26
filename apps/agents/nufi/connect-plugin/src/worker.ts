import { definePlugin, runWorker } from "@paperclipai/plugin-sdk";

/**
 * A worker that does nothing, on purpose.
 *
 * The manifest requires a worker entrypoint and the host starts one for every
 * plugin, so there has to be a process here that completes the handshake. There
 * is nothing for it to do: this plugin's only server-side need is its console
 * URL, and that is company-scoped operator config the host already stores,
 * validates against `instanceConfigSchema`, and serves over its own API — which
 * the page reads directly with the member's session.
 *
 * Reading the URL from `process.env` here would not work even if it were
 * tempting: the host deliberately withholds its environment from plugin
 * workers, passing only deployment mode and exposure (see
 * `buildPluginWorkerEnv`).
 */
const plugin = definePlugin({
  // Required by the host even when there is nothing to wire up: activation
  // calls `setup` unconditionally and an absent one fails the whole plugin
  // with "definition.setup is not a function".
  async setup() {},

  async onHealth() {
    return { status: "ok", message: "UI-only plugin; configuration lives in plugin settings" };
  },
});

export default plugin;
runWorker(plugin, import.meta.url);
