import { createHash, createPublicKey } from 'node:crypto';
import { exportJWK, generateKeyPair, importPKCS8, SignJWT } from 'jose';

export type IdentityClaims = {
  sub: string;
  email?: string;
  access: 'viewer' | 'editor' | 'admin';
};

export const ISSUER = process.env.OIDC_ISSUER ?? 'https://console.nufi.me';

const ALG = 'RS256';

type LoadedKey = { privateKey: CryptoKey; publicJwk: JsonWebKey & { kid: string }; kid: string };
let cached: Promise<LoadedKey> | undefined;

/**
 * The signing key comes from OIDC_PRIVATE_KEY_PEM.
 *
 * Falling back to a generated key is a development convenience and nothing
 * more: it is new on every boot, so a token minted before a restart stops
 * verifying after one, and two replicas would never agree. Anywhere that runs
 * more than one process, or expects a session to outlive a deploy, has to set
 * the variable.
 */
async function load(): Promise<LoadedKey> {
  const pem = process.env.OIDC_PRIVATE_KEY_PEM?.trim();

  // The public JWK is derived from the PUBLIC key, never by exporting the
  // private one. Two reasons, and the first is not theoretical: importPKCS8
  // returns a non-extractable CryptoKey, so exportJWK on it throws and every
  // JWKS request 500s -- which is invisible in a test that never sets a PEM.
  // The second is that a signing key has no business being extractable.
  let privateKey: CryptoKey;
  let jwk: JsonWebKey;

  if (pem) {
    privateKey = await importPKCS8(pem, ALG);
    jwk = createPublicKey(pem).export({ format: 'jwk' }) as JsonWebKey;
  } else {
    // Development only: a fresh key on every boot, so tokens do not survive a
    // restart and two replicas would never agree.
    const pair = await generateKeyPair(ALG, { extractable: true });
    privateKey = pair.privateKey;
    jwk = await exportJWK(pair.publicKey);
  }

  // Rebuilt field by field rather than by deleting the private ones. A
  // delete-list silently stops being complete when the key type changes;
  // an allow-list cannot leak a component nobody remembered to name.
  const kid = createHash('sha256').update(`${jwk.n}.${jwk.e}`).digest('base64url').slice(0, 16);
  const publicJwk = {
    kty: jwk.kty,
    n: jwk.n,
    e: jwk.e,
    alg: ALG,
    use: 'sig',
    kid,
  } as JsonWebKey & {
    kid: string;
  };

  return { privateKey, publicJwk, kid };
}

export function getSigningKey(): Promise<LoadedKey> {
  cached ??= load();
  return cached;
}

export async function getJwks(): Promise<{ keys: (JsonWebKey & { kid: string })[] }> {
  const { publicJwk } = await getSigningKey();
  return { keys: [publicJwk] };
}

/**
 * Mint an identity for exactly one consumer. The audience is required rather
 * than defaulted: a token that works in both products is a token that lets
 * either one impersonate a member to the other.
 */
export async function signIdentity(
  claims: IdentityClaims,
  audience: string,
  ttlSeconds: number,
): Promise<string> {
  const { privateKey, kid } = await getSigningKey();
  const now = Math.floor(Date.now() / 1000);
  return new SignJWT({ email: claims.email, access: claims.access })
    .setProtectedHeader({ alg: ALG, kid })
    .setSubject(claims.sub)
    .setIssuer(ISSUER)
    .setAudience(audience)
    .setIssuedAt(now)
    .setExpirationTime(now + ttlSeconds)
    .sign(privateKey);
}
