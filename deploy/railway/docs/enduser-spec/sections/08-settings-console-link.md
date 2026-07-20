## Account Menu, Settings & Console Link

This section documents the account dropdown menu, all settings tabs visible to NuFi Chat end users, and the Console link that opens the NuFi Console. All statements are grounded in the source files under `client/src/components/Nav/` and the NuFi deployment configuration at `librechat.yaml`.

---

### Account Dropdown Menu

- **Purpose:** Gives the authenticated user quick access to files, help, the NuFi Console, application settings, and logout — without navigating away from any conversation.
- **Preconditions / access:** User must be authenticated. The dropdown button (`data-testid="nav-user"`) appears at the bottom of the left sidebar. It is always visible in expanded sidebar state; in collapsed state it shows the avatar icon only.
- **UI elements:**
  - **Avatar + display name button** — triggers the menu. Shows user avatar (32 px expanded, 28 px collapsed) and name (`user.name`, falling back to `user.username`, then the localized string "User").
  - **Email address** (read-only note at top of menu, `role="note"`)
  - **Balance row** (read-only, format `Balance: <locale-formatted integer>` e.g. `Balance: 1,234`, formatted via `Intl.NumberFormat`) — shown only when `startupConfig.balance.enabled === true` AND the balance query returns data. Not configured in NuFi; not visible.
  - **My Files** — opens the My Files modal (`com_nav_my_files`).
  - **Help & FAQ** — opens `startupConfig.helpAndFaqURL` in a new tab (`com_nav_help_faq`). Shown only when `helpAndFaqURL !== '/'`; NuFi does not set `HELP_AND_FAQ_URL`, so the default `https://librechat.ai` is used and the entry is visible.
  - **Console** — opens the NuFi Console URL (`com` label is the literal string `"Console"` hardcoded in `AccountSettings.tsx`). Present only when `startupConfig.interface.customConsole.externalUrl` is a non-empty string. NuFi sets this via `CONSOLE_URL`.
  - **Settings** — opens the Settings modal (`com_nav_settings`).
  - **Log out** — calls `logout()` (`com_nav_log_out`).
- **Functional behavior:**
  1. FR-1: Clicking the avatar/name button opens the ariakit Menu; clicking outside or pressing Escape closes it.
  2. FR-2: "My Files" renders the `MyFilesModal` in-place (does not navigate).
  3. FR-3: "Help & FAQ" calls `window.open(helpAndFaqURL, '_blank')`.
  4. FR-4: "Console" calls `window.open(externalUrl, openNewTab === false ? '_self' : '_blank')`. NuFi sets `openNewTab: true` in `librechat.yaml`, so the tab always opens in a new browser tab.
  5. FR-5: "Settings" sets `showSettings = true`, rendering the `<Settings>` dialog.
  6. FR-6: "Log out" calls the auth context `logout()` function.
- **States & edge cases:**
  - Console entry is entirely absent from the DOM when `CONSOLE_URL` env var is empty or unset; `resolveExternalUrl` in the data-schemas package substitutes the env variable at server startup, and the client only renders the item when `externalUrl` is truthy.
  - Balance row is hidden in NuFi (balance feature not configured).
  - Help & FAQ is shown unless `HELP_AND_FAQ_URL=/` is explicitly set.
  - Menu placement: right-end when sidebar is collapsed, otherwise bottom-aligned.
- **Acceptance criteria:**
  1. AC-1: Given the user is authenticated and `CONSOLE_URL` is set, when the account dropdown is opened, then a "Console" menu item with a dashboard icon is present.
  2. AC-2: Given `CONSOLE_URL` is empty or unset, when the account dropdown is opened, then no "Console" item appears.
  3. AC-3: Given the user clicks "Console", when the click handler fires, then the browser opens the configured URL in a new tab (not the same tab).
  4. AC-4: Given the user clicks "Log out", when the action completes, then the session is terminated and the user is redirected to the login page.
  5. AC-5: Given the sidebar is collapsed, when the user interacts with the account button, then the menu opens to the right of the button (not above it).

