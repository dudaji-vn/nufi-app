/**
 * The ten hooks. Each is a few lines over container-spec.ts and docker.ts --
 * this file owns none of the Docker- or config-specific logic itself.
 */
import {
  definePlugin,
  type PluginEnvironmentAcquireLeaseParams,
  type PluginEnvironmentDestroyLeaseParams,
  type PluginEnvironmentExecuteParams,
  type PluginEnvironmentExecuteResult,
  type PluginEnvironmentLease,
  type PluginEnvironmentProbeParams,
  type PluginEnvironmentProbeResult,
  type PluginEnvironmentRealizeWorkspaceParams,
  type PluginEnvironmentRealizeWorkspaceResult,
  type PluginEnvironmentReleaseLeaseParams,
  type PluginEnvironmentResumeLeaseParams,
  type PluginEnvironmentValidateConfigParams,
  type PluginEnvironmentValidationResult,
  type PluginHealthDiagnostics,
} from "@paperclipai/plugin-sdk";
import { parseConfig, validateConfig } from "./config.js";
import { containerCreateOptions, WORKSPACE_DIR } from "./container-spec.js";
import { DockerClient, SandboxStateUnknownError } from "./docker.js";

// One client for the worker's lifetime. NUFI_DOCKER_SOCKET exists for the
// tests, which point it at a fake daemon on a unix socket; on a box it is
// unset and the default socket is used.
let docker: DockerClient | null = null;
function client(): DockerClient {
  if (!docker) docker = new DockerClient({ socketPath: process.env.NUFI_DOCKER_SOCKET });
  return docker;
}

function leaseId(lease: PluginEnvironmentLease): string | null {
  return lease.providerLeaseId && lease.providerLeaseId.length > 0 ? lease.providerLeaseId : null;
}

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

// Shared by onEnvironmentReleaseLease and onEnvironmentDestroyLease: both are
// "force-remove this lease's container, but refuse if it is not one of
// ours" (see DockerClient.assertOurs -- the socket has no per-caller scope).
// assertOurs rejecting here is not swallowed: a refusal must fail the hook.
async function removeLease(id: string | null): Promise<void> {
  if (!id) return;
  const d = client();
  await d.assertOurs(id);
  await d.remove(id);
}

