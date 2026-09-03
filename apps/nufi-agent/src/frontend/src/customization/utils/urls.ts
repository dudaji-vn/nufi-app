import {
  BASE_URL_API,
  HEALTH_CHECK_URL,
  NUFI_ENTER_URL,
} from "@/customization/config-constants";

export function getBaseUrl(): string {
  return BASE_URL_API || "/api/v1/";
}

export function getHealthCheckUrl(): string {
  return HEALTH_CHECK_URL || "/health";
}

// NuFi: this backs the "Built with Langflow" badge shown on a published
// flow's playground view (modals/IOModal/playground-modal.tsx, gated on
// ENABLE_PUBLISH -- true, so this is live). The rebrand transform
// (nufi/rebrand.ts) already rewrites the badge's own label text to
// "Built with NUFI Studio" (it comes from locales/en.json), but the
// transform deliberately leaves URL literals alone so real links keep
// working -- which meant the NuFi-labelled badge still sent a click to
// https://langflow.org, a competitor's homepage. Pointed at the app's own
// root instead of a NuFi marketing URL (none exists yet) so the badge is
// at worst self-referential, never an off-brand redirect. See
// nufi/README.md "Third-party brand/link sweep".
export const LangflowButtonRedirectTarget = () => {
  return "/";
};

// NuFi: shared Docs-link target for every customization-seam override that
// used to point at upstream's DOCS_URL/DATASTAX_DOCS_URL
// (constants/constants.ts -- "https://docs.langflow.org" /
// ENABLE_DATASTAX_LANGFLOW's DataStax variant, the latter dead in this fork
// since ENABLE_DATASTAX_LANGFLOW is hardcoded false in
// customization/feature-flags.ts). Two seams needed this in the same sweep:
// custom-AccountMenu.tsx (header user menu) and
// components/core/canvasControlsComponent/HelpDropdown.tsx (canvas Help
// dropdown, a core file -- no customization seam exists for it, so it's
// allowlisted directly; see check-fork-diff.sh's ALLOWLIST). Centralized
// here so both stay in sync instead of drifting to two different NuFi URLs.
//
// Unlike LangflowButtonRedirectTarget above (no NuFi marketing URL existed
// when that was fixed), a real one does for docs specifically:
// apps/docs in this monorepo, deployed as the `nufi-docs` Railway service
// with custom domain docs.app.nufi.me (Railway service domains, verified
// ACTIVE; also verified live with `curl -o /dev/null -w '%{http_code}'` ->
// 200). Dropping the Docs item entirely (the other option the task allowed)
// would regress the menu the same way stripping a real call-to-action
// would -- Docs is legitimate, unlike GitHub/Discord/X, so it stays,
// just repointed off upstream's project.
export const NUFI_DOCS_URL = "https://docs.app.nufi.me";

const REENTRY_STAMP_KEY = "nufi_reentry_at";
const REENTRY_COOLDOWN_MS = 30_000;

/** The console door, carrying where to land once the identity is renewed. */
export function getNufiEnterUrl(pathname: string, search: string): string {
  return `${NUFI_ENTER_URL}?next=${encodeURIComponent(`${pathname}${search}`)}`;
}

/**
 * Pure so it can be tested without a browser. Guards the one failure mode a
 * redirect-on-auth-failure has: if the console hands back a token Studio still
 * rejects, the two would bounce the member between them without end.
 */
export function shouldReenter(now: number, stamp: string | null): boolean {
  if (!stamp) return true;
  const at = Number(stamp);
  if (!Number.isFinite(at)) return true;
  return now - at > REENTRY_COOLDOWN_MS;
}

/**
 * Send the browser back through the console. Returns false when the cooldown
 * says not to, so the caller can fall through to the normal failure path.
 */
export function redirectToNufiEntry(): boolean {
  let stamp: string | null = null;
  try {
    stamp = window.sessionStorage.getItem(REENTRY_STAMP_KEY);
  } catch {
    // Storage can throw outright in a locked-down browser. A missing stamp
    // means "allowed", which is the same as the first visit.
  }
  if (!shouldReenter(Date.now(), stamp)) return false;
  try {
    window.sessionStorage.setItem(REENTRY_STAMP_KEY, String(Date.now()));
  } catch {
    // Without a stamp the cooldown cannot hold, but a member who cannot store
    // one still deserves the redirect they came for.
  }
  window.location.assign(
    getNufiEnterUrl(window.location.pathname, window.location.search),
  );
  return true;
}