---

### Settings Dialog — Tab Overview

The Settings dialog renders the following tabs. Most are always present; two are conditional:

| Tab | Label key | Always shown? | Condition |
|---|---|---|---|
| General | `com_nav_setting_general` | Yes | — |
| Chat | `com_nav_setting_chat` | Yes | — |
| Commands | `com_nav_commands` | Yes | — |
| Speech | `com_nav_setting_speech` | Yes | — |
| Data | `com_nav_setting_data` | Yes | — |
| Account | `com_nav_setting_account` | Yes | — |
| **Personalization** | `com_nav_setting_personalization` | **No** | Shown when `hasAnyPersonalizationFeature` is true — currently equivalent to the user having `MEMORIES OPT_OUT` permission (`usePersonalizationAccess`). NuFi does not configure a `memory:` section; whether this tab appears depends on whether the default user role grants `MEMORIES OPT_OUT` (requires manual verification on the running product: confirm if Personalization tab is visible to standard NuFi users). |
| **Balance** | `com_nav_setting_balance` | **No** | Shown when `startupConfig?.balance?.enabled` is true. Not applicable to NuFi (balance feature not configured); tab is absent. |

The sections below document each tab individually.

---

### Settings Dialog — General Tab

- **Purpose:** Controls global display preferences: theme, interface language, and several sidebar/scroll behaviours. These settings persist across sessions (lang stored in a cookie; theme/toggles in Recoil/localStorage).
- **Preconditions / access:** User opens Settings from the account dropdown. The "General" tab (gear icon, label `com_nav_setting_general`) is the default active tab.
- **UI elements:**
  - **Theme** (`com_nav_theme`) — dropdown with three options: "System" (`com_nav_theme_system`), "Dark" (`com_nav_theme_dark`), "Light" (`com_nav_theme_light`). Width 180 px.
  - **Language** (`com_nav_language`) — dropdown listing 42 locale values (Auto, English, Chinese Simplified, Chinese Traditional, Arabic, Bosnian, Danish, German, Spanish, Catalan, Estonian, Persian, French, Hebrew, Hungarian, Armenian, Icelandic, Italian, Norwegian Bokmål, Norwegian Nynorsk, Polish, Brazilian Portuguese, Portuguese, Russian, Slovak, Japanese, Georgian, Czech, Swedish, Korean, Lithuanian, Latvian, Vietnamese, Thai, Turkish, Uyghur, Dutch, Indonesian, Finnish, Slovenian, Tibetan, Ukrainian). Default is "Auto" (uses `navigator.language`). Max display height 256 px / 60 vh.
  - **Render user messages as markdown** (`com_nav_user_msg_markdown`) — toggle switch.
  - **Auto-Scroll to latest message on chat open** (`com_nav_auto_scroll`) — toggle switch.
  - **Keep screen awake during response generation** (`com_nav_keep_screen_awake`) — toggle switch.
  - **Switch to Chat History on new chat** (`com_nav_new_chat_switch_to_history`) — toggle switch.
  - **Archived chats** (`com_nav_archived_chats`) — row with "Manage" button (`com_ui_manage`) that opens the `ArchivedChatsTable` dialog.
- **Functional behavior:**
  1. FR-1: Selecting a theme immediately applies the theme (via `ThemeContext.setTheme`); no save button needed.
  2. FR-2: Selecting a language sets `document.documentElement.lang`, updates the Recoil `lang` atom, and writes a 365-day cookie `lang`. When "Auto" is selected, the resolved value is `navigator.language`.
  3. FR-3: Each toggle switch reads from and writes to its Recoil atom; state persists via localStorage across page reloads.
  4. FR-4: Clicking "Manage" next to "Archived chats" opens a full-screen dialog listing archived conversations with restore and delete options.
