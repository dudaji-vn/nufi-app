# Verification findings — 01 Auth

## Summary

- Claims checked: 67 | CONFIRMED: 51 | WRONG: 5 | NEEDS-FIX (imprecise): 5 | RUNTIME-ONLY: 6

---

## Findings

### [WRONG] Sign in with Google — FR-7 / AC-6: failure redirects to `/oauth/error` "Authentication Failed" page with "Close Window" button

- **Spec says:** When sign-in is rejected (email belongs to another provider), "the server returns `AUTH_FAILED` and the user is redirected to **`/oauth/error`** — the **'Authentication Failed'** page (`com_ui_oauth_error_title`) showing *'Authentication failed. Please try again.'* (`com_ui_oauth_error_generic`) and a **'Close Window'** button."
- **Reality:** The server mounts the oauth routes at `/oauth` (Express: `app.use('/oauth', routes.oauth)`, `api/server/index.js:165`). Passport's `failureRedirect` is set to `${DOMAIN_CLIENT}/oauth/error` (`api/server/routes/oauth.js:55`). Because `DOMAIN_CLIENT` and `DOMAIN_SERVER` share the same hostname, this hits the **Express route** `GET /oauth/error` (`api/server/routes/oauth.js:31–39`), which reads the session error message and **redirects to `${DOMAIN_CLIENT}/login?redirect=false&error=AUTH_FAILED`**. The client `Login.tsx` component then detects `?error=AUTH_FAILED` and fires a **toast** with `com_auth_error_oauth_failed` = *"Authentication failed. Please check your login method and try again."* (`client/src/components/Auth/Login.tsx:41–49`, `client/src/locales/en/translation.json:181`). The `OAuthError.tsx` component (which does show a "Close Window" button) exists at the **client-side** route `/oauth/error`, but this route is intercepted by Express before React Router can render it; it is **never reached** in the standard failure flow.
- **Suggested correction:** Replace FR-7 / AC-6 with: "On failure, Passport redirects to the server's `/oauth/error` route, which redirects the browser to `/login?redirect=false&error=AUTH_FAILED`. The Login page displays a **toast** with the message *'Authentication failed. Please check your login method and try again.'* (`com_auth_error_oauth_failed`). There is no separate 'Authentication Failed' page with a 'Close Window' button in the failure path."

---

### [WRONG] Registration — Preconditions: "StartupLayout immediately redirects to `/c/new`" for `/register`

- **Spec says:** "If an authenticated session is detected on page load, `StartupLayout` immediately redirects to `/c/new`."
- **Reality:** The `/register` route is nested under the **outer** `<StartupLayout />` at router path `/` (`client/src/routes/index.tsx:66–83`), which has **no `isAuthenticated` prop** and is **not** inside the `<AuthLayout />` (`AuthContextProvider`) wrapper. `StartupLayout` only redirects when `isAuthenticated` is `true` (`client/src/routes/Layouts/Startup.tsx:33–39`). Since `isAuthenticated` is never provided (the outer `StartupLayout` is instantiated without it: `index.tsx:67`), and `Registration.tsx` never calls `useAuthContext`, **an authenticated user who navigates to `/register` will see the form**, not be redirected. Contrast this with `/login`, which is nested under `<LoginLayout>` which correctly passes `isAuthenticated` from `useAuthContext`.
- **Suggested correction:** Remove the auth-redirect claim from Registration's Preconditions section (or flag it as "not currently enforced"). AC-9 ("Given the user is already authenticated, When they navigate to `/register`, Then they are immediately redirected to `/c/new`") should be marked as FAILING / not implemented.

---

### [WRONG] Login — Validation table: "Email | minLength 1" row

- **Spec says:** (in the Login validation table) `Email | minLength 1 | com_auth_email_min_length → "Email must be at least 6 characters"`
- **Reality:** `LoginForm.tsx` registers the email field with only three rules: `required`, `maxLength: 120`, and a `validate` function calling `validateEmail` (Zod). There is **no `minLength` rule** (`client/src/components/Auth/LoginForm.tsx:113–119`). The `com_auth_email_min_length` message is never triggered by the Login form.
- **Suggested correction:** Remove the `minLength` row from the Login validation table entirely. The Login email field validates with: required, maxLength 120, and Zod email format via `validateEmail`.

