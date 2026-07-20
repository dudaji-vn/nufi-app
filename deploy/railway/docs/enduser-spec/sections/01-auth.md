## Authentication & Account Access

> **Scope note – NuFi deployment configuration**
> This section documents the authentication features active in the NuFi deployment
> (NuFi Chat is served at **https://chat.nufi.me**):
> `ALLOW_REGISTRATION=true`, `ALLOW_EMAIL_LOGIN=true`, `ALLOW_PASSWORD_RESET=false`,
> `ALLOW_SOCIAL_LOGIN=true`, `ALLOW_SOCIAL_REGISTRATION=true`.
> **Google** social sign-in **is enabled** (`GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET` are set
> in the deployment) and is documented below. The other social/OAuth providers (GitHub, Discord,
> Facebook, Apple, OpenID, SAML) are **not configured** (no client credentials) and are therefore
> omitted. Two-factor authentication (2FA) exists in code but is not covered here unless the user
> encounters the 2FA screen as a result of their account settings (verify: confirm whether any
> NuFi user has 2FA enabled before omitting that path).

---

### Registration

- **Purpose:** Allow a new user to create an email/password account on Nufi Chat.

- **Preconditions / access:**
  - `ALLOW_REGISTRATION=true` (server env). The API responds with `registrationEnabled: true`
    inside the startup-config payload; the registration route and link are only rendered when this
    flag is `true`.
  - The user is **not** already authenticated. Note: for the `/register` route, the outer
    `StartupLayout` is instantiated without an `isAuthenticated` prop, so the auth-redirect is
    **not currently enforced** — an authenticated user who navigates to `/register` will see the
    form rather than being redirected.
  - Route: `GET /register`. Rendered by the `Registration` component inside `StartupLayout`.

- **UI elements:**
  - Page heading: **"Create your account"** (`com_auth_create_account`)
  - Sub-heading link: **"Already have an account?"** + **"Login"** link to `/login`
    (`com_auth_already_have_account`, `com_auth_login`)
  - Field: **Full name** (`com_auth_full_name`), `type="text"`, `id="name"`, `data-testid="name"`
  - Field: **Username (optional)** (`com_auth_username`), `type="text"`, `id="username"`,
    `data-testid="username"` — optional, no `required` rule
  - Field: **Email** (`com_auth_email`), `type="email"`, `id="email"`, `data-testid="email"`
  - Field: **Password** (`com_auth_password`), `type="password"`, `id="password"`,
    `data-testid="password"`
  - Field: **Confirm password** (`com_auth_password_confirm`), `type="password"`,
    `id="confirm_password"`, `data-testid="confirm_password"`
  - Submit button: **"Continue"** (`com_auth_continue`), `aria-label="Submit registration"`,
    `variant="submit"`
  - All fields use a floating-label pattern (label visible above input when focused or filled;
    placeholder `" "` used as the peer-visible anchor)
  - Invalid fields receive `aria-invalid="true"` and a border in the destructive colour; inline
    error appears below the field as a `<span role="alert">`
  - On success, a banner appears in brand-purple tones with the success text and countdown
  - Form uses `mode: 'onChange'` — validation fires on each keystroke after first touch

- **Functional behavior:**
  1. **FR-1** The client POSTs the form data (name, username, email, password, confirm_password,
     and optionally a `token` query-parameter if the URL contains `?token=<invite>`) to the
     registration API endpoint via `useRegisterUserMutation`.
  2. **FR-2** While the request is in flight the submit button is disabled and a `Spinner`
     replaces the button label.
  3. **FR-3** On a successful API response the form hides and a success banner is shown. The
     banner text depends on whether the server has email delivery configured:
     - Email service configured: **"Please check your email to verify your email address."**
       (`com_auth_registration_success_generic`)
     - Email service not configured: **"Registration successful."**
       (`com_auth_registration_success_insecure`)
     Both variants are followed by **"Redirecting in N seconds..."**
     (`com_auth_email_verification_redirecting`) with a 3-second countdown.
  4. **FR-4** After the countdown reaches 0 the browser navigates to `/c/new` (replacing history
     entry).
  5. **FR-5** The submit button is disabled while `Object.keys(errors).length > 0` or
     `isSubmitting === true`.

- **Validation & errors:**

  | Field | Rule | Error message (translation key → English) |
  |---|---|---|
  | Full name | required | `com_auth_name_required` → "Name is required" |
  | Full name | minLength 3 | `com_auth_name_min_length` → "Name must be at least 3 characters" |
  | Full name | maxLength 80 | `com_auth_name_max_length` → "Name must be less than 80 characters" |
  | Username | minLength 2 (when provided) | `com_auth_username_min_length` → "Username must be at least 2 characters" |
  | Username | maxLength **80** (enforced) | `com_auth_username_max_length` → "Username must be less than 20 characters" (**code bug**: the enforced limit is 80 characters but the error message says "20 characters") |
  | Email | required | `com_auth_email_required` → "Email is required" |
  | Email | maxLength 120 | `com_auth_email_max_length` → "Email should not be longer than 120 characters" |
  | Email | pattern `/\S+@\S+\.\S+/` | `com_auth_email_pattern` → "You must enter a valid email address" |
  | Password | required | `com_auth_password_required` → "Password is required" |
  | Password | minLength (default 8, or `minPasswordLength` from server config) | `com_auth_password_min_length` → "Password must be at least 8 characters" |
  | Password | maxLength 128 | `com_auth_password_max_length` → "Password must be less than 128 characters" |
  | Confirm password | must equal Password field value | `com_auth_password_not_match` → "Passwords do not match" |

  - Server-side errors (e.g. duplicate email) are returned in `error.response.data.message` and
    displayed prepended with **"There was an error attempting to register your account. Please
    try again."** (`com_auth_error_create`) followed by the server message.

- **Edge cases:**
  - **Duplicate email:** Server returns an error; the error message from `response.data.message`
    is shown beneath the `com_auth_error_create` prefix.
  - **Captcha (Turnstile):** If `startupConfig.turnstile.siteKey` is set, the Cloudflare
    Turnstile widget is rendered and the submit button stays disabled until a valid token is
    obtained. In NuFi's current deployment, verify whether `TURNSTILE_SITE_KEY` is configured.
  - **Invite-token registration:** If the URL contains `?token=<value>`, the token is forwarded
    to the API. The UI behaves identically; any additional restriction is enforced server-side.
  - **Already authenticated:** For `/register` the redirect is **not enforced** (the outer
    `StartupLayout` receives no `isAuthenticated` prop), so an already-authenticated user sees the
    registration form rather than being redirected to `/c/new`.
  - **Network failure:** The mutation's `onError` fires, `isSubmitting` returns to `false`, and
    the server message is displayed. No automatic retry.

- **Acceptance criteria:**
  1. **AC-1** Given the user is unauthenticated and navigates to `/register`, When the page
     loads, Then a registration form is displayed with fields Full name, Username, Email,
     Password, Confirm password, and a **Continue** button (the button is enabled on initial load;
     it becomes disabled only after the first validation error fires).
  2. **AC-2** Given the user submits the form with a Full name shorter than 3 characters, When
     the field is changed, Then an inline error "Name must be at least 3 characters" appears
     below the field and the Continue button remains disabled.
  3. **AC-3** Given the user enters an email address that does not match the pattern
     `\S+@\S+\.\S+`, When the field value changes, Then "You must enter a valid email address"
     appears and the form cannot be submitted.
  4. **AC-4** Given the user enters a Password shorter than 8 characters, When the field is
     changed, Then "Password must be at least 8 characters" appears and the form cannot be
     submitted.
  5. **AC-5** Given the Confirm password field value does not match the Password field, When the
     field is changed, Then "Passwords do not match" appears and the form cannot be submitted.
  6. **AC-6** Given all fields are valid and the user clicks Continue, Then the button shows a
     spinner, the API is called, and on success a banner is displayed with the appropriate
     success message followed by a 3-second countdown.
  7. **AC-7** Given a successful registration, When the 3-second countdown completes, Then the
     browser navigates to `/c/new`.
  8. **AC-8** Given the registration API returns a duplicate-email error, Then the error banner
     displays "There was an error attempting to register your account. Please try again." followed
     by the server-supplied message, and the form is re-enabled.
  9. **AC-9** Given the user is already authenticated, When they navigate to `/register`, Then
     they are **not** currently redirected (the auth-redirect is not enforced on the outer
     `StartupLayout` for `/register`) — they will see the registration form. This AC is
     **not implemented** as described.

---

### Login (Email / Password)

- **Purpose:** Allow a registered user to authenticate with their email address and password.

- **Preconditions / access:**
  - `ALLOW_EMAIL_LOGIN=true` (server env). The API returns `emailLoginEnabled: true`; the
    `LoginForm` component is only mounted when `startupConfig.emailLoginEnabled === true`.
  - Route: `GET /login`. Rendered by the `Login` component inside `LoginLayout` /
    `StartupLayout`.
  - User must not be authenticated. An authenticated session triggers redirect to `/c/new`.

- **UI elements:**
  - Page heading: **"Welcome back"** (`com_auth_welcome_back`)
  - Sub-heading: **"Don't have an account?"** + **"Sign up"** link to `/register`
    (`com_auth_no_account`, `com_auth_sign_up`) — only shown when `registrationEnabled` is not
    `false`
  - Field: **Email address** (`com_auth_email_address`), `type="text"`, `id="email"`,
    `autoComplete="email"`. Label text: "Email address" (or "Username" if LDAP is configured —
    not applicable in NuFi).
  - Field: **Password** (`com_auth_password`), `type="password"`, `id="password"`,
    `autoComplete="current-password"`
  - Link: **"Forgot Password?"** (`com_auth_password_forgot`) — navigates to `/forgot-password`.
    This link is only rendered when `startupConfig.passwordResetEnabled === true`. In NuFi
    (`ALLOW_PASSWORD_RESET=false`) this link is **not shown**.
  - Submit button: **"Continue"** (`com_auth_continue`), `data-testid="login-button"`,
    `variant="submit"`. Shows a `Spinner` while submitting.
  - Error banner (above the form): rendered by `<ErrorMessage>` (`role="alert"`,
    `aria-live="assertive"`) when `error != null`
  - Resend verification banner: shown when the error contains `"422"` — see Validation section.
  - Left panel (desktop only): NuFi branding with the text **"Think it. Ask it. Done."** and
    logo `/assets/nufi-logo.svg`; hidden on mobile.
  - Theme selector (top-right corner, all screen sizes)

- **Functional behavior:**
  1. **FR-1** On form submit the client calls `loginUser.mutate({ email, password })` via
     `useLoginUserMutation`.
  2. **FR-2** On a successful API response with a standard (non-2FA) result, `isAuthenticated`
     is set to `true`, the JWT token is stored in memory and set as the Axios Authorization
     header, and the browser navigates to `/c/new` (or to a stored deep-link redirect — see
     Session & Token Persistence).
  3. **FR-3** On error, the error text from the API response is set via `setError`; the error
     message is mapped through `getLoginError` to a translation key and rendered in the
     `ErrorMessage` banner above the form. The URL is updated to `/login` (or
     `/login?redirect_to=<path>` if a pending deep link exists) using `replace: true`.
  4. **FR-4** While the request is in flight, the submit button is disabled and shows a
     `Spinner`.
  5. **FR-5** Cloudflare Turnstile: if `startupConfig.turnstile.siteKey` is present, the widget
     must succeed before the submit button is enabled (verify: confirm whether Turnstile is
     active in NuFi's deployment).
  6. **FR-6** Deep-link preservation: if the login page was reached via a `?redirect_to=<path>`
     query parameter or via `location.state.redirect_to`, the target path is persisted to
     `sessionStorage` under the key `post_login_redirect_to`. On successful login,
     `getPostLoginRedirect` resolves the stored path and navigates there instead of `/c/new`,
     provided the path passes `isSafeRedirect` (must start with `/`, not `//`, and must not
     contain a `/login` segment).

- **Validation & errors:**

  | Field | Rule | Error message |
  |---|---|---|
  | Email | required | `com_auth_email_required` → "Email is required" |
  | Email | maxLength 120 | `com_auth_email_max_length` → "Email should not be longer than 120 characters" |
  | Email | valid email (Zod) | `com_auth_email_pattern` → "You must enter a valid email address" |
  | Password | required | `com_auth_password_required` → "Password is required" |
  | Password | minLength (default 8) | `com_auth_password_min_length` → "Password must be at least 8 characters" |
  | Password | maxLength 128 | `com_auth_password_max_length` → "Password must be less than 128 characters" |

  Server-side errors mapped by HTTP status (via `getLoginError`):

  | Condition | HTTP status in error string | Error message (key → English) |
  |---|---|---|
  | Wrong credentials / unknown user | (no specific code — default) | `com_auth_error_login` → "Unable to login with the information provided. Please check your credentials and try again." |
  | Too many attempts | 429 | `com_auth_error_login_rl` → "Too many login attempts in a short amount of time. Please try again later." |
  | Account banned | 403 | `com_auth_error_login_ban` → "Your account has been temporarily banned due to violations of our service." |
  | Server error | 500 | `com_auth_error_login_server` → "There was an internal server error. Please wait a few moments and try again." |
  | Email not verified | 422 | `com_auth_error_login_unverified` → "Your account has not been verified. Please check your email for a verification link." |

  - **Unverified account (422) additional UI:** When the error string contains `"422"`,
    `showResendLink` is set to `true`. A secondary banner appears beneath the main error with
    the text **"Didn't receive the email?"** (`com_auth_email_verification_resend_prompt`) and a
    button **"Resend Email"** (`com_auth_email_resend_link`). Clicking it calls
    `useResendVerificationEmail` with the email currently in the form field.

- **Edge cases:**
  - **Empty form submission:** Client-side required-field validation fires; the submit button is
    not disabled by default on an empty form (no `errors` yet), but the `required` rule triggers
    on submit attempt and inline errors are shown.
  - **Wrong password:** API returns an error that does not contain 429 / 403 / 500 / 422, so the
    default `com_auth_error_login` message is displayed.
  - **Rate limiting (429):** The rate-limit message is displayed; the form is re-enabled for
    retry but will continue to fail until the rate-limit window expires.
  - **Already authenticated:** The `StartupLayout` effect detects `isAuthenticated === true` and
    navigates to `/c/new`.
  - **Startup config unavailable:** If the API call for startup config fails, an error banner is
    shown with **"There was an internal server error. Please wait a few moments and try again."**
    (`com_auth_error_login_server`) via `AuthLayout`'s `DisplayError` component.
  - **Network failure:** `loginUser.onError` fires; error message is displayed.

- **Acceptance criteria:**
  1. **AC-1** Given the user is unauthenticated and navigates to `/login`, When the page loads,
     Then the heading "Welcome back", email, and password fields are visible along with a
     "Continue" button.
  2. **AC-2** Given the user submits the form with the email field empty, Then the inline error
     "Email is required" appears and no API call is made.
  3. **AC-3** Given the user enters an invalid email format, Then "You must enter a valid email
     address" appears inline and the form cannot be submitted.
  4. **AC-4** Given the user submits valid credentials, When the API responds with success, Then
     the user is redirected to `/c/new` and the main chat interface is displayed.
  5. **AC-5** Given the user submits incorrect credentials, When the API responds with an error
     not matching 422/429/403/500, Then the banner "Unable to login with the information provided.
     Please check your credentials and try again." is displayed.
  6. **AC-6** Given the API returns a 422 (unverified email), Then the unverified-account error
     message is displayed AND a "Didn't receive the email? Resend Email" secondary banner appears.
  7. **AC-7** Given the user clicks "Resend Email" in the unverified banner, When the resend API
     call succeeds, Then the banner clears and no further error is shown.
  8. **AC-8** Given the user arrives at `/login?redirect_to=/c/some-conversation`, When they
     log in successfully, Then they are redirected to `/c/some-conversation` rather than
     `/c/new`.
  9. **AC-9** Given the API returns a 429 status, Then the error message "Too many login
     attempts in a short amount of time. Please try again later." is displayed.
  10. **AC-10** Given the user is already authenticated, When they navigate to `/login`, Then they
      are immediately redirected to `/c/new`.

---

### Sign in with Google (social login)

- **Purpose:** Allow a user to sign in — and, for a first-time user, register — using their Google
  account instead of email/password, via Google OAuth 2.0.

- **Preconditions / access:**
  - `ALLOW_SOCIAL_LOGIN=true` and Google credentials configured (`GOOGLE_CLIENT_ID` +
    `GOOGLE_CLIENT_SECRET`); the server then reports `googleLoginEnabled: true` and the
    `socialLogins` list includes `google`. Both hold in the NuFi deployment.
  - Creating a brand-new account via Google additionally requires `ALLOW_SOCIAL_REGISTRATION=true`
    (set in NuFi).
  - The user is not already authenticated.
  - Available on both the sign-in page (`/login`) and the registration page (`/register`) at
    **https://chat.nufi.me**.

- **UI elements:**
  - A divider showing **"OR"** (`com_auth_or`) separates the email/password form from the social
    button (shown because email login is also enabled).
  - **"Continue with Google"** button (`com_auth_google_login`), `data-testid="google"`, with the
    Google icon. It is a styled link pointing to `{DOMAIN_SERVER}/oauth/google` — in production,
    **https://chat.nufi.me/oauth/google**.
  - Only the Google button appears — no GitHub / Discord / Facebook / OpenID / SAML buttons (those
    providers are not configured).

- **Functional behavior:**
  1. **FR-1** When the user clicks **Continue with Google**, the browser navigates to the server's
     `/oauth/google` endpoint, which redirects to Google's OAuth consent screen.
  2. **FR-2** The user authenticates with Google and grants the requested scopes (openid, profile, email).
  3. **FR-3** Google redirects back to the configured callback (`GOOGLE_CALLBACK_URL` =
     `/oauth/google/callback`); the server verifies the response.
  4. **FR-4** If no NuFi account exists for that Google email and `ALLOW_SOCIAL_REGISTRATION=true`,
     a new account is created from the Google profile (name, email, avatar). If an account already
     exists **and it was also created via Google** (`provider = google`), the user is signed in to
     it. If the email belongs to a **password account** (`provider = local`), Google sign-in is
     **rejected** — see FR-7 / edge cases.
  7. **FR-7** **No account linking.** If an account already exists for that email but with a
     **different** sign-in provider (e.g. `local` for email/password), the server returns
     `AUTH_FAILED`. Passport's `failureRedirect` points to the server-side `/oauth/error` route,
     which in turn redirects the browser to `/login?redirect=false&error=AUTH_FAILED`. The Login
     page then detects `?error=AUTH_FAILED` and displays a **toast** with the message
     *"Authentication failed. Please check your login method and try again."*
     (`com_auth_error_oauth_failed`). There is **no** separate "Authentication Failed" page with
     a "Close Window" button in the failure path. LibreChat does **not** link a Google identity to
     an existing password account, and there is **no configuration option to enable merging**.
     (Source: `api/strategies/socialLogin.js`, `api/server/routes/oauth.js`, `client/src/components/Auth/Login.tsx`.)
  5. **FR-5** On success the server establishes the session (issues the JWT) and the browser lands
     in the chat at `/c/new`.
  6. **FR-6** On failure, or if the user cancels at Google, Passport follows the same
     `failureRedirect` path as FR-7: the server `/oauth/error` route redirects to
     `/login?redirect=false&error=AUTH_FAILED` and the Login page shows the
     `com_auth_error_oauth_failed` toast. (requires manual verification on the running product:
     confirm whether a Google-cancelled flow produces any difference in the visible toast or
     redirect compared with a provider-mismatch failure.)

- **States & edge cases:**
  - **User cancels Google consent:** no session is created; the browser is redirected back to
    `/login` where a `com_auth_error_oauth_failed` toast is displayed — *"Authentication failed.
    Please check your login method and try again."* (requires manual verification on the running
    product: confirm whether a cancelled consent produces a visibly different experience from a
    provider-mismatch rejection).
  - **Email already registered with email/password (no linking — confirmed):** Google sign-in is
    **rejected**; the browser is redirected to the `/login` page and a toast *"Authentication
    failed. Please check your login method and try again."* (`com_auth_error_oauth_failed`) is
    displayed. The two sign-in methods are **mutually exclusive per email** — an email registered
    with a password cannot later sign in with Google (and vice-versa). There is no merge feature
    and no flag to enable one. This is by design (prevents account takeover via a matching OAuth
    email).
  - **Full-page redirect, not a pop-up:** the flow is a full-page navigation, so any pop-up blocker
    is irrelevant.

- **Acceptance criteria:**
  1. **AC-1** Given Google sign-in is enabled, When the user opens `/login` or `/register`, Then a
     **Continue with Google** button is shown beneath an **"OR"** divider and no other
     social-provider buttons appear.
  2. **AC-2** Given the user clicks **Continue with Google**, Then the browser navigates to
     `https://chat.nufi.me/oauth/google` and on to Google's consent screen.
  3. **AC-3** Given a first-time user completes Google consent, Then a NuFi account is created from
     their Google profile and they land in the chat at `/c/new`.
  4. **AC-4** Given an existing user completes Google consent, Then they are signed in to their
     account and land at `/c/new`.
  5. **AC-5** Given the user cancels at Google's consent screen, Then no session is created, the
     browser returns to the Login page, and the `com_auth_error_oauth_failed` toast is displayed.
  6. **AC-6** Given an email that is already registered with email/password, When the user attempts
     **Continue with Google** with that same email, Then sign-in is **rejected**, the browser
     returns to the **Login page** and displays a toast *"Authentication failed. Please check your
     login method and try again."* (`com_auth_error_oauth_failed`), and **no account is linked or
     merged**.

---

### Logout

- **Purpose:** Allow an authenticated user to end their session and return to the login page.

- **Preconditions / access:**
  - User is authenticated (the main chat interface is visible).
  - The Account Settings popover is accessible from the sidebar (bottom of the left navigation
    panel).

- **UI elements:**
  - Trigger: User avatar / name button in the sidebar. `data-testid="nav-user"`,
    `aria-label` = value of `com_nav_account_settings`. Displays avatar and user's name (or
    email fallback).
  - Popover menu items (in order): My Files, Help & FAQ (if configured), Console (if configured),
    Settings, separator, **Log out**.
  - Log out item: `<Menu.MenuItem onClick={() => logout()}>` with a `LogOut` icon (Lucide) and
    the label **"Log out"** (`com_nav_log_out`).
  - The user's email address is displayed at the top of the popover as read-only text.