- **States & edge cases:**
  - Language "Auto": when the user selects "Auto", `changeLang` resolves `navigator.language` into the actual locale code (e.g., `en-US`) and stores that value in the Recoil atom. On the next render the dropdown displays the resolved locale label (e.g., "English") — **not** "Auto". The "Auto" option itself remains in the list but is no longer the active selection after it has been chosen once.
  - On small screens (`max-width: 767px`) the tab list renders horizontally at the top of the dialog; on larger screens it renders as a vertical sidebar.
- **Acceptance criteria:**
  1. AC-1: Given the user selects "Dark" from the Theme dropdown, when the selection is made, then the page immediately switches to dark mode without requiring a page reload.
  2. AC-2: Given the user selects "Vietnamese" from the Language dropdown, when the dialog is closed and reopened, then "Vietnamese" is still selected (persisted in cookie).
  3. AC-3: Given the user enables "Render user messages as markdown", when a new user message containing `**bold**` is sent, then the rendered message shows bold text.
  4. AC-4: Given the user clicks "Manage" next to "Archived chats", when the dialog opens, then it lists all archived conversations.

---

### Settings Dialog — Chat Tab

- **Purpose:** Controls per-conversation display and input behaviour: font size, text direction, a set of UX toggles, the advanced prompts editor mode, and conversation forking defaults.
- **Preconditions / access:** User selects the "Chat" tab (message-square icon, label `com_nav_setting_chat`) in the Settings dialog.
- **UI elements:**
  - **Message Font Size** (`com_nav_font_size`) — dropdown: "Extra Small", "Small", "Medium", "Large", "Extra Large" (CSS values `text-xs` through `text-xl`). Width 150 px.
  - **Chat direction** (`com_nav_chat_direction`) — button toggling between `ltr` and `rtl`. Default LTR.
  - **Always make new prompt versions production** (`com_nav_always_make_prod`) — toggle switch.
  - **Send prompts on select** (`com_nav_auto_send_prompts`) — toggle switch (tooltip: `com_nav_auto_send_prompts_desc`).
  - **Press Enter to send messages** (`com_nav_enter_to_send`) — toggle switch (tooltip: `com_nav_info_enter_to_send`).
  - **Maximize chat space** (`com_nav_maximize_chat_space`) — toggle switch.
  - **Center Chat Input on Welcome Screen** (`com_nav_center_chat_input`) — toggle switch.
  - **Open Thinking Dropdowns by Default** (`com_nav_show_thinking`) — toggle switch.
  - **Auto-expand tool details** (`com_nav_auto_expand_tools`) — toggle switch.
  - **Parsing LaTeX in messages (may affect performance)** (`com_nav_latex_parsing`) — toggle switch (tooltip: `com_nav_info_latex_parsing`).
  - **Save drafts locally** (`com_nav_save_drafts`) — toggle switch (tooltip: `com_nav_info_save_draft`).
  - **Scroll to the end button** (`com_nav_scroll_button`) — toggle switch.
  - **Save badges state** (`com_nav_save_badges_state`) — toggle switch (tooltip: `com_nav_info_save_badges_state`).
  - **Enable switching Endpoints mid-conversation** (`com_nav_modular_chat`) — toggle switch.
  - **Temporary Chat by default** (`com_nav_default_temporary_chat`) — toggle switch (tooltip: `com_nav_info_default_temporary_chat`).
  - **Advanced prompts editor** (`com_nav_advanced_prompts`) — toggle switch (tooltip: `com_nav_advanced_prompts_desc`). Switches the prompts editor between Simple and Advanced modes.
  - **Use default fork option** (`com_ui_fork_default`) — toggle switch. When enabled, reveals the "Default fork option" dropdown.
  - **Default fork option** (`com_ui_fork_change_default`) — dropdown (visible only when "Use default fork option" is on): "Visible messages only" (`com_ui_fork_visible`), "Include branches" (`com_ui_fork_branches`), "All messages to target level" (`com_ui_fork_all_target`). Tooltip: `com_nav_info_fork_change_default`.
  - **Start fork here** (`com_ui_fork_split_target_setting`) — toggle switch (tooltip: `com_nav_info_fork_split_target_setting`).
