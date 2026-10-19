// Read-only "is there a newer box?" check — no host command, no docker.
//
// The box updates to `main` (nufi-box update), and every first-party image is
// rebuilt together from one commit, so the owner-console's own build revision
// (baked as NUFI_BUILD_REVISION at image build) IS the box's version. Comparing
// it to the latest commit on main answers "is an update available?" without
// running anything on the host — the update itself stays a host command.

const GITHUB_COMMITS_MAIN = 'https://api.github.com/repos/dudaji-vn/nufi-app/commits/main';

export type UpdateStatus = {
  current: string | null; // the box's build revision, null if the image never baked it
  latest: string | null; // newest commit on main, null if GitHub was unreachable
  updateAvailable: boolean | null; // null when either side is unknown
  checkedAt: string;
};

export type UpdateDeps = {
  revision: () => string;
  fetchLatest: () => Promise<string | null>;
  now: () => Date;
};

// Same-prefix compare so a 7-char short sha and a 40-char full sha still match.
function sameCommit(a: string, b: string): boolean {
  const n = Math.min(a.length, b.length);
  return n >= 7 && a.slice(0, n) === b.slice(0, n);
}

export async function checkUpdate(d: UpdateDeps): Promise<UpdateStatus> {
  const current = d.revision().trim() || null;
  const latest = await d.fetchLatest();
  const updateAvailable = current && latest ? !sameCommit(current, latest) : null;
  return { current, latest, updateAvailable, checkedAt: d.now().toISOString() };
}

// The newest commit sha on main, over the public, unauthenticated GitHub API
// (the same endpoint `nufi-box update` resolves against). Any failure — offline,
// rate-limited, non-2xx, malformed — is a null "could not determine", never a throw.
export async function fetchLatestMain(fetchImpl: typeof fetch = fetch): Promise<string | null> {
  try {
    const r = await fetchImpl(GITHUB_COMMITS_MAIN, {
      headers: { accept: 'application/vnd.github+json', 'user-agent': 'nufi-box-owner-console' },
    });
    if (!r.ok) return null;
    const j = (await r.json()) as { sha?: unknown };
    return typeof j.sha === 'string' && j.sha ? j.sha : null;
  } catch {
    return null;
  }
}