- **Functional behavior:**
  1. **FR-1** Clicking **"Log out"** calls `logout()` from `useAuthContext`, which calls
     `logoutUser.mutate(undefined)` (a `POST /api/auth/logout` via `useLogoutUserMutation`).
  2. **FR-2** On a successful logout API response (no `data.redirect`), `setUserContext` is
     called with `{ token: undefined, isAuthenticated: false, user: undefined, redirect: '/login' }`.
     The JWT token is cleared from memory and from the Axios Authorization header. The browser
     navigates to `/login`.
  3. **FR-3** On a logout API error, the same `setUserContext` call is made — the user is still
     treated as logged out and redirected to `/login`.
  4. **FR-4** If the server returns a `data.redirect` URL (relevant only for OpenID / SAML IdP
     sign-out — not applicable in NuFi's config because Google OAuth does not implement
     IdP-side sign-out), the token header is cleared immediately and
     `window.location.replace(data.redirect)` is called.

- **Validation & errors:**
  - No client-side input validation required.
  - On API error, the user is still signed out locally and redirected to `/login`; the error
    message is set via `doSetError` but may not be visible to the user if navigation occurs
    before it renders (verify: confirm whether an error toast appears on logout failure).

- **Edge cases:**
  - **Network failure during logout:** The `onError` branch fires; the user is still
    de-authenticated locally and redirected to `/login`.
  - **Logout called with a redirect argument:** The `logout(redirect)` signature stores the
    target in `logoutRedirectRef` and uses it after the API call instead of `/login`. For
    example, declining Terms & Conditions calls `logout('/login?redirect=false')`.
  - **Already unauthenticated:** Root returns `null` if `!isAuthenticated`; the user cannot
    reach the Account Settings menu.