- **Functional behavior:**
  1. FR-1: Changing font size applies the Tailwind text class to message content immediately.
  2. FR-2: Toggling chat direction switches the chat container between `dir="ltr"` and `dir="rtl"`.
  3. FR-3: When "Use default fork option" is toggled off, the "Default fork option" dropdown is hidden.
  4. FR-4: All toggles persist to their Recoil atoms, which are backed by localStorage.
- **States & edge cases:**
  - "Start fork here" is always visible regardless of the "Use default fork option" state.
  - Toggling "Advanced prompts editor" off automatically sets "Always make new prompt versions production" to `true` (side effect in `AdvancedPrompts.handleChange`).
- **Acceptance criteria:**
  1. AC-1: Given the user sets font size to "Large", when a chat response is rendered, then the message text uses the `text-lg` CSS class.
  2. AC-2: Given the user enables "Use default fork option", when the setting is active, then the "Default fork option" dropdown appears below it.
  3. AC-3: Given "Press Enter to send messages" is off, when the user presses Enter in the chat input, then the message is not sent (requires Shift+Enter or the send button).

---

### Settings Dialog — Commands Tab

- **Purpose:** Lets the user enable or disable keyboard shortcut prefixes that trigger special chat actions. Each command is triggered by a specific character at the start of a message.
- **Preconditions / access:** User selects the "Commands" tab (command icon, label `com_nav_commands`) in the Settings dialog. The `+`-command is only shown when the user has `MULTI_CONVO USE` permission; the `/`-command is only shown when the user has `PROMPTS USE` permission.
- **UI elements:**
  - Section heading "Chat Commands" (`com_nav_chat_commands`) with an info hover card.
  - **@ Command** (`com_nav_at_command_description`): "Toggle command '@' for switching endpoints, models, presets, etc." — toggle switch.
  - **+ Command** (`com_nav_plus_command_description`): "Toggle command '+' for adding a multi-response setting" — toggle switch (shown with `MULTI_CONVO` access).
  - **/ Command** (`com_nav_slash_command_description`): "Toggle command '/' for selecting a prompt via keyboard" — toggle switch (shown with `PROMPTS` access).
- **Functional behavior:**
  1. FR-1: Disabling the `@` command prevents the model/endpoint picker from appearing when the user types `@` at the start of a message.
  2. FR-2: Disabling the `+` command prevents the multi-response panel from being triggered by `+`.
  3. FR-3: Disabling the `/` command prevents the prompt-picker overlay from appearing when `/` is typed.
- **States & edge cases:**
  - The `+` and `/` command rows are conditionally rendered based on permissions; a user without `MULTI_CONVO USE` will not see the `+` toggle.
  - NuFi exposes both `multiConvo: true` and `prompts: true` in `librechat.yaml`, so all three command toggles should be visible to standard users (requires manual verification on the running product: confirm the default user role grants `MULTI_CONVO USE` and `PROMPTS USE` permissions).
- **Acceptance criteria:**
  1. AC-1: Given the `@` command toggle is off, when the user types `@` at the start of the message input, then the endpoint/model selector does not appear.
  2. AC-2: Given the user does not have `MULTI_CONVO USE` permission, when the Commands tab is opened, then the `+` command row is not present.

---

### Settings Dialog — Speech Tab

