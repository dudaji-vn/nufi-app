export const BASENAME = "";
export const PORT = 3000;
export const PROXY_TARGET = "http://localhost:7860";
export const API_ROUTES = ["^/api/v1/", "^/api/v2/", "/health"];
export const BASE_URL_API = "/api/v1/";
export const BASE_URL_API_V2 = "/api/v2/";
export const HEALTH_CHECK_URL = "/health_check";
// NuFi: dead code (no other file imports DOCS_LINK, named or via this
// module's default export) at the time of this sweep, so it isn't a live
// defect the way the other findings in this change were -- but it's a
// docs.langflow.org literal sitting in customization/ itself, the exact
// place a future change is most likely to start consuming it from without
// a second look. Fixed anyway, cheaply, before that happens. See
// nufi/README.md "Third-party brand/link sweep".
export const DOCS_LINK = "https://docs.app.nufi.me";

// NuFi: Studio does not own a login of its own -- the console mints the
// identity cookie Studio reads, and it lasts eight hours. When it expires the
// upstream frontend falls through to a local login form with a password field
// no NUFI member has. This is the door back. Baked at build time because the
// console's hostname is stable; override with VITE_NUFI_ENTER_URL for a
// deployment that is not nufi.me.
export const NUFI_ENTER_URL =
  import.meta.env.VITE_NUFI_ENTER_URL ?? "https://console.nufi.me/enter/studio";

export default {
  DOCS_LINK,
  BASENAME,
  PORT,
  PROXY_TARGET,
  API_ROUTES,
  BASE_URL_API,
  BASE_URL_API_V2,
  HEALTH_CHECK_URL,
};