- **Acceptance criteria:**
  1. **AC-1** Given the user is authenticated, When they click their avatar in the sidebar and
     then click "Log out", Then the application calls the logout API endpoint.
  2. **AC-2** Given the logout API call succeeds, Then the user is redirected to `/login`, the
     JWT token is cleared, and the chat interface is no longer accessible.
  3. **AC-3** Given the logout API call fails, Then the user is still redirected to `/login` and
     treated as signed out.
  4. **AC-4** Given the user has been logged out and navigates to `/c/new`, Then
     `useAuthRedirect` detects the unauthenticated state and redirects to `/login` (with the
     original path preserved as `redirect_to`).

---

### Session & Token Persistence

- **Purpose:** Maintain an authenticated session across page reloads and browser tabs without
  requiring the user to re-enter credentials within the session lifetime.

- **Preconditions / access:**
  - Applies to any authenticated user after successful login.

- **UI elements:**
  - No dedicated UI — behavior is transparent to the user.
  - On `/login` a `BlinkAnimation` wraps the NuFi logo on mobile while `isFetching` is `true`
    (indicating startup config is loading).

- **Functional behavior:**
  1. **FR-1** On mount of the `AuthContextProvider`, if no in-memory token exists, `silentRefresh`
     is called. It calls `refreshToken.mutate(undefined)` (a `POST /api/auth/refresh`).
  2. **FR-2** If the refresh API returns a valid token, `setUserContext` is called with the new
     token and `isAuthenticated: true`. The user is navigated to the stored deep-link redirect
     (from `sessionStorage` key `post_login_redirect_to`) or to the current URL path (if safe),
     or falls back to `/c/new`.
  3. **FR-3** If the refresh API returns no token or an error, the user is navigated to
     `buildLoginRedirectUrl()` (i.e. `/login?redirect_to=<current-path>` for protected paths).
  4. **FR-4** The JWT access token is stored **in memory only** (React state), not in
     `localStorage` or `sessionStorage`. This means closing all tabs ends the token lifetime.
  5. **FR-5** The refresh token is managed server-side via an HTTP-only cookie named
     `refreshToken`. Cookie options: `httpOnly: true`, `secure` (conditional on protocol),
     `sameSite` from `COOKIE_SAMESITE` env (default `strict`). The expiry is set per-user
     to `refreshTokenExpires` (no single hardcoded value).
  6. **FR-6** Any unauthenticated attempt to access a protected route triggers `useAuthRedirect`,
     which calls `buildLoginRedirectUrl(location.pathname, location.search, location.hash)` and
     navigates there after a 300 ms timeout.
  7. **FR-7** The startup-config fetch is gated: when the user is already authenticated,
     `StartupLayout` only fetches startup config if `startupConfig === null` (i.e., first load).

