/**
 * From a parsed config and a lease, the exact create request sent to Docker.
 *
 * Pure, so the whole contract of "what every sandbox gets and cannot change"
 * is one function with one test file. Nothing in here reads the raw config
 * and nothing in here talks to Docker.
 */
import type Dockerode from "dockerode";
import { memoryBytes, type DockerProviderConfig } from "./config.js";

export const SANDBOX_NETWORK = "works-sandbox";
export const SANDBOX_RUNTIME = "runsc";
export const WORKSPACE_DIR = "/workspace";

export interface LeaseIdentity {
  runId: string;
  agentId?: string;
  companyId?: string;
}

const SAFE_NAME = /[^a-zA-Z0-9_.-]/g;

export function containerName(lease: LeaseIdentity): string {
  return `works-sandbox-${lease.runId.replace(SAFE_NAME, "-")}`;
}

export function containerCreateOptions(
  config: DockerProviderConfig,
  lease: LeaseIdentity,
): Dockerode.ContainerCreateOptions {
  const proxy = `http://${config.egressProxy}`;
  const labels: Record<string, string> = { "me.nufi.works.run": lease.runId };
  if (lease.agentId) labels["me.nufi.works.agent"] = lease.agentId;
  if (lease.companyId) labels["me.nufi.works.company"] = lease.companyId;

  return {
    name: containerName(lease),
    Image: config.image,
    // Stay up and wait for exec; the lease decides when this container ends.
    Cmd: ["sleep", "infinity"],
    WorkingDir: WORKSPACE_DIR,
    Labels: labels,
    // Both cases: libraries disagree on which they read, and a client that
    // ignores both has no route anyway -- the network is internal.
    Env: [
      `HTTP_PROXY=${proxy}`,
      `HTTPS_PROXY=${proxy}`,
      `http_proxy=${proxy}`,
      `https_proxy=${proxy}`,
      "NO_PROXY=localhost,127.0.0.1",
      "no_proxy=localhost,127.0.0.1",
    ],
    NetworkingConfig: { EndpointsConfig: { [SANDBOX_NETWORK]: {} } },
    HostConfig: {
      // The kernel boundary. Not a config option, by design.
      Runtime: SANDBOX_RUNTIME,
      NetworkMode: SANDBOX_NETWORK,
      Memory: memoryBytes(config.memory),
      NanoCpus: Math.round(config.cpus * 1e9),
      PidsLimit: config.pidsLimit,
      ReadonlyRootfs: true,
      Tmpfs: { "/tmp": "rw,noexec,nosuid,size=256m" },
      // Source is the sanitised container name, not the raw runId: the
      // container name is already sanitised, and a volume name follows
      // stricter rules than a container name -- a runId containing "/"
      // would be accepted for the former and rejected for the latter.
      Mounts: [
        { Type: "volume", Source: containerName(lease), Target: WORKSPACE_DIR },
      ],
      CapDrop: ["ALL"],
      SecurityOpt: ["no-new-privileges"],
      // The lease owns the lifetime; an auto-removed container would vanish
      // between execs.
      AutoRemove: false,
      // A real init (tini) as PID 1 in place of "sleep infinity". A run is
      // many exec()s, and each one's process tree is reparented to PID 1
      // when it exits; sleep does not reap, so without an init the zombies
      // accumulate against the pids limit for the life of the container.
      // Not for a graceful stop: there is no stop path -- release and destroy
      // force-remove, and a timed-out command is killed by the sandbox's own
      // timeout(1).
      Init: true,
    },
  };
}