- **Purpose:** Configures Speech-to-Text (STT) and Text-to-Speech (TTS) behaviour. The tab is always present in the Settings dialog (it is not gated by a server-side feature flag in the tab list). However, NuFi does not configure a speech backend, so STT and TTS functionality will not work unless a compatible engine is available.
- **Preconditions / access:** User selects the "Speech" tab (speech icon, label `com_nav_setting_speech`). The tab is unconditionally rendered in `Settings.tsx`.
- **UI elements — Simple mode (default):**
  - Mode switcher row: "Simple" (lightbulb icon) / "Advanced" (cog icon).
  - **Speech to Text** (`SpeechToTextSwitch`) — master toggle for STT.
  - **STT Engine** (`EngineSTTDropdown`) — dropdown selecting the STT backend.
  - **STT Language** (`LanguageSTTDropdown`) — language selection for recognition.
  - **Text to Speech** (`TextToSpeechSwitch`) — master toggle for TTS.
  - **TTS Engine** (`EngineTTSDropdown`) — dropdown selecting the TTS backend.
  - **Voice** (`VoiceDropdown`) — voice selection for the TTS engine.
- **UI elements — Advanced mode (additional controls):**
  - **Conversation Mode** (`ConversationModeSwitch`) — enables a continuous voice-conversation loop.
  - **Auto-Transcribe Audio** (`AutoTranscribeAudioSwitch`) — automatically transcribes microphone input.
  - **Decibel Threshold** (`DecibelSelector`) — shown only when Auto-Transcribe is on; sets the silence threshold.
  - **Auto-Send Text** (`AutoSendTextSelector`) — controls whether transcribed text is sent automatically.
  - **Automatic Playback** (`AutomaticPlaybackSwitch`) — plays TTS responses automatically.
  - **Cloud/browser voices** (`CloudBrowserVoicesSwitch`) — shown only when `engineTTS === 'browser'`.
  - **Playback Rate** (`PlaybackRate`) — slider or selector for TTS playback speed.
  - **Cache TTS** (`CacheTTSSwitch`) — caches TTS audio responses in the browser (`tts-responses` Cache Storage).
- **Functional behavior:**
  1. FR-1: On tab mount the component fetches `customConfigSpeech` from the server; if the response is not `not_found`, its values are applied as defaults only when no user preference exists in localStorage.
  2. FR-2: Switching to Advanced mode sets `advancedMode` Recoil atom to `true`, persisting across sessions.
  3. FR-3: If the stored `engineTTS` value is not `'browser'` or `'external'` (e.g., deprecated `'edge'`), it is silently reset to `'browser'`.
- **States & edge cases:**
  - **NuFi deployment note:** NuFi does not configure a speech backend (`librechat.yaml` has no `speech:` section). The tab is visible, but STT and TTS toggles will have no functional effect unless the user's browser supports the Web Speech API for browser-mode TTS/STT. (requires manual verification on the running product: confirm whether browser-native speech is accessible to end users or whether the tab should be noted as non-functional in NuFi.)
- **Acceptance criteria:**
  1. AC-1: Given the Speech tab is opened, when the user clicks "Advanced", then the additional controls (Conversation Mode, Auto-Transcribe, etc.) appear.
  2. AC-2: Given the TTS engine is "browser", when the user views the Advanced tab, then the "Cloud/browser voices" switch is visible.
  3. AC-3: Given NuFi has no speech backend configured, when the user enables Speech to Text, then the system does not throw an unhandled error (requires manual verification on the running product: confirm graceful degradation when no speech backend is active).

---

### Settings Dialog — Data Controls Tab

