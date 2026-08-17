/**
 * Minimal local declarations for the Paperclip plugin SDK.
 *
 * This package deliberately lives outside Paperclip's pnpm workspace — the fork
 * guard rejects additions under `apps/agents/packages/`, and keeping NuFi code
 * in `nufi/` is what keeps `git subtree pull` a merge rather than a conflict.
 * The bundled kubernetes sandbox plugin upstream does the same thing: bare
 * imports at build time, resolved from the host's node_modules at run time,
 * because the host spawns the worker.
 *
 * Only the surface this plugin touches is declared. If the upstream contract
 * changes shape, the build here still passes and the failure surfaces when the
 * plugin loads — the same trade the NuFi adapter makes, and the reason both are
 * exercised against a real server before release.
 */

declare module "@paperclipai/plugin-sdk" {
  export interface PluginDataClient {
    register(key: string, handler: (params: Record<string, unknown>) => Promise<unknown>): void;
  }

  export interface PluginLogger {
    info(message: string, meta?: Record<string, unknown>): void;
    warn(message: string, meta?: Record<string, unknown>): void;
    error(message: string, meta?: Record<string, unknown>): void;
  }

  export interface PluginSetupContext {
    data: PluginDataClient;
    logger: PluginLogger;
  }

  export interface PluginDefinition {
    setup(ctx: PluginSetupContext): Promise<void> | void;
    onHealth?(): Promise<{ status: string; message?: string }> | { status: string; message?: string };
  }

  export function definePlugin(definition: PluginDefinition): PluginDefinition;
  export function runWorker(plugin: PluginDefinition, moduleUrl: string): void;

  export interface PaperclipPluginManifestV1 {
    id: string;
    apiVersion: 1;
    version: string;
    displayName: string;
    description: string;
    author: string;
    categories: string[];
    capabilities: string[];
    entrypoints: { worker: string; ui?: string };
    instanceConfigSchema?: Record<string, unknown>;
    ui?: {
      slots: Array<{
        type: string;
        id: string;
        displayName: string;
        exportName: string;
        routePath?: string;
        order?: number;
      }>;
    };
  }
}

declare module "@paperclipai/plugin-sdk/ui" {
  export interface PluginHostContext {
    companyId: string | null;
    companyPrefix: string | null;
    projectId: string | null;
    entityId: string | null;
    entityType: string | null;
    userId: string | null;
  }

  export interface PluginWidgetProps {
    context: PluginHostContext;
  }

  export function usePluginData<T = unknown>(
    key: string,
    params?: Record<string, unknown>,
  ): { data: T | null; loading: boolean; error: Error | null };
}
