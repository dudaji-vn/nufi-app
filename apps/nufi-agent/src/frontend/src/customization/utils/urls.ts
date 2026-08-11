import {
  BASE_URL_API,
  HEALTH_CHECK_URL,
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
// "Built with NuFi Agent" (it comes from locales/en.json), but the
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