- **Purpose:** Manages conversation data, shared links, API credentials, and local browser caches. All actions in this tab are irreversible or have significant side effects; destructive operations each require explicit confirmation.
- **Preconditions / access:** User selects the "Data" tab (data icon, label `com_nav_setting_data`) in the Settings dialog.
- **UI elements:**
  - **Import conversation** (`com_ui_import_conversation_info`) — label + "Import" button with an upload icon. Opens a hidden `<input type="file" accept=".json">` for selecting a LibreChat-format JSON export file.
  - **Shared links** (`com_nav_shared_links`) — label + "Manage" button. Opens a paginated data table of public shared links with columns: Name (sortable, clickable external link), Date (sortable), Actions (open source chat, delete). Supports search/filter and infinite scroll (page size 25).
  - **Agent API Keys** (`com_ui_agent_api_keys`) — label + "Manage" button. Visible only when user has `REMOTE_AGENTS USE` permission. Opens a dialog listing existing API keys (name, key prefix, created date, last used date) with create and delete controls.
  - **Revoke all user provided credentials** (`com_ui_revoke_info`) — label + "Revoke" button (destructive variant). Triggers a confirmation dialog before calling `useRevokeAllUserKeysMutation`.
  - **Delete cache storage** (`com_nav_delete_cache_storage`) — label + "Delete" button (destructive variant). Clears the browser's `tts-responses` Cache Storage. Button is disabled when the cache is empty.
  - **Clear all chats** (`com_nav_clear_all_chats`) — label + "Delete" button (destructive variant). Opens a confirmation dialog before calling `useClearConversationsMutation`, which deletes all conversations server-side.
- **Functional behavior:**
  1. FR-1: "Import" accepts `.json` files only. File size is validated against `startupConfig.conversationImportMaxFileSize`; if exceeded, an error toast is shown. On success a success toast appears; on unknown file type, `com_ui_import_conversation_file_type_error` is shown.
  2. FR-2: "Manage" (Shared links) fetches links lazily (only when the dialog is open, `enabled: isOpen`). Deleting a link shows a per-link confirmation dialog with the link title before calling `useDeleteSharedLinkMutation`.
  3. FR-3: "Manage" (Agent API Keys) shows the key only once at creation time; after dismissal the full key cannot be retrieved again (only the prefix is stored).
  4. FR-4: "Revoke" (credentials) requires confirmation; on success closes the parent dialog if a `setDialogOpen` prop is provided.
  5. FR-5: "Delete" (cache) is disabled when `caches.open('tts-responses')` returns zero entries; re-enabled as soon as entries exist.
  6. FR-6: "Clear all chats" — after server deletion, `clearAllConversationStorage()` is called client-side and a new blank conversation is created via `newConversation()`.
- **States & edge cases:**
  - All destructive buttons open a modal with a confirm/cancel pattern before executing; clicking outside the ClearChats confirm state also cancels (via `useOnClickOutside`).
  - Agent API Keys section is hidden when the user lacks `REMOTE_AGENTS USE` permission. NuFi enables `agents: true` in `librechat.yaml`; the effective permission depends on the user's role configuration (requires manual verification on the running product: confirm the default user role grants `REMOTE_AGENTS USE`).
  - Shared links table shows an empty-state message when no public links exist.
  - Import is disabled while an upload is in progress (spinner replaces the import icon).
- **Acceptance criteria:**
  1. AC-1: Given the user selects a `.json` file larger than the server's `conversationImportMaxFileSize`, when the file is chosen, then an error toast with the maximum size is shown and no upload is attempted.
  2. AC-2: Given the user clicks "Delete" (Clear all chats) and confirms, when the mutation succeeds, then the sidebar conversation list is empty and a new blank chat is started.
  3. AC-3: Given the TTS cache is empty, when the Data tab is opened, then the "Delete" button in the "Delete cache storage" row is disabled.
  4. AC-4: Given the user creates an Agent API Key, when the creation dialog is first shown, then the full key is visible and copyable; when the dialog is closed and reopened, only the key prefix is visible.
  5. AC-5: Given the user clicks "Revoke" (credentials) and confirms, when the mutation succeeds, then all stored third-party API credentials are cleared from the server.

---

### Settings Dialog — Account Tab

