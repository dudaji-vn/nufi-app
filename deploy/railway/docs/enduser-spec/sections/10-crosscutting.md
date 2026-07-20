## Cross-Cutting Concerns

These requirements apply across all features above. Where a specific feature restates one of these
(e.g. a particular error message), the feature section is authoritative for that detail.

### Authentication & session
- **CC-1** Every authenticated screen in both NuFi Chat and NuFi Console requires a valid session.
  When the session is missing or expired, Chat redirects to sign-in and Console shows the
  *unauthorized* page that links to sign-in.
- **CC-2** The Chat and Console share the same login session (JWT). Signing out of Chat must
  invalidate access to the Console on the next request (verify: confirm the exact propagation
  behaviour and any token-refresh window in the running product).
- **CC-3** Session tokens are refreshed transparently while the user is active; the user should not
  be unexpectedly logged out during continuous use.

### Input validation
- **CC-4** All user inputs are validated on the client with inline, field-level error messages
  before submission; invalid forms cannot be submitted (the submit control is disabled or the
  submission is blocked).
- **CC-5** File uploads are validated against the NuFi limits (max 5 files per message, 20 MB per
  file, 50 MB total) and the allowed MIME-type list; violations are reported to the user and the
  offending file is rejected.

### Error handling & messaging
- **CC-6** Network or backend failures must surface a human-readable message (toast, banner, or
  inline) rather than failing silently or showing a raw stack trace.
- **CC-7** When the AI backend is unreachable, the model list falls back to a placeholder and chat
  sends fail with a visible error; the application must remain usable (the user can retry).
- **CC-8** Destructive actions (delete conversation, revoke API key, delete account, clear all
  chats) must require explicit confirmation before proceeding.

### Performance & responsiveness
- **CC-9** Streaming responses render incrementally; the UI must remain responsive (scroll, stop,
  navigate) while a response is streaming.
- **CC-10** Long conversation lists load incrementally (infinite scroll / pagination) rather than
  blocking on a single large fetch.
- **CC-11** Uploading and embedding Knowledge documents is asynchronous; the UI must show progress
  and not block other interaction.

### Localisation (i18n)
- **CC-12** The interface supports multiple languages selectable in Settings → General. All
  user-visible strings are sourced from translation files (no hard-coded English in localised
  screens). The default for NuFi is English (verify: confirm the default language configured for
  the deployment).
- **CC-13** The custom welcome message "Welcome to Nufi Chat." is shown on the chat landing screen.

### Accessibility
- **CC-14** Interactive controls expose accessible names (`aria-label` / labels) and validation
  errors use `role="alert"`; primary flows are operable by keyboard (verify: full keyboard-only
  traversal of each primary flow against the running product).
- **CC-15** Keyboard shortcuts documented in feature sections (e.g. Enter to send, Shift+Enter for
  newline) behave as specified.

### Theming & appearance
- **CC-16** The application supports light, dark, and system themes selectable in Settings; the
  selected theme persists across sessions.

### Security & privacy
- **CC-17** A newly created Console API key's secret is shown exactly **once** and cannot be
  retrieved afterwards; the stored/listed form is masked.
- **CC-18** A user can only see and manage **their own** conversations, agents, files, keys, and
  usage. Cross-user access must not be possible from the end-user UI.
- **CC-19** Temporary chats are not persisted to history; closing/leaving them discards their
  content.

### Browser support
- **CC-20** The application targets current versions of mainstream desktop browsers (Chrome, Edge,
  Firefox, Safari). The exact supported matrix should be confirmed and recorded by QA
  (verify: define and record the official supported-browser matrix).

### Known limitations / not-enabled features (NuFi)
The following upstream LibreChat capabilities are **not enabled** in the NuFi deployment and must
**not** be expected during testing (their controls should be absent, or, if visible, treated as
out of scope): web search, code interpreter / artifacts execution, voice input/output (TTS/STT),
social/OAuth sign-in via providers **other than Google** (GitHub, Discord, Facebook, Apple, OpenID,
SAML — note that **Google sign-in IS enabled**), password reset (`ALLOW_PASSWORD_RESET=false`), and
any chat endpoint other than **Nufi** and **Agents**. If any of these appear and are functional,
raise it as a configuration discrepancy.