- **Edge cases:**
  - **Page reload:** `silentRefresh` fires on mount. If the server-side refresh-token cookie is
    still valid, the session is restored transparently and the user lands on the page they were
    viewing (or `/c/new`).
  - **Expired refresh token:** `silentRefresh` returns no token; the user is redirected to
    `/login?redirect_to=<current-path>`, preserving their intended destination.
  - **Multiple tabs:** Each tab runs `silentRefresh` independently. If the refresh token is
    revoked in one tab (logout), subsequent refreshes in other tabs will fail and redirect those
    tabs to `/login`.
  - **External redirect (OpenID/SAML sign-out):** Not applicable in NuFi's config (Google OAuth
    does not implement IdP-side sign-out).

- **Acceptance criteria:**
  1. **AC-1** Given the user is authenticated and reloads the page, When the page mounts, Then a
     silent token refresh is performed and the user remains on the chat interface without
     being redirected to login.
  2. **AC-2** Given the user's refresh token has expired and they reload the page, Then they are
     redirected to `/login?redirect_to=<original-path>`.
  3. **AC-3** Given an unauthenticated user navigates directly to `/c/some-id`, Then they are
     redirected to `/login?redirect_to=%2Fc%2Fsome-id` after at most 300 ms.
  4. **AC-4** Given the user logs in from the URL in AC-3, When login succeeds, Then they are
     navigated to `/c/some-id`.