- **Purpose:** Manages personal profile settings, profile picture, two-factor authentication, and permanent account deletion.
- **Preconditions / access:** User selects the "Account" tab (user icon, label `com_nav_setting_account`) in the Settings dialog.
- **UI elements:**
  - **Display username in messages** (`com_nav_user_name_display`) — toggle switch with an info hover card (`com_nav_info_user_name_display`). Controls whether the user's name or the generic "User" label appears above their messages in the chat.
  - **Profile Picture** (`com_nav_profile_picture`) — label + "Change Picture" button (with file-image icon). Opens the avatar editor dialog.
    - Avatar editor dialog: drag-and-drop area (accepts `.png`, `.jpg`, `.jpeg`; max size from `fileConfig.avatarSizeLimit`, default display 2 MB). After file selection: 280×280 circular preview (`AvatarEditor`), Zoom slider (1–5×, step 0.1) with Zoom In / Zoom Out buttons, Rotate 90° button, Reset button. Action buttons: Cancel (resets image state) and Upload (posts as `multipart/form-data` with `manual=true`).
  - **Two-factor authentication** (`com_ui_2fa_setup` / `com_ui_2fa_disable`) — shown only when `user.provider === 'local'`. Toggle that opens the 2FA wizard dialog.
    - Setup wizard phases: Setup → Scan QR → Verify → Backup. **No progress bar is shown during initial setup** (when `twoFactorEnabled` is `false`). The progress bar in the dialog header is only rendered when the user already has 2FA enabled (`twoFactorEnabled === true`) and is going through an update or re-confirm flow.
    - Disable phase: prompts for the current TOTP token or a backup code.
  - **Backup Codes** (`com_ui_backup_codes`) — shown only when `user.provider === 'local'` AND `user.twoFactorEnabled === true`. "Manage" button opens the backup codes dialog showing all 10 backup codes with used/unused status and a "Regenerate backup codes" action (requires TOTP or backup code verification).
  - **Delete account** (`com_nav_delete_account`) — shown when `startupConfig.allowAccountDeletion !== false`. Label + "Delete" button (destructive variant). Opens a confirmation dialog requiring the user to type their email address before the delete button unlocks. If 2FA is enabled, also requires a 6-digit TOTP or 8-character backup code.
- **Functional behavior:**
  1. FR-1: "Display username in messages" toggle writes the `UsernameDisplay` Recoil atom; change is reflected immediately in any open conversation.
  2. FR-2: "Change Picture" — uploading an image updates `user.avatar` in the Recoil `user` atom via `useUploadAvatarMutation`; the avatar in the account button updates without a page reload.
  3. FR-3: 2FA setup — clicking the toggle opens the wizard at the "Setup" phase, which generates a QR code (`useEnableTwoFactorMutation`). The user scans with an authenticator app, enters the 6-digit code to verify (`useVerifyTwoFactorMutation`), then confirms (`useConfirmTwoFactorMutation`). After confirmation, backup codes are displayed and can be downloaded as `backup-codes.txt`. Closing the dialog mid-flow triggers `disable2FAMutate` to roll back the pending secret.
  4. FR-4: 2FA disable — entering a valid TOTP or backup code calls `useDisableTwoFactorMutation`; on success `user.twoFactorEnabled` is set to `false` in Recoil and the wizard resets to the setup phase.
  5. FR-5: Delete account — the delete button in the confirmation dialog is locked (lock icon, 30% opacity) until the typed email matches `user.email` (case-insensitive). If 2FA is enabled, the TOTP/backup field must also be complete. On success, `logout()` is called automatically.
- **States & edge cases:**
  - "Two-factor authentication" and "Backup Codes" rows are hidden for OAuth-authenticated users (`user.provider !== 'local'`). NuFi uses local authentication by default; no OAuth providers (`google`, `github`, etc.) are configured in `librechat.yaml`. If the Railway deployment environment does not set OAuth env vars (`GOOGLE_CLIENT_ID`, etc.), local auth is the only provider and both rows are visible to all users. (requires manual verification on the running product: confirm no OAuth env vars are active in Railway.)
  - "Delete account" is hidden when `ALLOW_ACCOUNT_DELETION` env var is explicitly set to `false`. NuFi does not set this variable, so the default (`true`) applies and the option is visible.
  - Avatar uploads are rejected if the file exceeds `fileConfig.avatarSizeLimit`; an error toast shows the limit in human-readable form.
  - Closing the avatar dialog without uploading resets all editor state (scale, rotation, position, selected image).
