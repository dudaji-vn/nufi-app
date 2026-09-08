import axios, {
  type AxiosError,
  type AxiosInstance,
  type AxiosRequestConfig,
} from "axios";
import * as fetchIntercept from "fetch-intercept";
import { useEffect } from "react";
import { IS_AUTO_LOGIN } from "@/constants/constants";
import { baseURL } from "@/customization/constants";
import { useCustomApiHeaders } from "@/customization/hooks/use-custom-api-headers";
import {
  getAxiosWithCredentials,
  getFetchCredentials,
} from "@/customization/utils/get-fetch-credentials";
import {
  isLoginPath,
  isLogoutPath,
  isSessionDiscoveryPath,
  redirectToNufiEntry,
} from "@/customization/utils/urls";
import useAuthStore from "@/stores/authStore";
import { useUtilityStore } from "@/stores/utilityStore";
import { BuildStatus, type EventDeliveryType } from "../../constants/enums";
import useAlertStore from "../../stores/alertStore";
import useFlowStore from "../../stores/flowStore";
import { checkDuplicateRequestAndStoreRequest } from "./helpers/check-duplicate-requests";
import { useLogout, useRefreshAccessToken } from "./queries/auth";

// Create a new Axios instance
const api: AxiosInstance = axios.create({
  baseURL: baseURL,
  withCredentials: getAxiosWithCredentials(),
});

// URL fragments for auth-maintenance endpoints. A 401/403 on any of these
// must NOT trigger the refresh-then-retry branch — that path itself goes
// through this same axios instance, so retrying would recurse. Exported
// for unit testing.
export const AUTH_MAINTENANCE_PATHS = [
  "/refresh",
  "/login",
  "/logout",
  "/auto_login",
];

// NuFi: when the member signed out, in milliseconds since the epoch.
//
// Signing out ends with the app asking /auto_login whether a session exists,
// and being told no -- the same 403 an expired identity produces. Without this
// the handoff below would read a deliberate sign-out as a lapsed session and
// put the member straight back in, making Log out impossible.
let lastLogoutAt = 0;
const LOGOUT_GRACE_MS = 15_000;

export function isAuthMaintenanceURL(url: string | undefined): boolean {
  if (!url) return false;
  return AUTH_MAINTENANCE_PATHS.some((path) => {
    const idx = url.indexOf(path);
    if (idx === -1) return false;
    const charAfter = url[idx + path.length];
    return (
      charAfter === undefined ||
      charAfter === "/" ||
      charAfter === "?" ||
      charAfter === "#"
    );
  });
}