---

### Password Reset

- **Purpose:** Allow a user who has forgotten their password to reset it via an emailed link.

> **NuFi deployment note:** `ALLOW_PASSWORD_RESET=false` in the NuFi `.env.example`. With this
> setting, `passwordResetEnabled` is `false` in the startup config. As a result:
> - The **"Forgot Password?"** link is **not rendered** in `LoginForm`
>   (guarded by `startupConfig.passwordResetEnabled`).
> - The routes `/forgot-password` and `/reset-password` still exist in the router and their
>   components would render if accessed directly by URL.
>
> **Testing scope:** Unless NuFi explicitly enables this feature, testers should verify that the
> "Forgot Password?" link is absent from the login form and that no password-reset path is
> surfaced in the UI. The functional details below describe the underlying implementation for
> completeness and for use if the feature is enabled in future.

- **Preconditions / access:**
  - `ALLOW_PASSWORD_RESET=true` (server env, `passwordResetEnabled: true` in startup config) —
    **not currently enabled in NuFi**.
  - Server must have email delivery configured (`emailEnabled: true`) for the link to be sent
    via email; if not configured, the reset link is returned directly in the API response and
    displayed on-screen (verify: NuFi email configuration).
  - Routes: `/forgot-password` (Request reset), `/reset-password?token=<t>&userId=<id>` (Set
    new password).