- **Acceptance criteria:**
  1. AC-1: Given "Display username in messages" is enabled, when a user message is visible in the chat, then the user's name appears above the message bubble.
  2. AC-2: Given the user uploads a valid `.jpg` avatar and clicks "Upload", when the mutation succeeds, then the avatar displayed in the account dropdown button updates to the new image.
  3. AC-3: Given the user has not enabled 2FA, when they click the 2FA toggle, then the 4-phase wizard dialog opens at the "Setup" phase.
  4. AC-4: Given the user opens the Delete Account dialog and types an incorrect email, when they view the delete button, then it shows a lock icon and is disabled.
  5. AC-5: Given the user types the correct email and (if 2FA is active) enters a valid TOTP code, when they click the delete button, then the account is permanently deleted and the user is logged out.
  6. AC-6: Given `ALLOW_ACCOUNT_DELETION` is not set in the NuFi environment (default), when the Account tab is opened, then the "Delete account" row is visible.

---

### Console Link Behavior

- **Purpose:** Provides a direct entry point from NuFi Chat into the NuFi Console (administration / billing / project management interface) without requiring the user to remember a separate URL.
- **Preconditions / access:** `CONSOLE_URL` environment variable must be set in the NuFi deployment (configured in `docker-compose.yml` as `CONSOLE_URL: ${CONSOLE_URL:-}`). When set, the value is interpolated at server startup by `resolveExternalUrl` in `packages/data-schemas/src/app/interface.ts` and delivered to the client via `startupConfig.interface.customConsole.externalUrl`. The user must be authenticated and the account dropdown must be open.
- **UI elements:**
  - Menu item labeled `"Console"` (literal string, not localized) with a `LayoutDashboard` icon (Lucide).
  - The item appears in the account dropdown between "Help & FAQ" (when present) and "Settings".
- **Functional behavior:**
  1. FR-1: When `startupConfig.interface.customConsole.externalUrl` is a non-empty string, the Console menu item is rendered.
  2. FR-2: Clicking the item calls `window.open(externalUrl, '_blank')` because `openNewTab` is `true` in `librechat.yaml`. The current NuFi Chat tab remains open.
  3. FR-3: If `openNewTab` were set to `false` in `librechat.yaml`, the URL would open in the same tab (`'_self'`). NuFi sets `openNewTab: true`, so this branch is not active.
  4. FR-4: `CONSOLE_URL` is passed through Docker Compose from the host environment. If the variable is absent from the host, `CONSOLE_URL` resolves to an empty string, `resolveExternalUrl` returns an object whose `externalUrl` is `""`, and the client-side conditional `startupConfig?.interface?.customConsole?.externalUrl` is falsy — the item is not rendered.
- **States & edge cases:**
  - When `CONSOLE_URL` is empty, the Console entry is not in the DOM at all (not merely hidden); no fallback or tooltip is shown.
  - The label is hardcoded as the string `"Console"` in `AccountSettings.tsx` (not a localization key); it will not change with the user's language setting.
  - There is no in-app back-link from the Console to NuFi Chat; users return to the chat tab via standard browser tab management.
- **Acceptance criteria:**
  1. AC-1: Given `CONSOLE_URL=https://console.nufi.me` is set, when the user opens the account dropdown, then a "Console" item with a dashboard icon is present in the menu.
  2. AC-2: Given the user clicks "Console", when the browser processes the click, then `https://console.nufi.me` opens in a new browser tab and the NuFi Chat tab remains active.
  3. AC-3: Given `CONSOLE_URL` is empty or unset, when the user opens the account dropdown, then no "Console" item exists anywhere in the dropdown's DOM.
  4. AC-4: Given the user's UI language is set to Vietnamese, when the account dropdown is opened, then the item still displays the English label "Console" (not translated).