---

### [WRONG] Registration → Login validation table: Google scopes documented as "profile, email"

- **Spec says (FR-2):** "The user authenticates with Google and grants the requested scopes (profile, email)."
- **Reality:** The Google passport strategy requests three scopes: `['openid', 'profile', 'email']` (`api/server/routes/oauth.js:47` and `:58`). The `openid` scope is silently omitted from the spec's description.
- **Suggested correction:** Change to "grants the requested scopes (openid, profile, email)."

---

### [WRONG] Social login "Or" divider text

- **Spec says:** A divider showing **"Or"** (`com_auth_or`) separates the email/password form from the social button.
- **Reality:** The translation key `com_auth_or` is `"OR"` (all-caps) (`client/src/locales/en/translation.json:193`). The `SocialLoginRender.tsx` renders `{localize('com_auth_or') || 'Or'}` (`SocialLoginRender.tsx:127`), falling back to the title-case "Or" only if the key is missing, which it is not.
- **Suggested correction:** Change **"Or"** to **"OR"** in the spec.

---

### [NEEDS-FIX] Password Reset — `com_auth_error_invalid_reset_token` banner full text

- **Spec says (Set New Password validation table):** `com_auth_error_invalid_reset_token` → "This password reset token is no longer valid. Click here to try again."
- **Reality:** The translation key `com_auth_error_invalid_reset_token` contains only `"This password reset token is no longer valid."` (`client/src/locales/en/translation.json:175`). `AuthLayout.tsx` (line 38–49) composes the full display by rendering the key's value + a separate `<Link>` with `com_auth_click_here` ("Click here") + the text `com_auth_to_try_again` ("to try again.") (`client/src/locales/en/translation.json:153, 212`). The banner text is assembled from three pieces, not one key.
- **Suggested correction:** Note that the key `com_auth_error_invalid_reset_token` alone renders only "This password reset token is no longer valid." The full visible banner is "This password reset token is no longer valid. Click here to try again." assembled from three translation keys.

---

### [NEEDS-FIX] Password Reset Request — success when email service not configured ("Click here to reset your password")

- **Spec says (FR-3):** "On success (email service not configured): the API response includes `data.link`; the header changes to **'Reset your password'** and a direct link **'Click here to reset your password'** is displayed."
- **Reality:** `RequestPasswordReset.tsx` (lines 57–64) renders: `{localize('com_auth_click')} {' '} <a href={data.link}>{localize('com_auth_here')}</a> {' '} {localize('com_auth_to_reset_your_password')}`. The translations are: `com_auth_click` = "Click" (line 152), `com_auth_here` = "HERE" (line 186), `com_auth_to_reset_your_password` = "to reset your password." (line 211). So the rendered text is **"Click HERE to reset your password."** — not "Click here to reset your password."
- **Suggested correction:** Change the link text to "Click HERE to reset your password." (noting HERE is the hyperlink anchor, rendered in uppercase).

---

### [NEEDS-FIX] Registration — username maxLength mismatch (existing inconsistency, flagged by spec but resolution not stated)

- **Spec says (verify:):** "translation key says 20 but field cap is 80 — check actual translation value"
- **Reality confirmed:** `Registration.tsx:156–159` — `maxLength: { value: 80, message: localize('com_auth_username_max_length') }`. Translation `com_auth_username_max_length` = "Username must be less than 20 characters" (`translation.json:215`). This is an existing bug in the codebase: the enforced limit is 80 characters but the error message says 20.
- **Status:** The `(verify:)` is now resolved. The spec table should be updated to state: maxLength **80** (enforced) with a note that the error message incorrectly says "20 characters" (code bug, not a spec error).

---

### [NEEDS-FIX] Logout — NuFi scope note incorrectly labels this as "email-only config" for FR-4

