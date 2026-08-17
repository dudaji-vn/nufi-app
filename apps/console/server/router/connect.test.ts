import { afterEach, beforeEach, describe, expect, it, mock } from 'bun:test';

/**
 * The connect flow's security properties, exercised against a stubbed LiteLLM.
 *
 * These are the assertions worth keeping: a wrong origin must be refused, and
 * refused at `approve` too — not only at `begin`, which is a UI affordance a
 * caller can skip. Everything else about this endpoint is convenience; this is
 * the part that decides whether a page on the internet can walk away with a
 * signed-in user's gateway key.
 */

type Key = {
  key: string;
  token: string;
  key_alias: string | null;
  user_id: string | null;
  spend: number;
  max_budget: number | null;
  team_id: null;
  budget_duration: null;
  tpm_limit: null;
  rpm_limit: null;
  created_at: null;
  expires: null;
};

let keys: Key[] = [];
let generated = 0;
const provisioned: string[] = [];

mock.module('../lib/litellm.ts', () => ({
  listKeysForUser: async (userId: string) => keys.filter((k) => k.user_id === userId),
  generateKey: async (input: { user_id: string; key_alias?: string }) => {
    generated += 1;
    const row: Key = {
      key: `sk-test-${generated}`,
      token: `tok-${generated}`,
      key_alias: input.key_alias ?? null,
      user_id: input.user_id,
      spend: 0,
      max_budget: null,
      team_id: null,
      budget_duration: null,
      tpm_limit: null,
      rpm_limit: null,
      created_at: null,
      expires: null,
    };
    keys.push(row);
    return row;
  },
  deleteKey: async (token: string) => {
    keys = keys.filter((k) => k.token !== token);
  },
}));

mock.module('../lib/jit-provision.ts', () => ({
  ensureLiteLLMUser: async (user: { id: string }) => {
    provisioned.push(user.id);
    return {};
  },
}));

const { call } = await import('@orpc/server');
const { begin, approve } = await import('./connect.ts');

const context = { user: { id: 'user_1', email: 'a@nufi.me', role: 'USER' as const } };
const ALLOWED = 'https://agents.nufi.me';

beforeEach(() => {
  keys = [];
  generated = 0;
  provisioned.length = 0;
  process.env.AGENTS_ALLOWED_ORIGINS = `${ALLOWED}, http://localhost:3100`;
});

afterEach(() => {
  process.env.AGENTS_ALLOWED_ORIGINS = '';
});

describe('connect.begin', () => {
  it('describes the credential for an allowed origin', async () => {
    const res = await call(begin, { origin: ALLOWED, workspaceId: 'co_1' }, { context });
    expect(res.ok).toBe(true);
    if (!res.ok) throw new Error('unreachable');
    expect(res.origin).toBe(ALLOWED);
    expect(res.alias).toBe('nufi-agents:co_1');
    expect(res.replaces).toBe(0);
    expect(res.terms.budgetDuration).toBeString();
  });

  it('returns the canonical origin, not the caller’s spelling', async () => {
    const res = await call(
      begin,
      { origin: `${ALLOWED}/some/path`, workspaceId: 'co_1' },
      { context },
    );
    expect(res.ok && res.origin).toBe(ALLOWED);
  });

  /** Refused before any consent screen can render, so nobody can be talked into it. */
  it.each([
    ['an unrelated site', 'https://evil.example'],
    ['a suffix lookalike', 'https://evil-agents.nufi.me'],
    ['a subdomain of an attacker domain', 'https://agents.nufi.me.evil.example'],
    ['a downgraded scheme', 'http://agents.nufi.me'],
  ])('refuses %s', async (_label, origin) => {
    const res = await call(begin, { origin, workspaceId: 'co_1' }, { context });
    expect(res).toEqual({ ok: false, reason: 'origin_not_allowed' });
  });

  it('reports the feature as disabled rather than open when nothing is configured', async () => {
    process.env.AGENTS_ALLOWED_ORIGINS = '';
    const res = await call(begin, { origin: ALLOWED, workspaceId: 'co_1' }, { context });
    expect(res).toEqual({ ok: false, reason: 'disabled' });
  });

  it('counts what a reconnect would replace', async () => {
    await call(approve, { origin: ALLOWED, workspaceId: 'co_1' }, { context });
    const res = await call(begin, { origin: ALLOWED, workspaceId: 'co_1' }, { context });
    expect(res.ok && res.replaces).toBe(1);
  });
});

describe('connect.approve', () => {
  it('provisions the user, then mints a key aliased to the workspace', async () => {
    const res = await call(approve, { origin: ALLOWED, workspaceId: 'co_1' }, { context });
    expect(res.key).toBe('sk-test-1');
    expect(res.alias).toBe('nufi-agents:co_1');
    expect(provisioned).toEqual(['user_1']);
  });

  /**
   * `begin` is a UI affordance, not a gate — a caller can skip straight here.
   * If this check were missing, the allow-list would protect nothing.
   */
  it('refuses a disallowed origin even when begin was never called', async () => {
    await expect(
      call(approve, { origin: 'https://evil.example', workspaceId: 'co_1' }, { context }),
    ).rejects.toThrow(/not allowed/i);
    expect(keys).toBeEmpty();
  });

  it('replaces rather than accumulates on reconnect', async () => {
    const first = await call(approve, { origin: ALLOWED, workspaceId: 'co_1' }, { context });
    const second = await call(approve, { origin: ALLOWED, workspaceId: 'co_1' }, { context });

    expect(second.key).not.toBe(first.key);
    expect(keys.map((k) => k.key_alias)).toEqual(['nufi-agents:co_1']);
  });

  /**
   * A member connected to two Agents instances must be able to reconnect one
   * without silently cutting off the other — hence scoping the alias by
   * workspace rather than one key per person.
   */
  it('keeps a second workspace’s key intact', async () => {
    await call(approve, { origin: ALLOWED, workspaceId: 'co_1' }, { context });
    await call(approve, { origin: ALLOWED, workspaceId: 'co_2' }, { context });
    await call(approve, { origin: ALLOWED, workspaceId: 'co_1' }, { context });

    expect(keys.map((k) => k.key_alias).sort()).toEqual(['nufi-agents:co_1', 'nufi-agents:co_2']);
  });

  it('rejects a workspace id that is not a plain identifier', async () => {
    await expect(
      call(approve, { origin: ALLOWED, workspaceId: '../../etc/passwd' }, { context }),
    ).rejects.toThrow();
  });
});