const plugin = definePlugin({
  async setup(ctx) {
    docker = new DockerClient({ socketPath: process.env.NUFI_DOCKER_SOCKET });
    ctx.logger.info("Docker+gVisor sandbox provider ready");
  },

  async onHealth(): Promise<PluginHealthDiagnostics> {
    const h = await client().health();
    return h.ok
      ? { status: "ok", message: "Docker reachable, runsc runtime present" }
      : { status: "error", message: h.reason };
  },

  async onEnvironmentValidateConfig(
    params: PluginEnvironmentValidateConfigParams,
  ): Promise<PluginEnvironmentValidationResult> {
    return validateConfig(params.config ?? {});
  },

  async onEnvironmentProbe(_params: PluginEnvironmentProbeParams): Promise<PluginEnvironmentProbeResult> {
    const h = await client().health();
    return h.ok ? { ok: true, summary: "Docker reachable, runsc present" } : { ok: false, summary: h.reason };
  },

  async onEnvironmentAcquireLease(
    params: PluginEnvironmentAcquireLeaseParams,
  ): Promise<PluginEnvironmentLease> {
    // parseConfig ignores keys it does not know, and containerCreateOptions
    // never reads the raw config -- so `runtime: "runc"` or `privileged: true`
    // in a stored config changes nothing. The test for that is in
    // plugin.test.ts, not only container-spec.test.ts, because this is the
    // path a stored config actually takes.
    const config = parseConfig(params.config ?? {});
    const options = containerCreateOptions(config, {
      runId: params.runId,
      agentId: params.agentId,
      companyId: params.companyId,
    });
    const d = client();
    const id = await d.create(options);
    try {
      await d.start(id);
    } catch (err) {
      await d.remove(id).catch(() => undefined);
      throw err;
    }
    return {
      providerLeaseId: id,
      metadata: { provider: "docker", image: config.image, remoteCwd: WORKSPACE_DIR },
      expiresAt: new Date(Date.now() + config.timeoutMs).toISOString(),
    };
  },

  async onEnvironmentResumeLease(
    params: PluginEnvironmentResumeLeaseParams,
  ): Promise<PluginEnvironmentLease> {
    const id = params.providerLeaseId;
    const d = client();
    const state = await d.inspect(id);
    if (!state.exists) {
      // Not quietly a new one: the host asked for *this* sandbox, with whatever
      // was in its workspace. A fresh container is a different answer, and the
      // host has an acquire hook for that.
      throw new Error(`sandbox ${id.slice(0, 12)} no longer exists on this box`);
    }
    if (!state.running) await d.start(id);
    return { providerLeaseId: id, metadata: { ...(params.leaseMetadata ?? {}), resumed: true } };
  },

  // The host calls onEnvironmentReleaseLease at the end of every run for
  // every plugin-backed lease, and calls onEnvironmentDestroyLease only for
  // leases the manifest marks reuse_by_environment -- which ours never are
  // (see manifest.ts). So release is not a "pause, might resume later" step
  // here: it is the only cleanup call a normal run gets. Releasing by
  // stopping (not removing) would leave a stopped container -- and its
  // volume -- on the box forever, once per run.
  async onEnvironmentReleaseLease(params: PluginEnvironmentReleaseLeaseParams): Promise<void> {
    await removeLease(params.providerLeaseId);
  },

  async onEnvironmentDestroyLease(params: PluginEnvironmentDestroyLeaseParams): Promise<void> {
    await removeLease(params.providerLeaseId);
  },

  async onEnvironmentRealizeWorkspace(
    params: PluginEnvironmentRealizeWorkspaceParams,
  ): Promise<PluginEnvironmentRealizeWorkspaceResult> {
    const cwd = params.workspace?.remotePath ?? params.workspace?.localPath ?? WORKSPACE_DIR;
    const id = leaseId(params.lease);
    if (id) {
      const r = await client().exec(id, ["mkdir", "-p", cwd], { timeoutMs: 30_000 });
      if (r.exitCode !== 0) throw new Error(`could not create ${cwd} in the sandbox: ${r.stderr}`);
    }
    return { cwd, metadata: { provider: "docker", remoteCwd: cwd } };
  },

  async onEnvironmentExecute(
    params: PluginEnvironmentExecuteParams,
  ): Promise<PluginEnvironmentExecuteResult> {
    const id = leaseId(params.lease);
    if (!id) {
      return { exitCode: 1, timedOut: false, stdout: "", stderr: "No provider lease ID available for execution." };
    }
    // Every exec has a deadline: the caller's, or the environment's own
    // lifetime when the caller sets none (the e2b provider does the same).
    const config = parseConfig(params.config ?? {});
    try {
      const r = await client().exec(id, [params.command, ...(params.args ?? [])], {
        cwd: params.cwd,
        env: params.env,
        stdin: params.stdin,
        timeoutMs: params.timeoutMs ?? config.timeoutMs,
      });
      return { exitCode: r.exitCode, timedOut: r.timedOut, stdout: r.stdout, stderr: r.stderr };
    } catch (err) {
      // A rejection before the exec existed -- the daemon refused to create
      // the exec -- is a known state: nothing ran,
      // the container is as it was, and the command simply failed.
      if (!(err instanceof SandboxStateUnknownError)) {
        return { exitCode: 1, timedOut: false, stdout: "", stderr: errorMessage(err) };
      }
      // After that point a rejection means the container's state is unknown
      // (see DockerClient.exec's doc comment): the daemon connection dropped
      // mid-command. We cannot claim to know what is running in there, so we
      // force-remove the container rather than leave an orphan the host has
      // no other handle on -- but assertOurs still guards this exactly like
      // release/destroy: an unknown state is not a license to remove a
      // container this provider did not create.
      const d = client();
      await d.assertOurs(id).then(() => d.remove(id)).catch(() => undefined);
      return {
        exitCode: null,
        timedOut: false,
        stdout: "",
        stderr: `sandbox ${id.slice(0, 12)} is in an unknown state and was removed: ${errorMessage(err)}`,
      };
    }
  },
});

export default plugin;