#### Password Reset — Request

- **UI elements:**
  - Page heading: **"Reset your password"** (`com_auth_reset_password`)
  - Field: **Email address** (`com_auth_email_address`), `type="email"`, `id="email"`,
    `autoComplete="off"`
  - Submit button: **"Continue"** (`aria-label="Continue with password reset"`)
  - Link: **"Back to Login"** (`com_auth_back_to_login`) — navigates to the login page

- **Functional behavior:**
  1. **FR-1** On submit, calls `useRequestPasswordResetMutation` with the supplied email.
  2. **FR-2** On success (email service configured): the header changes to **"Email Sent"**
     (`com_auth_reset_password_link_sent`) and the form is replaced by a success panel showing
     **"If an account with that email exists, an email with password reset instructions has been
     sent. Please make sure to check your spam folder."** (`com_auth_reset_password_if_email_exists`)
     plus a **"Back to Login"** link.
  3. **FR-3** On success (email service not configured): the API response includes `data.link`;
     the header changes to **"Reset your password"** and a direct link **"Click HERE to reset
     your password."** is displayed (HERE is the hyperlink anchor, rendered in uppercase via
     `com_auth_here`; the full text is assembled from `com_auth_click` + `com_auth_here` +
     `com_auth_to_reset_your_password`).
  4. **FR-4** On error: the same success-panel copy is shown as FR-2 (deliberately vague, to
     avoid disclosing whether an account exists for a given email).
  5. **FR-5** While the request is in flight, the submit button is disabled and shows a
     `Spinner`.

