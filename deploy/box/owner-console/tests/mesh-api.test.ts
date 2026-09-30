import { describe, expect, test } from 'bun:test';
import { listNodes, meshConfig, mintFleetKey, mintMemberKey, revokeNode, FLEET_TTL_MS, MeshError } from '../src/mesh-api';

const CFG = { serverUrl: 'https://coordinator.internal', apiKey: 'k' };

// A fake headscale: GET user -> one user 'box' id 7; POST preauthkey -> a key,
// recording the request body so we can assert the tag and one-time shape.
function fakeHeadscale(posts: unknown[] = []) {
  const f = ((url: string, init: { method?: string; body?: string; headers?: Record<string, string> }) => {
    const u = String(url);
    if (u.endsWith('/api/v1/user?name=box')) {
      return Promise.resolve(new Response(JSON.stringify({ users: [{ id: 7, name: 'box' }] }), { status: 200 }));
    }
    if (u.endsWith('/api/v1/preauthkey') && init.method === 'POST') {
      posts.push(JSON.parse(init.body as string));
      return Promise.resolve(new Response(JSON.stringify({ preAuthKey: { key: 'k-member-abc' } }), { status: 200 }));
    }
    return Promise.resolve(new Response('not found', { status: 404 }));
  }) as unknown as typeof fetch;
  return f;
}

describe('meshConfig', () => {
  test('null when the box is LAN-only or has no api key', () => {
    expect(meshConfig({})).toBeNull();
    expect(meshConfig({ MESH_SERVER_URL: 'https://c' })).toBeNull();
    expect(meshConfig({ MESH_API_KEY: 'k' })).toBeNull();
  });
  test('config when both are present', () => {
    expect(meshConfig({ MESH_SERVER_URL: 'https://c', MESH_API_KEY: 'k' })).toEqual({ serverUrl: 'https://c', apiKey: 'k' });
  });
});

describe('mintMemberKey', () => {
  test('resolves the box user and mints a single-use tag:member key', async () => {
    const posts: unknown[] = [];
    const key = await mintMemberKey(CFG, () => 1_000_000, fakeHeadscale(posts));
    expect(key).toBe('k-member-abc');
    expect(posts).toHaveLength(1);
    const body = posts[0] as Record<string, unknown>;
    expect(body.user).toBe('7');                 // numeric id, as a string
    expect(body.aclTags).toEqual(['tag:member']);
    expect(body.reusable).toBe(false);
    expect(body.ephemeral).toBe(false);
    expect(typeof body.expiration).toBe('string');
  });

  test('a fleet key is REUSABLE, tag:member, and valid for the deployment window', async () => {
    const posts: unknown[] = [];
    const t0 = 1_000_000;
    const key = await mintFleetKey(CFG, () => t0, fakeHeadscale(posts));
    expect(key).toBe('k-member-abc');
    const body = posts[0] as Record<string, unknown>;
    expect(body.aclTags).toEqual(['tag:member']);
    expect(body.reusable).toBe(true);            // many machines enrol with one code
    expect(body.ephemeral).toBe(false);
    // expiry is the fleet window out from now, not one hour
    expect(new Date(body.expiration as string).getTime()).toBe(t0 + FLEET_TTL_MS);
  });

  test('a 401/403 becomes a clear MeshError naming the api key', async () => {
    const f = (() => Promise.resolve(new Response('no', { status: 403 }))) as unknown as typeof fetch;
    expect(mintMemberKey(CFG, Date.now, f)).rejects.toThrow(MeshError);
    await mintMemberKey(CFG, Date.now, f).catch((e) => expect(String(e.message)).toContain('MESH_API_KEY'));
  });

  test('fails closed when no user exactly matches (never mints against users[0])', async () => {
    // A coordinator that returns an unfiltered list without 'box' must NOT mint
    // against an arbitrary user — resolution requires an exact name match.
    const f = ((url: string) => {
      if (String(url).includes('/api/v1/user')) {
        return Promise.resolve(new Response(JSON.stringify({ users: [{ id: 1, name: 'someone-else' }] }), { status: 200 }));
      }
      return Promise.resolve(new Response('{}', { status: 200 }));
    }) as unknown as typeof fetch;
    await mintMemberKey(CFG, Date.now, f).catch((e) => {
      expect(e).toBeInstanceOf(MeshError);
      expect(String(e.message)).toContain("no user 'box'");
    });
    expect(mintMemberKey(CFG, Date.now, f)).rejects.toThrow(MeshError);
  });

  test('a connection failure becomes an unreachable MeshError', async () => {
    const f = (() => Promise.reject(new Error('ECONNREFUSED'))) as unknown as typeof fetch;
    await mintMemberKey(CFG, Date.now, f).catch((e) => {
      expect(e).toBeInstanceOf(MeshError);
      expect(String(e.message)).toContain('unreachable');
    });
  });
});

describe('listNodes', () => {
  test('maps the coordinator node list to a tidy shape', async () => {
    const f = (() => Promise.resolve(new Response(JSON.stringify({
      nodes: [
        { id: 1, name: 'nufi', ipAddresses: ['100.64.0.1'], online: true, lastSeen: '2026-09-29T00:00:00Z', tags: ['tag:box'] },
        { id: 2, name: 'ivy', ipAddresses: ['100.64.0.5'], online: false, lastSeen: '2026-09-28T00:00:00Z', tags: ['tag:member'] },
      ],
    }), { status: 200 }))) as unknown as typeof fetch;
    const nodes = await listNodes(CFG, f);
    expect(nodes).toHaveLength(2);
    expect(nodes[0]).toEqual({ id: '1', name: 'nufi', ips: ['100.64.0.1'], online: true, lastSeen: '2026-09-29T00:00:00Z', tags: ['tag:box'] });
    expect(nodes[1].id).toBe('2');
    expect(nodes[1].tags).toEqual(['tag:member']);
    expect(nodes[1].online).toBe(false);
  });

  test('an empty tailnet is an empty list, not a throw', async () => {
    const f = (() => Promise.resolve(new Response(JSON.stringify({}), { status: 200 }))) as unknown as typeof fetch;
    expect(await listNodes(CFG, f)).toEqual([]);
  });
});

describe('revokeNode', () => {
  test('DELETEs the node by id', async () => {
    const calls: string[] = [];
    const f = ((url: string, init: { method?: string }) => {
      calls.push(`${init.method} ${url}`);
      return Promise.resolve(new Response('{}', { status: 200 }));
    }) as unknown as typeof fetch;
    await revokeNode(CFG, '2', f);
    expect(calls).toEqual(['DELETE https://coordinator.internal/api/v1/node/2']);
  });

  test('a 401/403 surfaces as a MeshError', async () => {
    const f = (() => Promise.resolve(new Response('no', { status: 403 }))) as unknown as typeof fetch;
    expect(revokeNode(CFG, '2', f)).rejects.toThrow(MeshError);
  });
});
