import { describe, expect, it } from 'bun:test';
import { createLocalJWKSet, jwtVerify } from 'jose';
import { ISSUER, getJwks, signIdentity } from './oidc-keys.ts';

/**
 * The console is about to become the only thing standing between a chat
 * session and a signed-in session in two other products. These are the
 * assertions that matter once that is true.
 *
 * A token must verify against the key we publish, or every member is locked
 * out. A token minted for one product must NOT verify for the other, or the
 * audience field is decoration. And the published key set must never carry
 * private material — the one mistake that would let anyone mint identities.
 */
describe('identity tokens', () => {
  it('verifies against the published JWKS', async () => {
    const token = await signIdentity(
      { sub: 'user-1', email: 'a@b.c', access: 'editor' },
      'nufi-studio',
      300,
    );
    const jwks = createLocalJWKSet(await getJwks());
    const { payload } = await jwtVerify(token, jwks, {
      issuer: ISSUER,
      audience: 'nufi-studio',
    });
    expect(payload.sub).toBe('user-1');
    expect(payload.email).toBe('a@b.c');
    expect(payload.access).toBe('editor');
  });

  it('refuses a token minted for another audience', async () => {
    const token = await signIdentity({ sub: 'u', access: 'viewer' }, 'nufi-works', 300);
    const jwks = createLocalJWKSet(await getJwks());
    await expect(
      jwtVerify(token, jwks, { issuer: ISSUER, audience: 'nufi-studio' }),
    ).rejects.toThrow();
  });

  it('refuses a token that has expired', async () => {
    const token = await signIdentity({ sub: 'u', access: 'viewer' }, 'nufi-studio', -10);
    const jwks = createLocalJWKSet(await getJwks());
    await expect(
      jwtVerify(token, jwks, { issuer: ISSUER, audience: 'nufi-studio' }),
    ).rejects.toThrow();
  });

  it('never publishes private key material', async () => {
    const jwks = await getJwks();
    expect(jwks.keys.length).toBe(1);
    for (const k of jwks.keys) {
      // RSA private components. Any one of them in the public set is a leak.
      for (const secret of ['d', 'p', 'q', 'dp', 'dq', 'qi']) {
        expect(k).not.toHaveProperty(secret);
      }
      expect(k.kid).toBeTruthy();
      expect(k.alg).toBe('RS256');
    }
  });
});