function ApiInterceptor() {
  const autoLogin = useAuthStore((state) => state.autoLogin);
  const setErrorData = useAlertStore((state) => state.setErrorData);
  const accessToken = useAuthStore((state) => state.accessToken);
  const authenticationErrorCount = useAuthStore(
    (state) => state.authenticationErrorCount,
  );
  const setAuthenticationErrorCount = useAuthStore(
    (state) => state.setAuthenticationErrorCount,
  );

  const { mutate: mutationLogout } = useLogout();
  const { mutateAsync: mutationRenewAccessToken } = useRefreshAccessToken();
  const isLoginPage = location.pathname.includes("login");
  const customHeaders = useCustomApiHeaders();

  // NuFi: the interceptor below cannot rescue a session on this route --
  // `checkErrorCount` and `tryToRenewAccessToken` both bail on `isLoginPage`
  // before the renewal path runs, so the redirect they guard never fires. That
  // is fine for upstream, which has a password here; NuFi members do not. So a
  // browser that BOOTS on the login route is sent back through the console door
  // instead of being shown a form nobody can fill in.
  //
  // Deliberately mount-only, with no dependencies: signing out is an in-app
  // navigation that never remounts this component, so Log out still reaches the
  // login screen and stays there. Only a cold load gets the handoff, and
  // `redirectToNufiEntry`'s cooldown means a second arrival within thirty
  // seconds falls through -- which is also the escape hatch for anyone who
  // genuinely needs the upstream form.
  useEffect(() => {
    if (isLoginPath(window.location.pathname)) redirectToNufiEntry();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const setHealthCheckTimeout = useUtilityStore(
    (state) => state.setHealthCheckTimeout,
  );

  useEffect(() => {
    const unregister = fetchIntercept.register({
      request: (url, config) => {
        // Browser automatically sends cookies with requests (including HttpOnly cookies)
        // No need to manually add Authorization header from cookies

        if (!isExternalURL(url)) {
          for (const [key, value] of Object.entries(customHeaders)) {
            config.headers[key] = value;
          }
        }

        return [url, config];
      },
    });

    const interceptor = api.interceptors.response.use(
      (response) => {
        setHealthCheckTimeout(null);
        return response;
      },
      async (error: AxiosError) => {
        const isAuthenticationError =
          error?.response?.status === 403 || error?.response?.status === 401;

        const shouldRetryRefresh =
          (isAuthenticationError && !IS_AUTO_LOGIN) ||
          (isAuthenticationError && !autoLogin && autoLogin !== undefined);

        if (shouldRetryRefresh) {
          if (
            error?.config?.url?.includes("github") ||
            error?.config?.url?.includes("public")
          ) {
            return Promise.reject(error);
          }
          // Auth-maintenance endpoints must not trigger refresh themselves.
          // The refresh mutation uses this same axios instance, so if
          // ``/refresh`` returns 401 (expired refresh token) it would
          // re-enter this branch and recurse. Same for login/logout/
          // auto_login. Reject the original failure and let the caller
          // (typically the refresh mutation's catch block) drive logout.
          if (isAuthMaintenanceURL(error?.config?.url)) {
            await clearBuildVerticesState(error);
            // NuFi: this branch is where a lapsed session actually surfaces.
            // /auto_login answering 403 IS the discovery that there is no
            // session, and upstream can do nothing with it -- it has a password
            // form to fall back on and NuFi does not. So this is the moment to
            // go and get a new identity from the console, unless the member
            // just chose to leave.
            if (
              isSessionDiscoveryPath(error?.config?.url) &&
              Date.now() - lastLogoutAt > LOGOUT_GRACE_MS
            ) {
              redirectToNufiEntry();
            }
            return Promise.reject(error);
          }
          const stillRefresh = checkErrorCount();
          if (!stillRefresh) {
            return Promise.reject(error);
          }

          try {
            await tryToRenewAccessToken(error);
          } catch {
            // NuFi: the local refresh is not the only credential here. Studio's
            // session is minted by the console from the member's chat session,
            // so an expired one is renewable without a password -- send the
            // browser back through the door it came in by. The cooldown inside
            // guards against a console that keeps handing back a token Studio
            // rejects -- but the cooldown only narrows that loop, it does not
            // end it. What ends it is upstream's checkErrorCount() above:
            // after four authentication errors it logs out and returns false,
            // so this catch is never reached again. Named here because it is a
            // dependency on upstream code, which a resync can move or rename.
            if (redirectToNufiEntry()) {
              return Promise.reject(error);
            }
            await clearBuildVerticesState(error);
            return Promise.reject(error);
          }
          await clearBuildVerticesState(error);
          return await remakeRequest(error);
        }

        await clearBuildVerticesState(error);

        // Non-recoverable failure path: always reject so callers and
        // React Query see a real error rather than an undefined response.
        // This used to silently swallow auth errors under AUTO_LOGIN,
        // producing infinite "Loading models…" spinners on fresh installs.
        return Promise.reject(error);
      },
    );

    const isAuthorizedURL = (url) => {
      // NuFi: the two api.github.com entries were dropped along with the
      // calls that used them (controllers/API/index.ts getRepoStars). They
      // were dead config once nothing fetched those URLs, and leaving the
      // strings in the bundle would trip check-brand-css.sh's third-party
      // grep. raw.githubusercontent.com stays: it is upstream's example
      // store host, still referenced below.
      const authorizedDomains = [
        "https://raw.githubusercontent.com/langflow-ai/langflow_examples/main/examples",
        "auto_login",
      ];

      const authorizedEndpoints = ["auto_login"];

      try {
        const parsedURL = new URL(url);
        const isDomainAllowed = authorizedDomains.some(
          (domain) => parsedURL.origin === new URL(domain).origin,
        );
        const isEndpointAllowed = authorizedEndpoints.some((endpoint) =>
          parsedURL.pathname.includes(endpoint),
        );

        return isDomainAllowed || isEndpointAllowed;
      } catch (_e) {
        // Invalid URL
        return false;
      }
    };

    // Check for external url which we don't want to add custom headers to
    const isExternalURL = (url: string): boolean => {
      // NuFi: api.github.com removed here too -- this list decides which
      // hosts must NOT receive our auth headers, so an entry for a host we
      // no longer call is dead weight, and the literal would fail the
      // bundle grep. segment.io/sprig.com stay listed: they are upstream
      // telemetry hosts that never fire in this build (measured: zero
      // requests over a full session) but the list is the safety net if
      // they ever do.
      const EXTERNAL_DOMAINS = [
        "https://raw.githubusercontent.com",
        "https://api.segment.io",
        "https://cdn.sprig.com",
      ];

      try {
        const parsedURL = new URL(url);
        return EXTERNAL_DOMAINS.some((domain) => parsedURL.origin === domain);
      } catch (_e) {
        return false;
      }
    };

    // Request interceptor to add custom headers
    // Browser automatically sends cookies (including HttpOnly) with requests
    const requestInterceptor = api.interceptors.request.use(
      async (config) => {
        const controller = new AbortController();
        try {
          checkDuplicateRequestAndStoreRequest(config);
        } catch (e) {
          const error = e as Error;
          controller.abort(error.message);
          console.error(error.message);
        }

        const currentOrigin = window.location.origin;
        const requestUrl = new URL(config?.url as string, currentOrigin);

        // NuFi: remember a sign-out so the handoff below can tell it apart
        // from a session that simply ran out.
        if (isLogoutPath(config?.url)) lastLogoutAt = Date.now();

        const urlIsFromCurrentOrigin = requestUrl.origin === currentOrigin;
        if (urlIsFromCurrentOrigin) {
          for (const [key, value] of Object.entries(customHeaders)) {
            config.headers[key] = value;
          }
        }

        return {
          ...config,
          signal: controller.signal,
        };
      },
      (error) => {
        return Promise.reject(error);
      },
    );

    return () => {
      // Clean up the interceptors when the component unmounts
      api.interceptors.response.eject(interceptor);
      api.interceptors.request.eject(requestInterceptor);
      unregister();
    };
  }, [accessToken, setErrorData, customHeaders, autoLogin]);

  function checkErrorCount(): boolean {
    if (isLoginPage) return false;

    setAuthenticationErrorCount(authenticationErrorCount + 1);

    if (authenticationErrorCount > 3) {
      setAuthenticationErrorCount(0);
      mutationLogout();
      return false;
    }

    return true;
  }

  async function tryToRenewAccessToken(error: AxiosError) {
    if (isLoginPage) throw error;
    if (error.config?.headers) {
      for (const [key, value] of Object.entries(customHeaders)) {
        error.config.headers[key] = value;
      }
    }
    try {
      await mutationRenewAccessToken(undefined);
      setAuthenticationErrorCount(0);
    } catch (refreshError) {
      console.error(refreshError);
      const isNetworkError =
        (refreshError as AxiosError)?.response === undefined;
      if (!isNetworkError) {
        mutationLogout();
      }
      throw refreshError;
    }
  }

  async function clearBuildVerticesState(error) {
    if (error?.response?.status === 500) {
      const vertices = useFlowStore.getState().verticesBuild;
      useFlowStore
        .getState()
        .updateBuildStatus(vertices?.verticesIds ?? [], BuildStatus.BUILT);
      useFlowStore.getState().setIsBuilding(false);
    }
  }

  async function remakeRequest(error: AxiosError) {
    const originalRequest = error.config as AxiosRequestConfig;

    // Return the full AxiosResponse so when this value resolves the
    // outer interceptor promise, callers see a normal axios response and
    // can read ``response.data`` as usual. Returning ``response.data``
    // here would double-unwrap and produce ``undefined`` at the call site.
    return axios.request(originalRequest);
  }

  return null;
}

export type StreamingRequestParams = {
  method: string;
  url: string;
  onData: (event: object) => Promise<boolean>;
  onDataBatch?: (events: object[]) => Promise<boolean>;
  body?: object;
  onError?: (statusCode: number) => void;
  onNetworkError?: (error: Error) => void;
  buildController: AbortController;
  eventDeliveryConfig?: EventDeliveryType;
};

// Helper function to sanitize JSON strings
function sanitizeJsonString(jsonStr: string): string {
  // Replace NaN with null (valid JSON)
  return jsonStr
    .replace(/:\s*NaN\b/g, ": null")
    .replace(/\[\s*NaN\s*\]/g, "[null]")
    .replace(/,\s*NaN\s*,/g, ", null,")
    .replace(/,\s*NaN\s*\]/g, ", null]");
}

async function performStreamingRequest({
  method,
  url,
  onData,
  onDataBatch,
  body,
  onError,
  onNetworkError,
  buildController,
}: StreamingRequestParams) {
  const headers = {
    "Content-Type": "application/json",
    // this flag is fundamental to ensure server stops tasks when client disconnects
    Connection: "close",
  };

  const params: RequestInit = {
    method: method,
    headers: headers,
    signal: buildController.signal,
    credentials: getFetchCredentials(),
  };
  if (body) {
    params.body = JSON.stringify(body);
  }
  let current: string[] = [];
  const textDecoder = new TextDecoder();

  try {
    const response = await fetch(url, params);
    if (!response.ok) {
      if (onError) {
        onError(response.status);
      } else {
        throw new Error("Error in streaming request.");
      }
    }
    if (response.body === null) {
      return;
    }
    const reader = response.body.getReader();
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      const decodedChunk = textDecoder.decode(value);
      const all = decodedChunk.split("\n\n");

      // Parse all complete events from this chunk first
      const parsedEvents: object[] = [];
      for (const string of all) {
        if (string.endsWith("}")) {
          const allString = current.join("") + string;
          try {
            const sanitizedJson = sanitizeJsonString(allString);
            parsedEvents.push(JSON.parse(sanitizedJson));
            current = [];
          } catch (_e) {
            current.push(string);
          }
        } else {
          current.push(string);
        }
      }

      // Dispatch: batch callback processes all chunk events at once,
      // otherwise fall back to per-event processing.
      if (onDataBatch && parsedEvents.length > 0) {
        const shouldContinue = await onDataBatch(parsedEvents);
        if (!shouldContinue) {
          buildController.abort();
          return;
        }
      } else {
        for (const data of parsedEvents) {
          const shouldContinue = await onData(data);
          if (!shouldContinue) {
            buildController.abort();
            return;
          }
        }
      }
    }
    if (current.length > 0) {
      const allString = current.join("");
      if (allString) {
        const sanitizedJson = sanitizeJsonString(allString);
        const data = JSON.parse(sanitizedJson);
        await onData(data);
      }
    }
  } catch (e: unknown) {
    if (onNetworkError) {
      onNetworkError(e as Error);
    } else {
      throw e;
    }
  }
}

export { api, ApiInterceptor, performStreamingRequest };
