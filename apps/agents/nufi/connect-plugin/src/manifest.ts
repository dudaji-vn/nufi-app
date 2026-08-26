import type { PaperclipPluginManifestV1 } from "@paperclipai/plugin-sdk";

/**
 * NUFI Connection — one page under company settings where a member hands this
 * app their own gateway key.
 *
 * It ships as a plugin rather than a patch to `ui/src` because the fork guard
 * rejects changes to vendored upstream files, and because upstream already
 * provides this extension point. The whole feature is additive: remove the
 * plugin and the app is stock Paperclip again.
 */
const manifest: PaperclipPluginManifestV1 = {
  id: "nufi.connect",
  apiVersion: 1,
  version: "0.1.0",
  displayName: "NUFI Connection",
  description:
    "Connect your NUFI account so agents call the gateway with your own key, on your own budget.",
  author: "NuFi",
  categories: ["ui"],
  // `companySettingsPage` maps to instance.settings.register in the host's
  // capability table, not ui.page.register.
  capabilities: ["instance.settings.register"],
  entrypoints: {
    worker: "./dist/worker.js",
    ui: "./dist/ui",
  },
  /**
   * Where this deployment's NUFI console lives. The host renders a form for
   * this automatically under Plugin settings and validates what is saved, so
   * one bundle serves every deployment and changing the address needs no
   * rebuild and no restart.
   *
   * It is operator config rather than something the page carries, because the
   * page must not get to name its own credential issuer.
   */
  instanceConfigSchema: {
    type: "object",
    properties: {
      consoleUrl: {
        type: "string",
        title: "NUFI console URL",
        description:
          "Base address of the NUFI console, e.g. https://console.nufi.me. The console must also list this app's address in AGENTS_ALLOWED_ORIGINS, or it will refuse to issue keys.",
      },
    },
  },
  ui: {
    slots: [
      {
        type: "companySettingsPage",
        id: "nufi-connection",
        displayName: "NUFI",
        exportName: "NufiConnectionPage",
        routePath: "nufi",
        order: 40,
      },
    ],
  },
};

export default manifest;