- **Validation & errors:**

  | Field | Rule | Error message |
  |---|---|---|
  | Email | required | `com_auth_email_required` → "Email is required" |
  | Email | minLength 3 | `com_auth_email_min_length` → "Email must be at least 6 characters" |
  | Email | maxLength 120 | `com_auth_email_max_length` → "Email should not be longer than 120 characters" |
  | Email | pattern `/\S+@\S+\.\S+/` | `com_auth_email_pattern` → "You must enter a valid email address" |

  The submit button is disabled while `errors.email` is truthy or `isLoading` is `true`.

#### Password Reset — Set New Password

- **UI elements:**
  - Page heading: **"Reset your password"** (`com_auth_reset_password`; changes to
    **"Password Reset Success"** on success)
  - Hidden fields: `token` and `userId` (read from `?token=` and `?userId=` query parameters)
  - Field: **Password** (`com_auth_password`), `type="password"`, `id="password"`,
    `autoComplete="current-password"`
  - Field: **Confirm password** (`com_auth_password_confirm`), `type="password"`,
    `id="confirm_password"`
  - Submit button: **"Continue"** (`aria-label` = `com_auth_submit_registration`), disabled
    while `errors.password` or `errors.confirm_password` is truthy, or while submitting
  - On success: a banner with **"You may now login with your new password."**
    (`com_auth_login_with_new_password`) and a **"Continue"** button that navigates to `/login`

- **Functional behavior:**
  1. **FR-1** On submit, calls `useResetPasswordMutation` with `{ token, userId, password,
     confirm_password }`.
  2. **FR-2** On error, sets the error state to `'com_auth_error_invalid_reset_token'`, which
     causes `AuthLayout`'s `DisplayError` to render: **"This password reset token is no longer
     valid."** (`com_auth_error_invalid_reset_token`) with a **"Click here"**
     (`com_auth_click_here`) link to `/forgot-password`.
  3. **FR-3** On success, the form is replaced by the success banner (FR-1 success state of
     `ResetPassword`).

- **Validation & errors:**

  | Field | Rule | Error message |
  |---|---|---|
  | Password | required | `com_auth_password_required` → "Password is required" |
  | Password | minLength (default 8) | `com_auth_password_min_length` → "Password must be at least 8 characters" |
  | Password | maxLength 128 | `com_auth_password_max_length` → "Password must be less than 128 characters" |
  | Confirm password | must match Password | `com_auth_password_not_match` → "Passwords do not match" |
  | token (hidden) | required | Hard-coded: "Unable to process: No valid reset token" |
  | userId (hidden) | required | Hard-coded: "Unable to process: No valid user id" |

  The `com_auth_error_invalid_reset_token` key alone renders: **"This password reset token is no
  longer valid."** The full visible banner is assembled by `AuthLayout` from three translation
  keys: `com_auth_error_invalid_reset_token` + a `<Link>` with `com_auth_click_here`
  ("Click here") + `com_auth_to_try_again` ("to try again."), producing the complete text:
  **"This password reset token is no longer valid. Click here to try again."**

- **Edge cases:**
  - **Invalid or expired token:** API returns an error; `com_auth_error_invalid_reset_token`
    banner is shown with a link back to `/forgot-password`.
  - **Missing token/userId in URL:** The hidden-field required rules fire client-side; the
    submit button may be enabled but the form submission will show "Unable to process: No valid
    reset token" / "No valid user id" inline errors.
  - **Password reset not enabled (`ALLOW_PASSWORD_RESET=false`):** The "Forgot Password?" link
    is hidden on the login page. Routes are still reachable by direct URL but the feature is
    not surfaced to users.