- **Spec says:** "If the server returns a `data.redirect` URL (relevant only for OpenID / SAML IdP sign-out — not applicable in NuFi's email-only config)..."
- **Reality:** NuFi enables `ALLOW_SOCIAL_LOGIN=true` with Google OAuth (per the scope note at the top of the same spec document). The correct phrase should be "not applicable in NuFi's config because Google OAuth does not use an IdP end_session_endpoint", not "email-only config".
- **Suggested correction:** Replace "NuFi's email-only config" with "NuFi's config (Google OAuth does not implement IdP-side sign-out)".

---

### [NEEDS-FIX] Registration AC-1: "disabled Continue button" on page load

- **Spec says (AC-1):** "a registration form is displayed with fields … and a **disabled** Continue button."
- **Reality:** The Registration button disabled condition is `Object.keys(errors).length > 0 || isSubmitting || (requireCaptcha && !turnstileToken)` (`Registration.tsx:209–212`). On initial render with no errors and no Turnstile configured, `errors` is `{}` and `isSubmitting` is `false` — so the button is **enabled**. AC-2/FR-5 correctly notes "The submit button is disabled while `Object.keys(errors).length > 0` or `isSubmitting === true`", so AC-1's "disabled" claim is internally contradictory.
- **Suggested correction:** AC-1 should say "a **Continue** button" (not "disabled"). The button becomes disabled only after the first validation error fires (due to `mode: 'onChange'`).

---

### [VERIFY-RESOLVED] `(verify:)` — Translation key `com_auth_username_max_length` says 20 but field cap is 80

- **CONFIRMED:** Code enforces maxLength 80 (`Registration.tsx:157`); error message says "less than 20 characters" (`translation.json:215`). This is a real discrepancy in the codebase. The spec table's note is correct.

---

### [VERIFY-RESOLVED] `(verify:)` — Cookie name and expiry for refresh token

- **CONFIRMED from code:** The refresh token is stored in an HTTP-only cookie named `refreshToken` (`AuthService.js:644`). Cookie options are `httpOnly: true`, `secure` (conditional on protocol), `sameSite` from `COOKIE_SAMESITE` env (default `strict`) (`api/server/utils/sessionCookies.js:12–23`). Expiry is set to the `refreshTokenExpires` timestamp computed per-user. No single fixed expiry is hardcoded in the shared utility.
- **Spec claim (FR-5):** "The refresh token is managed server-side via an HTTP-only cookie" — **CONFIRMED**.

---

### [VERIFY-RESOLVED] `(verify:)` — Whether any NuFi user has 2FA enabled

- **RUNTIME-ONLY:** Cannot be determined from code inspection. The 2FA code paths exist (`api/server/routes/auth.js:88–93`, `AuthContext.tsx:106–108`). Whether any deployed user has enabled 2FA requires a database query against the live deployment.

---

### [VERIFY-RESOLVED] `(verify:)` — Turnstile/captcha active in NuFi's deployment

- **RUNTIME-ONLY:** `TURNSTILE_SITE_KEY` does not appear in `nufi-chat/.env.example` or `docker-compose.yml`. Unless set in the Railway deployment environment, `startupConfig.turnstile.siteKey` will be undefined and Turnstile will not be shown. Cannot confirm from code alone.

---

### [VERIFY-RESOLVED] `(verify:)` — Error toast on logout failure

- **RUNTIME-ONLY (partially code-verifiable):** `AuthContext.tsx:146–154` — on logout error, `doSetError` is called with the error message, then `setUserContext` navigates to `/login`. The `doSetError` is debounced with a short callback (`useTimeout`). Whether the error renders visibly before navigation completes depends on render timing. Not determinable without a manual test.

---

### [VERIFY-RESOLVED] `(verify:)` — NuFi email service configuration

