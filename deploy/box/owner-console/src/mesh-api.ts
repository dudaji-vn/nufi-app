// A minimal headscale REST client — just enough to mint a tag:member pre-auth
// key, the same call `nufi-box invite` makes. The only credential it holds is
// MESH_API_KEY. It trusts the coordinator's certificate through the container's
// NODE_EXTRA_CA_CERTS (the mounted internal CA) for a self-hosted coordinator,
// or the system bundle for a public one — nothing to configure here.

export type MeshConfig = { serverUrl: string; apiKey: string };

export class MeshError extends Error {
  constructor(message: string, readonly status?: number) {
    super(message);
    this.name = 'MeshError';
  }
}

// The box's mesh config, or null when the box is LAN-only / has no API key —
// in which case the console cannot mint invites and says so.
export function meshConfig(env: Record<string, string | undefined> = process.env): MeshConfig | null {
  const serverUrl = env.MESH_SERVER_URL ?? '';
  const apiKey = env.MESH_API_KEY ?? '';
  if (!serverUrl || !apiKey) return null;
  return { serverUrl, apiKey };
}

async function api(
  cfg: MeshConfig,
  method: string,
  path: string,
  body: unknown,
  fetchImpl: typeof fetch,
): Promise<Record<string, unknown>> {
  let r: Response;
  try {
    r = await fetchImpl(cfg.serverUrl.replace(/\/$/, '') + path, {
      method,
      headers: {
        authorization: `Bearer ${cfg.apiKey}`,
        ...(body ? { 'content-type': 'application/json' } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
      signal: AbortSignal.timeout(20000),
    });
  } catch (e) {
    // Connection refused, DNS failure, TLS failure, or the 20s timeout — the
    // coordinator is unreachable (e.g. sealed off under --egress-enforce).
    throw new MeshError(e instanceof Error ? `coordinator unreachable: ${e.message}` : 'coordinator unreachable');
  }
  if (r.status === 401 || r.status === 403) throw new MeshError('MESH_API_KEY rejected by the coordinator', r.status);
  if (!r.ok) throw new MeshError(`headscale ${method} ${path} returned HTTP ${r.status}`, r.status);
  return (await r.json()) as Record<string, unknown>;
}

// The numeric id of the box's headscale user. v0.29.3's preauthkey create takes
// the id, not the name, so resolve it first (as lib/mesh.sh does).
async function userId(cfg: MeshConfig, name: string, fetchImpl: typeof fetch): Promise<string> {
  const data = await api(cfg, 'GET', `/api/v1/user?name=${encodeURIComponent(name)}`, undefined, fetchImpl);
  const users = (data.users as Array<{ id?: string | number; name?: string }>) ?? [];
  // Fail closed: require an EXACT name match. Never fall back to users[0] — on a
  // shared/public coordinator that would mint the box's key against an arbitrary
  // user if headscale ever returned an unfiltered list.
  const user = users.find((u) => u.name === name);
  if (!user || user.id === undefined) throw new MeshError(`the coordinator has no user '${name}'`);
  return String(user.id);
}

export type Node = {
  id: string;
  name: string;
  ips: string[];
  online: boolean;
  lastSeen: string;
  tags: string[];
  // The pre-auth key this node joined with (headscale v0.29 node.preAuthKey.id);
  // how the users API tells which invite was activated. Absent for a node with none.
  preAuthKeyId?: string;
};

// The nodes the coordinator knows — the box itself (tag:box) and every member
// laptop (tag:member). Mirrors `nufi-box members` (GET /api/v1/node). v0.29.3
// lists key-derived tags under `tags` (not forcedTags/validTags).
export async function listNodes(cfg: MeshConfig, fetchImpl: typeof fetch = fetch): Promise<Node[]> {
  const data = await api(cfg, 'GET', '/api/v1/node', undefined, fetchImpl);
  const nodes = (data.nodes as Array<Record<string, unknown>>) ?? [];
  return nodes.map((n) => ({
    id: String(n.id ?? ''),
    name: String(n.name ?? n.givenName ?? ''),
    ips: (n.ipAddresses as string[]) ?? [],
    online: Boolean(n.online),
    lastSeen: String(n.lastSeen ?? ''),
    tags: (n.tags ?? n.validTags ?? n.forcedTags ?? []) as string[],
    preAuthKeyId: (() => {
      const id = (n.preAuthKey as { id?: string | number } | undefined)?.id;
      return id === undefined || id === null ? undefined : String(id);
    })(),
  }));
}

// Remove one node by id (DELETE /api/v1/node/{id}) — that laptop can no longer
// reach the box until invited again. By id, not name: headscale allows two
// nodes to share a name, so a name would be ambiguous (lib/mesh.sh refuses it).
export async function revokeNode(cfg: MeshConfig, id: string, fetchImpl: typeof fetch = fetch): Promise<void> {
  await api(cfg, 'DELETE', `/api/v1/node/${encodeURIComponent(id)}`, undefined, fetchImpl);
}

// How long a fleet enrolment key (and its share link) stays valid: a deployment
// window, not a single sitting. Seven days.
export const FLEET_TTL_MS = 7 * 24 * 3600_000;
export const FLEET_TTL_SECONDS = FLEET_TTL_MS / 1000;

// Mint a non-ephemeral tag:member pre-auth key. Single-use + one hour for a
// normal invite; reusable + a deployment window for a fleet invite. Mirrors
// lib/mesh.sh's mesh_preauth.
async function mintKey(
  cfg: MeshConfig,
  opts: { reusable: boolean; ttlMs: number },
  now: () => number,
  fetchImpl: typeof fetch,
): Promise<{ id: string; key: string }> {
  const uid = await userId(cfg, 'box', fetchImpl);
  const expiration = new Date(now() + opts.ttlMs).toISOString();
  const data = await api(cfg, 'POST', '/api/v1/preauthkey', {
    user: uid,
    reusable: opts.reusable,
    ephemeral: false,
    expiration,
    aclTags: ['tag:member'],
  }, fetchImpl);
  const pk = data.preAuthKey as { id?: string | number; key?: string } | undefined;
  if (!pk?.key) throw new MeshError('the coordinator returned no pre-auth key');
  if (pk.id === undefined || pk.id === null || String(pk.id) === '') {
    throw new MeshError('the coordinator returned a pre-auth key with no id');
  }
  return { id: String(pk.id), key: pk.key };
}

// A single-use, one-hour tag:member key — the key one laptop uses to join.
export function mintMemberKey(
  cfg: MeshConfig,
  now: () => number = Date.now,
  fetchImpl: typeof fetch = fetch,
): Promise<string> {
  return mintKey(cfg, { reusable: false, ttlMs: 3600_000 }, now, fetchImpl).then((k) => k.key);
}

// Same key, but with headscale's key id too — the users API stores the id so it
// can later tell whether a node joined with this key.
export function mintMemberKeyWithId(
  cfg: MeshConfig,
  now: () => number = Date.now,
  fetchImpl: typeof fetch = fetch,
): Promise<{ id: string; key: string }> {
  return mintKey(cfg, { reusable: false, ttlMs: 3600_000 }, now, fetchImpl);
}

// A REUSABLE tag:member key valid for a deployment window — one enrolment code
// many machines join with (fleet / MDM rollout), instead of one invite each.
export function mintFleetKey(
  cfg: MeshConfig,
  now: () => number = Date.now,
  fetchImpl: typeof fetch = fetch,
): Promise<string> {
  return mintKey(cfg, { reusable: true, ttlMs: FLEET_TTL_MS }, now, fetchImpl).then((k) => k.key);
}

export type PreAuthKey = { id: string; used: boolean; expiration: string };

// The box user's pre-auth keys — used to tell a pending invite from an expired one.
export async function listKeys(cfg: MeshConfig, fetchImpl: typeof fetch = fetch): Promise<PreAuthKey[]> {
  const uid = await userId(cfg, 'box', fetchImpl);
  const data = await api(cfg, 'GET', `/api/v1/preauthkey?user=${encodeURIComponent(uid)}`, undefined, fetchImpl);
  const keys = (data.preAuthKeys as Array<Record<string, unknown>>) ?? [];
  return keys
    .filter((k) => k.id !== undefined && k.id !== null && String(k.id) !== '')
    .map((k) => ({ id: String(k.id), used: Boolean(k.used), expiration: String(k.expiration ?? '') }));
}

// Expire a pre-auth key so its invite link stops working at once. headscale takes
// the key SECRET plus the user (not the key id). Callers treat this as best-effort.
export async function expireKey(cfg: MeshConfig, keySecret: string, fetchImpl: typeof fetch = fetch): Promise<void> {
  const uid = await userId(cfg, 'box', fetchImpl);
  await api(cfg, 'POST', '/api/v1/preauthkey/expire', { user: uid, key: keySecret }, fetchImpl);
}
