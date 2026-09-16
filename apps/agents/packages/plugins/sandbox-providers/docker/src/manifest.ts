import type { PaperclipPluginManifestV1 } from "@paperclipai/plugin-sdk";

const PLUGIN_ID = "nufi.docker-sandbox-provider";
const PLUGIN_VERSION = "0.1.0";

const manifest: PaperclipPluginManifestV1 = {
  id: PLUGIN_ID,
  apiVersion: 1,
  version: PLUGIN_VERSION,
  displayName: "Docker + gVisor Sandbox Provider",
  description:
    "Runs agent code in a Docker container under gVisor on the NuFi box. Every sandbox is on an internal network with the egress proxy as its only way out.",
  author: "NuFi",
  categories: ["automation"],
  capabilities: ["environment.drivers.register"],
  entrypoints: {
    worker: "./dist/worker.js",
  },
  environmentDrivers: [
    {
      driverKey: "docker",
      kind: "sandbox_provider",
      displayName: "Docker + gVisor (NuFi box)",
      description:
        "A container per run under the runsc runtime, on the works-sandbox network, reaching the world only through works-egress.",
      // What an operator may change. Deliberately absent: runtime, network,
      // privileged, the socket. A provider that can be told to use runc is one
      // config line away from having no kernel boundary.
      configSchema: {
        type: "object",
        properties: {
          image: {
            type: "string",
            description:
              "Pinned image reference for the sandbox (tag or digest; a bare name is refused).",
            default: "ghcr.io/dudaji-vn/nufi-sandbox:main",
          },
          memory: {
            type: "string",
            description: "Memory limit, Docker syntax.",
            default: "2g",
          },
          cpus: {
            type: "number",
            description: "CPU limit, Docker syntax.",
            default: 2,
          },
          pidsLimit: {
            type: "number",
            description: "Process limit inside the sandbox.",
            default: 512,
          },
          egressProxy: {
            type: "string",
            description: "The forward proxy every sandbox is pointed at. Hostname:port on the works-sandbox network.",
            default: "works-egress:3128",
          },
          timeoutMs: {
            type: "number",
            description: "Sandbox lifetime in milliseconds; a lease older than this is not resumed.",
            default: 3600000,
          },
        },
      },
    },
  ],
};

export default manifest;
