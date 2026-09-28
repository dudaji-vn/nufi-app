import { describe, expect, test } from 'bun:test';
import { meshConfig, mintMemberKey, MeshError } from '../src/mesh-api';

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

  test('a 401/403 becomes a clear MeshError naming the api key', async () => {
    const f = (() => Promise.resolve(new Response('no', { status: 403 }))) as unknown as typeof fetch;
    expect(mintMemberKey(CFG, Date.now, f)).rejects.toThrow(MeshError);
    await mintMemberKey(CFG, Date.now, f).catch((e) => expect(String(e.message)).toContain('MESH_API_KEY'));
  });

  test('a connection failure becomes an unreachable MeshError', async () => {
    const f = (() => Promise.reject(new Error('ECONNREFUSED'))) as unknown as typeof fetch;
    await mintMemberKey(CFG, Date.now, f).catch((e) => {
      expect(e).toBeInstanceOf(MeshError);
      expect(String(e.message)).toContain('unreachable');
    });
  });
});