- **Acceptance criteria (when feature is enabled):**
  1. **AC-1** Given `passwordResetEnabled` is `true`, When the user views the login page, Then a
     "Forgot Password?" link is visible below the password field.
  2. **AC-2** Given `passwordResetEnabled` is `false` (NuFi default), When the user views the
     login page, Then no "Forgot Password?" link is present.
  3. **AC-3** Given the user navigates to `/forgot-password` and submits a valid email, Then the
     form is replaced by the "Email Sent" success panel regardless of whether the email exists
     (no account enumeration).
  4. **AC-4** Given the user submits an invalid email format on `/forgot-password`, Then the
     error "You must enter a valid email address" appears and no API call is made.
  5. **AC-5** Given the user follows the reset link and the token is valid, When they submit
     matching new passwords, Then the success banner "You may now login with your new password."
     is shown with a button navigating to `/login`.
  6. **AC-6** Given the user follows the reset link and the token is expired, When they submit
     the form, Then the error banner "This password reset token is no longer valid. Click here
     to try again." is displayed.
  7. **AC-7** Given the user submits the new-password form with non-matching passwords, Then
     "Passwords do not match" appears and the form cannot be submitted.

---

### Email Verification

- **Purpose:** Confirm a user's email address after registration when the server has email
  delivery configured.

- **Preconditions / access:**
  - Triggered automatically when the user clicks the verification link in the registration
    confirmation email.
  - Route: `/verify?token=<token>&email=<email>`
  - Applies when `emailEnabled: true` on the server (i.e., `EMAIL_SERVICE` or `EMAIL_HOST` +
    `EMAIL_USERNAME` + `EMAIL_PASSWORD` + `EMAIL_FROM` are all configured).
  - If email delivery is not configured, registration completes without requiring verification
    and the user is redirected to `/c/new` directly. (verify: confirm NuFi's email service
    configuration.)

- **UI elements:**
  - Full-screen centered layout (no sidebar, no nav).
  - While verifying: heading **"Verifying your email, please wait"**
    (`com_auth_email_verification_in_progress`) with a `Spinner`.
  - On success: heading **"Email verified successfully 🎉"**
    (`com_auth_email_verification_success`) with countdown text **"Redirecting in N seconds..."**.
  - On failure: heading **"Email verification failed 😢"** (`com_auth_email_verification_failed`)
    with the option to resend.
  - Resend prompt: **"Didn't receive the email?"** + button **"Resend Email"**
    (`com_auth_email_resend_link`).
  - Theme selector (bottom-left).

- **Functional behavior:**
  1. **FR-1** On mount, if both `token` and `email` query parameters are present, calls
     `useVerifyEmailMutation({ email, token })`.
  2. **FR-2** On success, shows the success heading and starts a 3-second countdown, then
     navigates to `/c/new`.
  3. **FR-3** On error, shows the failure heading and a "Resend Email" button.
  4. **FR-4** If `email` is present but `token` is missing, shows **"Verification failed, token
     missing 😢"** (`com_auth_email_verification_failed_token_missing`) and the resend button.
  5. **FR-5** If neither `token` nor `email` is present, shows **"Invalid email verification 🤨"**
     (`com_auth_email_verification_invalid`) and the resend button.
  6. **FR-6** Clicking **"Resend Email"** calls `useResendVerificationEmail({ email })`. On
     success: heading changes to **"Verification email resent successfully 📧"**
     (`com_auth_email_resent_success`) and the 3-second countdown begins. On error: heading
     changes to **"Failed to resend verification email 😢"** (`com_auth_email_resent_failed`).

- **Validation & errors:** No form input; all validation is server-side on the token.

- **Edge cases:**
  - **Already-verified token / expired token:** API returns an error; failure heading and resend
    button are shown.
  - **User clicks verify link twice:** Second call will fail (token already consumed); resend is
    offered.
  - **Email service not configured:** The `com_auth_registration_success_insecure` message is
    shown after registration, and no verification email is sent; this screen is never reached.

- **Acceptance criteria:**
  1. **AC-1** Given a valid `?token=<t>&email=<e>` URL, When the `/verify` page loads, Then the
     spinner and "Verifying your email, please wait" text are displayed while the API call is
     in flight.
  2. **AC-2** Given the verification API returns success, Then the heading "Email verified
     successfully" is shown and after 3 seconds the browser navigates to `/c/new`.
  3. **AC-3** Given the verification API returns an error, Then the "Email verification failed"
     heading and "Resend Email" button are displayed.
  4. **AC-4** Given the URL is missing the `token` parameter, Then the "Verification failed,
     token missing" heading and "Resend Email" button are displayed without making a verification
     API call.
  5. **AC-5** Given the user clicks "Resend Email" and the resend API succeeds, Then the heading
     changes to "Verification email resent successfully" and a 3-second redirect to `/c/new`
     begins.

---

### Validation Errors — Cross-Cutting Summary

This section consolidates all client-side validation messages used across auth screens for
ease of QA reference.

- **Error display pattern:** Inline errors are rendered as `<span role="alert" className="...
  text-destructive">` immediately below the invalid field. The Registration form evaluates on
  each change (`mode: 'onChange'`); the Login form evaluates on submit.
- **Banner errors** (above the form) use `<div role="alert" aria-live="assertive">` with a
  red/destructive border and background.
- **Success banners** use a brand-purple border and background.
- **Server-side errors** are surfaced through one of: (a) the `ErrorMessage` banner keyed to a
  translation string, (b) the `errorMessage` state in Registration prepended with
  `com_auth_error_create`, or (c) the `AuthLayout` `DisplayError` component for token errors.

All error messages are localizable. The English strings listed in the tables above are the
default values from `/client/src/locales/en/translation.json`.
