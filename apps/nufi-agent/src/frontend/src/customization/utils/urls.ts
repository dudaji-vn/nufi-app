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