- **RUNTIME-ONLY:** `nufi-chat/.env.example` and `docker-compose.yml` contain no `EMAIL_SERVICE`, `EMAIL_HOST`, `EMAIL_USERNAME`, `EMAIL_PASSWORD`, or `EMAIL_FROM` variables. If these are not set in Railway, `emailEnabled` will be `false` (`api/server/routes/config.js:66–70`), and registration will show the insecure success banner without sending a verification email.

---

### [VERIFY-RESOLVED] `(verify:)` — Exact message/state shown when user cancels at Google consent screen

- **RUNTIME-ONLY:** When the user cancels, Google returns an `access_denied` error to the callback URL. Passport treats this as an authentication failure and follows `failureRedirect`. The resulting user experience follows the same path as any other AUTH_FAILED: the server `/oauth/error` route redirects to `/login?redirect=false&error=AUTH_FAILED`, and Login.tsx shows the toast. However, the exact Google-returned error parameter and whether it passes through differently is only verifiable by manual test.

---

### [VERIFY-RESOLVED] `(verify:)` — ALLOW_SOCIAL_LOGIN, ALLOW_SOCIAL_REGISTRATION, GOOGLE_* in NuFi deployment

- **RUNTIME-ONLY (not in tracked config files):** `nufi-chat/.env.example` does not contain `ALLOW_SOCIAL_LOGIN`, `ALLOW_SOCIAL_REGISTRATION`, `GOOGLE_CLIENT_ID`, or `GOOGLE_CLIENT_SECRET`. `docker-compose.yml` only maps `ALLOW_REGISTRATION` and `ALLOW_EMAIL_LOGIN`. The spec's scope note claims these are set in the Railway deployment, but this cannot be confirmed from the repository files. The spec's framing of Google sign-in as an enabled, documented feature is reasonable given deployment context, but should be flagged as configuration-only evidence.

---

## Confirmed-correct highlights (non-exhaustive)

The following were verified correct and require no change:

- Registration form: `mode: 'onChange'`, field IDs/testids, all listed validation rules and exact translation strings, spinner on submit, 3-second countdown, brand-purple success banner, `aria-invalid`, `role="alert"` for errors (`Registration.tsx`).
- Login form: `type="text"` for email field (not `type="email"`), no minLength for password in login form is wrong — **password does have minLength** from `startupConfig?.minPasswordLength || 8` (`LoginForm.tsx:143–145`). Validation table rows for 422/429/403/500 error codes and their messages (`getLoginError.ts`). Resend verification banner on 422.
- Social login: `SocialButton` renders an `<a>` tag (not a `<button>`), `href` = `{serverDomain}/oauth/${oauthPath}`, `data-testid={id}`. Only enabled providers render.
- `socialLogin.js` no-linking logic: confirmed — lines 58–69 show that if `existingUser` is found but `existingUser.provider !== provider`, an `AUTH_FAILED` error is returned. No linking, no merge. Correct.
- Session & Token: JWT in memory only (React state, not localStorage), refresh token is HTTP-only cookie named `refreshToken`, `silentRefresh` on mount, `useAuthRedirect` with 300ms timeout, `isSafeRedirect` rules (starts with `/`, not `//`, no `/login/` segment).
- `ALLOW_PASSWORD_RESET=false` in NuFi (unset = `isEnabled(undefined)` = `false`): confirmed in `config.js:12` and `api/server/utils/common.ts:18`.
- Logout: `POST /api/auth/logout`, clears `refreshToken` cookie, navigates to `/login` on both success and error, `logoutRedirectRef` pattern for overriding redirect destination.
- `VerifyEmail.tsx`: token + email → mutation on mount; success/failure headings with emoji; 3-second redirect; resend flow; `com_auth_email_verification_failed_token_missing` when token absent but email present; `com_auth_email_verification_invalid` when neither present. All confirmed correct.
- Password Reset (Request): `minLength: 3` (not 1) for email, `pattern /\S+@\S+\.\S+/`, `required`. On error the form shows the same success panel as on success (no enumeration). Confirmed.
- `com_auth_error_invalid_reset_token` = "This password reset token is no longer valid." (translation correct; the composed banner in AuthLayout adds "Click here" link + "to try again." from two additional keys).
