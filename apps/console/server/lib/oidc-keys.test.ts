import { describe, expect, it } from 'bun:test';
import { createLocalJWKSet, jwtVerify } from 'jose';
import { getJwks, ISSUER, signIdentity } from './oidc-keys.ts';

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

/**
 * The PEM path, which the tests above never touch because they leave
 * OIDC_PRIVATE_KEY_PEM unset and fall through to the generated key.
 *
 * That gap was not hypothetical. importPKCS8 returns a NON-EXTRACTABLE
 * CryptoKey, so deriving the public JWK by exporting the private key throws --
 * and since production always sets a PEM, every JWKS request would have
 * returned 500 while every test stayed green.
 */
describe('a configured signing key', () => {
  it('publishes a JWKS and signs a verifiable token from a PKCS#8 PEM', async () => {
    const { generateKeyPair: gen, exportPKCS8 } = await import('jose');
    const { privateKey } = await gen('RS256', { extractable: true });
    const pem = await exportPKCS8(privateKey);

    // The module caches its key, so the PEM path is exercised in a subprocess
    // with the variable set rather than by reaching into module state.
    const script = `
      process.env.OIDC_PRIVATE_KEY_PEM = ${JSON.stringify(pem)};
      const { getJwks, signIdentity, ISSUER } = await import('${import.meta.dir}/oidc-keys.ts');
      const { createLocalJWKSet, jwtVerify } = await import('jose');
      const jwks = await getJwks();
      const token = await signIdentity({ sub: 'pem-user', access: 'admin' }, 'nufi-studio', 300);
      const { payload } = await jwtVerify(token, createLocalJWKSet(jwks), {
        issuer: ISSUER, audience: 'nufi-studio',
      });
      console.log(JSON.stringify({ jwks, sub: payload.sub }));
    `;
    const proc = Bun.spawnSync(['bun', '-e', script]);
    const out = proc.stdout.toString().trim();
    expect(proc.exitCode, `stderr: ${proc.stderr.toString()}`).toBe(0);

    const { jwks, sub } = JSON.parse(out.split('\n').pop() as string);
    expect(sub).toBe('pem-user');
    expect(jwks.keys.length).toBe(1);
    for (const secret of ['d', 'p', 'q', 'dp', 'dq', 'qi']) {
      expect(jwks.keys[0]).not.toHaveProperty(secret);
    }
  });
});
