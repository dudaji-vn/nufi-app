## Prompts Library

The Prompts Library is a persistent, server-side store of reusable prompt templates. Each prompt belongs to a **prompt group** (the organisational unit), which may contain multiple **versions** of its text. One version per group is designated the **production** version — this is the text seen by end users in the chat command palette. Users with appropriate permissions may create, edit, version, categorise, share, and delete prompts. The library is accessible both as a dedicated `/prompts` route and as a slide-in panel during chat.

---

### Accessing the Prompts Library

- **Purpose:** Navigate to the full-page library view or open the in-chat prompts panel so a user can browse, manage, and apply saved prompts.
- **Preconditions / access:** The user must be authenticated and hold the `PROMPTS › USE` permission (controlled server-side). Users lacking this permission are redirected to `/c/new` after a 1-second delay and the prompts panel is not rendered.
- **UI elements:**
  - Sidebar navigation item or dedicated route `/prompts` — navigates to the library page.
  - In-chat prompts panel (slide-in sidebar) opened from the chat interface.
  - Search bar labelled **"Filter prompts by name"** (`com_ui_filter_prompts_name`).
  - Category/filter dropdown with icon (`ListFilter`) labelled **"Filter:"** / `com_ui_filter_prompts`.
  - Filter options: **All** (`com_ui_all_proper`), **My Prompts** (`com_ui_my_prompts`), **Shared Prompts** (`com_ui_shared_prompts`), followed by a divider and individual category entries.
  - Prompt cards (one per group) in a scrollable list; pagination controls **Prev** / **Next** at the bottom of the panel.
  - Empty-state panel: icon + heading **"No prompts title"** (`com_ui_no_prompts_title`) + sub-text **"Add first prompt"** (`com_ui_add_first_prompt`).
  - When no prompt is selected in the library view: centred message **"Select or create a prompt"** (`com_ui_select_or_create_prompt`).
- **Functional behavior:**
  1. FR-1 — On load, the system fetches all prompt groups the user is authorised to view (paginated) and displays them as cards sorted by the server's default order.
  2. FR-2 — Typing in the search bar filters the list server-side by prompt name; the debounced name value (500 ms) is passed as a query parameter to the API, which applies a case-insensitive regex filter in the database. Screen-reader live region announces the result count.
  3. FR-3 — Selecting a filter option from the category dropdown restricts the list to prompts matching that `SystemCategory` or custom category value; selecting **All** removes the restriction.
  4. FR-4 — When the **My Prompts** filter is active, the server returns only prompt groups authored by the current user (resolved via `ownedPromptGroupIds` on the server; the client sends `category = 'sys__my__prompts__sys'`).
  5. FR-5 — When the **Shared Prompts** filter is active, the server returns all ACL-accessible prompt groups the user does not own (including publicly shared ones), excluding any groups in `ownedPromptGroupIds`. The `authorName` field is used client-side only to display the "shared by author" badge on cards.
  6. FR-6 — Clicking **Prev** / **Next** fetches the adjacent page; controls are disabled when `hasPreviousPage` / `hasNextPage` is false.
  7. FR-7 — On mobile viewports, the prompts panel appears as a full-screen or drawer overlay.
- **States & edge cases:**
  - Empty library: the list area shows the file-icon empty state (`com_ui_no_prompts_title`); the `Create Prompt` button remains visible if the user has `PROMPTS › CREATE` permission.
  - Search returns zero results: same empty-state UI appears; live region announces "0 results".
  - Loading: skeleton cards (`h-[72px]`) appear in place of real cards while `groupsQuery.isLoading` is true.
- **Acceptance criteria:**
  1. AC-1 — Given the user holds `PROMPTS › USE`, when they navigate to `/prompts`, then the prompt list loads within one network round-trip with no error.
  2. AC-2 — Given a search term is entered, when 500 ms elapses, then only prompt groups whose names contain the term (case-insensitive) are shown.
  3. AC-3 — Given no prompts exist, when the library view renders, then the empty-state message is visible and no list items are present.
  4. AC-4 — Given the user lacks `PROMPTS › USE`, when they visit `/prompts/new`, then they are redirected to `/c/new` within 1 second.

---

### Creating a Prompt

- **Purpose:** Let authorised users define a new reusable prompt (group + first version) with a name, body text, optional category, optional one-liner description, and optional slash command.
- **Preconditions / access:** User must hold both `PROMPTS › USE` and `PROMPTS › CREATE` permissions. The create form is at route `/prompts/new` and is also reachable via the **"Create Prompt"** button (plus icon, `com_ui_create_prompt`) in the filter toolbar.
- **UI elements:**
  - **Prompt Name** field: floating-label text input (`id="prompt-name"`, `aria-label="Prompt name"`, placeholder `" "`). Label text: **"Prompt name"** (`com_ui_prompt_name`) with a required asterisk (`*`). Validation error appears below the field in `text-status-error`.
  - **Category** dropdown: `CategorySelector` button labelled `com_ui_prompt_category_selector_aria`, shows current category label or **"Category"** placeholder when none is selected. Persists last selection to `localStorage` key `LAST_PROMPT_CATEGORY`.
  - **Prompt Text** panel: header shows `FileText` icon and label **"Text"** (`com_ui_prompt_text`) with asterisk; body is a `TextareaAutosize` with `minRows=4`, `maxRows=16`, `font-mono`, placeholder `com_ui_prompt_input`.
  - **Special Variables** dropdown button (sparkles icon, label `com_ui_special_variables`) — top-right of prompt text panel. Inserts a special variable token at the end of the textarea.
  - **Variables** panel: appears below the text area automatically when `{{...}}` tokens are detected in the prompt text (see §Prompt Variables).
  - **Description** field: single-line input with floating label **"Description placeholder"** (`com_ui_description_placeholder`), `Info` icon, maximum 120 characters; character count displayed as `n/120`.
  - **Command** field: single-line input with floating label **"Command placeholder"** (`com_ui_command_placeholder`), `SquareSlash` icon; accepts lowercase alphanumeric and hyphens only, spaces converted to hyphens, maximum 56 characters (`Constants.COMMANDS_MAX_LENGTH`); character count displayed as `n/56`.
  - **Create Prompt** button (`com_ui_create_prompt`): disabled (opacity 50%) when the form is not dirty, is submitting, or fails validation.
- **Functional behavior:**
  1. FR-1 — Submitting the form calls `useCreatePrompt` which creates a new prompt group and its first prompt version in a single API call.
  2. FR-2 — The `name` field is required; submitting with an empty name shows the error `com_ui_prompt_name_required` below the field.
  3. FR-3 — The `prompt` (body text) field is required; submitting with empty text shows `com_ui_prompt_text_required`.
  4. FR-4 — `oneliner` is only included in the API payload when its length is greater than zero; similarly for `command`.
  5. FR-5 — The `command` value is forced to lowercase and stripped of any character that is not `[a-z0-9-]`; spaces are converted to hyphens.
  6. FR-6 — On successful creation, the user is navigated to `/prompts/{groupId}` (replace history entry) unless the form is used in an embedded context that provides an `onSuccess` callback.
  7. FR-7 — The selected category is stored in `localStorage` under `LAST_PROMPT_CATEGORY` and pre-populated on subsequent uses of the create form.
- **States & edge cases:**
  - Form dirty / pristine: the **Create Prompt** button is visually inactive (50% opacity) when `isDirty` is false.
  - Concurrent submission: the button is disabled while `isSubmitting` is true.
  - No category selected: category field is optional; group is created with an empty string for `category`.
  - User navigates away without submitting: no data is persisted (the form is not auto-saved).
- **Acceptance criteria:**
  1. AC-1 — Given both required fields are populated, when the user clicks **Create Prompt**, then a new prompt group is created and the browser navigates to `/prompts/{newGroupId}`.
  2. AC-2 — Given the name field is empty, when the user submits, then the inline error `com_ui_prompt_name_required` appears and no API call is made.
  3. AC-3 — Given a command containing uppercase letters or spaces, when the user types it, then the field automatically converts it to lowercase-hyphenated form.
  4. AC-4 — Given a description of 121+ characters is pasted, when the handler fires, then characters beyond 120 are rejected and the count stays at 120.

---

### Prompt Variables and Substitution

- **Purpose:** Allow prompt authors to embed placeholder tokens into prompt text; when the prompt is used in chat, end users are prompted to supply values before the message is sent.
- **Preconditions / access:** Variables are authored during prompt creation or editing; they are consumed during prompt use (no special permission beyond `USE`).
- **UI elements:**

  **Authoring panel — Variables preview (`PromptVariables` component):**
  - Appears automatically below the prompt text whenever `{{...}}` tokens are present.
  - Header: `Variable` icon + label **"Variables"** (`com_ui_variables`) + count badge.
  - Three sub-sections (each only shown when non-empty):
    - **Special variables** (`com_ui_special_variables`): displayed as `SpecialVariableChip` — icon, display label, and description.
    - **Dropdown variables** (`com_ui_dropdown_variables`): displayed as `DropdownVariableCard` — shows variable name, option count badge, and individual option chips.
    - **Text variables** (`com_ui_text_variables`): displayed as `SimpleVariableChip` — `Variable` icon + truncated name.

  **Special Variables dropdown (editor toolbar):**
  - Button labelled `com_ui_add_special_variables` (sparkles icon + `com_ui_special_variables` text on ≥`sm` breakpoint).
  - Four built-in special variables (from `specialVariables` in `librechat-data-provider`):
    - `current_date` — icon `Calendar`, label `com_ui_special_var_current_date`
    - `current_datetime` — icon `Clock`, label `com_ui_special_var_current_datetime`
    - `current_user` — icon `User`, label `com_ui_special_var_current_user`
    - `iso_datetime` — icon `Globe`, label `com_ui_special_var_iso_datetime`
  - Already-used variables are shown with a checkmark and are disabled.
  - Clicking an item appends `{label}: {{key}}` to the prompt text (preceded by `\n\n` if text is non-empty).

  **Variable Fill-in Dialog (`VariableForm`):**
  - Title: the prompt group's name.
  - Prompt preview pane: rendered markdown with user-entered values bold-highlighted in real time.
  - Per-variable input: `TextareaAutosize` for simple variables; `InputCombobox` with pre-defined options (plus free-text entry) for dropdown variables.
  - Floating labels identify each variable by its name.
  - **Submit** button (`com_ui_submit`) sends the filled text to chat.

- **Functional behavior:**
  1. FR-1 — Variable syntax: simple text variables use `{{variable_name}}`; dropdown variables use `{{variable_name:option1|option2|option3}}`. The colon-pipe syntax is parsed by `parseFieldConfig`; at least one pipe character in the options string triggers a `select` (combobox) input.
  2. FR-2 — Special variable tokens (`{{current_date}}`, `{{current_datetime}}`, `{{current_user}}`, `{{iso_datetime}}`) are resolved server/client-side via `replaceSpecialVars` before the variable fill-in dialog is shown. They do **not** appear as editable fields in `VariableForm`.
  3. FR-3 — `extractUniqueVariables` deduplicates variables so each name appears as one input field regardless of how many times it appears in the prompt text.
  4. FR-4 — On submission, `VariableForm` performs a global regex replacement of each `{{variable}}` occurrence with the entered value; empty-valued fields leave the placeholder token unchanged in the sent text.
  5. FR-5 — The live preview replaces filled-in values with `**bold**` markdown in real time as the user types.
  6. FR-6 — Dropdown variable comboboxes allow custom free-text input in addition to the predefined options.
  7. FR-7 — After submission, `recordUsage` is called with the group ID to track prompt usage analytics.
- **States & edge cases:**
  - No variables in prompt: `VariableDialog` returns `null` and is never shown; the prompt text is submitted directly.
  - Variable left blank on submit: the `{{variable}}` placeholder token is preserved in the sent message.
  - Special variable in prompt: it is resolved to its runtime value (e.g., today's date) before the dialog opens.
  - Dialog cancelled: focus returns to the textarea (via `requestAnimationFrame`).
- **Acceptance criteria:**
  1. AC-1 — Given a prompt contains `{{name}}`, when it is selected for use, then the Variable Fill-in Dialog opens with a text input labelled "name".
  2. AC-2 — Given a prompt contains `{{tone:formal|casual}}`, when the dialog opens, then a combobox with options "formal" and "casual" is shown alongside a free-text entry.
  3. AC-3 — Given the user fills in a value, when the preview pane is visible, then the variable placeholder is replaced by the value rendered in bold.
  4. AC-4 — Given a prompt contains `{{current_date}}`, when the dialog would open, then no input field for `current_date` is shown; the value is already resolved.
  5. AC-5 — Given all fields are filled and the user clicks **Submit**, then the assembled text (with substitutions) is sent to the chat input and usage is recorded.

---

### Editing a Prompt and Versioning

- **Purpose:** Allow authorised users to revise a prompt's text, name, description, command, and category. Each saved text change creates a new **version**; one version per group is the **production** version used in chat.
- **Preconditions / access:**
  - User must have `EDIT` permission (`PermissionBits.EDIT`) on the specific prompt group (checked via `useResourcePermissions`).
  - Read-only users who hold `VIEW` see `PromptDetails` with no edit controls (`showActions=false`).
  - Users without `VIEW` or `EDIT` see the `NoPromptGroup` state.
- **UI elements:**

  **Prompt editor page (`/prompts/{groupId}`):**
  - **Prompt Name** (`PromptName` component): inline editable heading. Click to enter edit mode (text input with border); press `Enter` or blur to save; press `Escape` to cancel. Shows `Loader2` spinner while saving, `Check` on success, `X` on error (each for ~2 seconds).
  - **Prompt Text editor** (`PromptEditor`): rounded border panel. In **view mode**: rendered markdown with `{{variable}}` tokens highlighted; hover reveals a centred chip **"Click to edit"** (`com_ui_click_to_edit`) and an `EditIcon` button (`com_ui_edit`). In **edit mode**: `TextareaAutosize` (`minRows=4`, `maxRows=16`, `font-mono`) with autofocus; toolbar retains the **Special Variables** dropdown. Press `Escape` or blur to exit edit mode and trigger save.
  - **Category** dropdown: same `CategorySelector` as creation; category changes are saved immediately on selection.
  - **Description** field: pre-populated from `group.oneliner`; updates are debounced 950 ms before calling the API (`updateGroupMutation`).
  - **Command** field: pre-populated from `group.command`; updates are debounced 950 ms.
  - **Versions panel** (Advanced mode only, `PromptsEditorMode.ADVANCED`): visible at `lg` breakpoints as a right sidebar (width 288–320 px); on smaller screens accessed via a **"Versions"** (`com_ui_versions`) button that opens a modal drawer.
    - Header count badge shows total number of versions.
    - Each version shown as a `VersionCard` in a timeline list: version number, creation timestamp (relative, e.g., "3 days ago"), and badges.
    - Version badges: **Live** (`com_ui_live`, green pill with slow-pulse dot) for the production version; **Latest** (`com_ui_latest`, blue pill with lightning icon) for the newest non-production version.
    - **Make Production / Deploy** button (`com_ui_make_production` / `com_ui_deploy`, `Rocket` icon): disabled if the selected version is already production; on click calls `useMakePromptProduction`.
  - **Editor mode toggle** (Simple vs Advanced): the versions sidebar is only rendered when `editorMode === PromptsEditorMode.ADVANCED` (stored in Recoil state `store.promptsEditorMode`).
  - **Always Make Production** setting (`store.alwaysMakeProd`): when enabled, every new version is automatically promoted to production immediately after save.

- **Functional behavior:**
  1. FR-1 — Exiting edit mode on the prompt text (blur or `Escape`) triggers `addPromptToGroupMutation`, which creates a **new version** in the database. The current prompt text is compared against `selectedPrompt.prompt`; if unchanged, no API call is made.
  2. FR-2 — Renaming the group calls `updatePromptGroup` with `{ name: newValue }`. The save status cycles through `saving → saved → idle` (or `error`) with a 2-second display timer.
  3. FR-3 — Changing the category calls `updateGroupMutation` with `{ name, category }` immediately on dropdown selection, independent of the form's dirty state (the category field sets `shouldDirty: false` so a category-only change does not mark the form dirty).
  4. FR-4 — Description and command changes are debounced 950 ms; rapid consecutive edits result in a single API call with the final value.
  5. FR-5 — Selecting a version card in the versions panel loads that version's text into the editor form field. The selected card is visually highlighted (green background, `CheckCircle2` marker).
  6. FR-6 — Clicking **Deploy** on a non-production version calls `useMakePromptProduction`; on success the version badge changes to **Live** and the button label changes to the production state label (`com_ui_production`).
  7. FR-7 — When `alwaysMakeProd` is true, every call to `addPromptToGroupMutation` is followed immediately by `useMakePromptProduction` on the newly created version.
  8. FR-8 — Navigating to a different prompt group resets `selectionIndex` to 0 and `isEditing` to false.
  9. FR-9 — Read-only users (no `EDIT` permission) see `PromptDetails` in static view; the prompt text, description, and command are displayed but not editable.

- **States & edge cases:**
  - Unsaved changes: changes are committed on blur; there is no explicit "Save" button for prompt text — navigating away immediately after editing without blurring may discard the in-progress edit (requires manual verification on the running product: whether `onBlur` fires reliably on route change across all browsers).
  - Empty prompt text: if the user clears all text and blurs, the save is skipped (guarded by `if (!value) return`). No toast is shown — a `// TODO: show toast, cannot be empty` comment is present in the code but unimplemented in the current build.
  - Save error on name update: the `showToast` with `status: 'error'` and message `com_ui_prompt_update_error` is displayed.
  - Mobile versions panel: the panel slides in from the right as a modal drawer with `role="dialog"`, `aria-modal="true"`. Focus is trapped within; `Escape` closes it and returns focus to the trigger button.
  - Loading state: a `Skeleton` component fills the editor area while `isLoadingPrompts` is true.

- **Acceptance criteria:**
  1. AC-1 — Given the user edits the prompt text and tabs away, then a new version appears in the versions panel with a **Latest** badge.
  2. AC-2 — Given a new version exists and is not production, when the user clicks **Deploy**, then that version receives the **Live** badge and the previous **Live** badge is removed.
  3. AC-3 — Given the user renames the prompt and presses `Enter`, when the API succeeds, then the name heading shows the updated value and a `Check` icon appears for ~2 seconds.
  4. AC-4 — Given `Always Make Production` is enabled, when the user saves an edit, then the new version is immediately promoted to production without manual deploy.
  5. AC-5 — Given a user with only `VIEW` permission opens a prompt, then the editor toolbar, edit button, and versions panel deploy button are absent.

---

### Using a Prompt in a Conversation

- **Purpose:** Insert a saved prompt's production text (with variable substitution if needed) into the active chat input and optionally auto-submit it.
- **Preconditions / access:** User must hold `PROMPTS › USE`. The prompt group must have a production prompt set (`productionPrompt.prompt` non-empty).
- **UI elements:**

  **Command palette (in-chat `PromptsCommand`):**
  - Triggered by typing `/` in the chat textarea. A popover appears above the input (`absolute bottom-28 z-10`).
  - Search input: `placeholder` = `com_ui_command_usage_placeholder`, inside a rounded panel (`rounded-2xl`, `bg-surface-tertiary-alt`).
  - Virtualised list of matching prompt groups (`react-virtualized`); row height 44 px; max visible height 160 px.
  - Each row rendered as `MentionItem` with `type="prompt"`, showing the group icon, name, and `oneliner`/description.
  - Keyboard navigation: `ArrowUp` / `ArrowDown` moves selection; `Enter` or `Tab` selects the active item; `Escape` or `Backspace` (when search is empty) closes the popover.
  - Spinner shown while `isLoading && matches.length === 0`.

  **In-library prompt cards (chat context):**
  - Clicking a card in the library panel (when `isChatRoute=true`) inserts the production prompt text directly into the chat.
  - Three-dot menu (`Ellipsis`) on each card: **Preview** (eye icon), **Edit** (pen icon, if user has `EDIT`), **Delete** (trash icon, if user has `DELETE`).

  **Preview dialog (`PreviewPrompt`):**
  - Modal showing `PromptDetails` with header, production text (markdown), variables panel, command chip, and **Use Prompt** button (`com_ui_use_prompt`, `Send` icon).
  - **Share** button also visible if the user has share access.

  **Auto-Send toggle:**
  - Toggle button labelled `com_nav_auto_send_prompts` (with checkbox) in the prompts sidebar. When active, selecting a prompt calls `submitPrompt()` which invokes `submitMessage({ text: parsedText })` in `useSubmitMessage.ts`, sending the message immediately. When inactive, `submitPrompt()` calls `setActivePrompt(newText)` to place the text in the textarea without sending.

- **Functional behavior:**
  1. FR-1 — Typing `/` in the chat textarea triggers the prompts popover; the search field receives focus and is pre-populated with any text typed after `/`.
  2. FR-2 — The combobox matches against all prompt groups (the `value` field is `group.command ?? group.name`; the `label` includes the command prefix, name, and one-liner).
  3. FR-3 — Selecting a prompt (Enter/Tab/click) removes the `/` character from the textarea via `removeCharIfLast`, then:
     - If `detectVariables(group.productionPrompt.prompt)` is true → opens `VariableDialog`.
     - Otherwise → calls `submitPrompt(group.productionPrompt.prompt)` and records usage.
  4. FR-4 — Clicking a prompt card in the library panel (chat route) follows the same variable-detection logic (FR-3).
  5. FR-5 — Clicking **Use Prompt** in the preview dialog also follows variable-detection logic.
  6. FR-6 — `useRecordPromptUsage` is called with `group._id` on every successful (non-variable) use, and at the end of variable form submission.
  7. FR-7 — The `Auto-Send Prompts` toggle state is stored in Recoil (`store.autoSendPrompts`). When `autoSendPrompts` is true, `submitPrompt()` calls `submitMessage({ text: parsedText })` directly (firing the `ask()` API call); when false, it calls `setActivePrompt(newText)` which places the text into the textarea without sending. The downstream consumption is in `useSubmitMessage.ts`, not in `ChatForm`.
  8. FR-8 — The popover closes on `Escape`, on `Backspace` with empty search, and on blur (after a 150 ms delay to allow click events to register).

- **States & edge cases:**
  - No production prompt set: `text?.trim()` is falsy; clicking the card is a no-op.
  - Prompt group has no command: the `value` field in the combobox falls back to `group.name`; the `/` search still matches by name.
  - Variable dialog cancelled: the textarea retains its previous content; no usage is recorded.
  - Popover loading: if the groups query is still fetching, a spinner is shown in the popover body.
- **Acceptance criteria:**
  1. AC-1 — Given the user types `/` in the chat input, then the prompts command popover appears with a search field.
  2. AC-2 — Given the user types `/report`, then only prompt groups whose command or name contains "report" are listed.
  3. AC-3 — Given a prompt without variables is selected, then the production prompt text is placed in the chat input and the popover closes.
  4. AC-4 — Given a prompt with variables is selected, then the Variable Fill-in Dialog opens before any text is sent.
  5. AC-5 — Given the user selects a prompt from the library panel on a chat route, then the production prompt is inserted (or the variable dialog is shown) using the same logic as the command palette.

---

### Sharing a Prompt

- **Purpose:** Allow authorised owners of a prompt group to grant other users or groups access to view or edit the prompt, and optionally make it public (visible to all users).
- **Preconditions / access:**
  - The **Share** button is rendered only when all of the following are true:
    1. The current user is the prompt group's `author`, or has `SystemRoles.ADMIN`, or holds `PermissionBits.SHARE` on the resource.
    2. The user holds the global `PROMPTS › SHARE` permission.
    3. The prompt group is fully loaded (`!isLoadingGroup`).
  - At least one of `hasPeoplePickerAccess` (user/group search) or `canSharePublic` must be true for the share dialog to be functional.
- **UI elements:**
  - **Share** button: icon-only (`Share2Icon`), `size="icon"`, `variant="outline"`, `size=9`, tooltip `com_ui_share`. Located in the `HeaderActions` bar (prompt editor) and in `PromptActions` (preview dialog).
  - **Share dialog** (`GenericGrantAccessDialog`): modal with title `com_ui_share_var` (e.g., "Share {prompt name}"), `Users` icon.
  - **People search section** (`UnifiedPeopleSearch`): search field labelled `com_ui_search_people_placeholder`; visible only when `hasPeoplePickerAccess` is true.
  - **Selected principals list** (`SelectedPrincipalsList`): shows each grantee with avatar, name, role picker (`AccessRolesPicker`), and remove button.
  - **Public Access section** (`PublicSharingToggle`): visible only when `canSharePublic` is true.
    - Toggle labelled **"Share everyone"** (`com_ui_share_everyone`) with `Globe` icon and an info hover card.
    - When toggled on: **Everyone Permission Level** (`com_ui_everyone_permission_level`) role picker appears with animated transition.
  - Warning banner: shown when `hasChanges && !hasAtLeastOneOwner` — `com_ui_at_least_one_owner_required`.
  - **Cancel** button (`com_ui_cancel`) and **Save Changes** button (`com_ui_save_changes`, disabled until changes are made or while saving).
  - Empty state (no shares yet): dashed-border card with `Users` icon, `com_ui_no_individual_access`, `com_ui_search_above_to_add_people`.
- **Functional behavior:**
  1. FR-1 — Opening the dialog loads the current permissions for the prompt group (`useResourcePermissionState`); existing principals are shown with `isExisting: true`.
  2. FR-2 — Searching for and selecting a user or group adds them to the local `allShares` list with `isExisting: false` and the default viewer role.
  3. FR-3 — Changing a principal's role updates the local state; no API call is made until **Save Changes** is clicked.
  4. FR-4 — Clicking the remove button filters the principal from `allShares` locally.
  5. FR-5 — Enabling the **Share everyone** toggle marks `isPublic = true`; the permission level picker becomes visible with the default viewer role.
  6. FR-6 — Clicking **Save Changes** calls `updatePermissionsMutation` with `{ updated, removed, public, publicAccessRoleId }` derived by diffing `allShares` against `currentShares`. On success: toast `com_ui_permissions_updated_success`; on error: toast `com_ui_permissions_failed_update`.
  7. FR-7 — The **Save Changes** button is disabled when no changes have been made, when the mutation is in-flight, or when changes exist but no principal holds the owner role.
  8. FR-8 — Clicking **Cancel** resets local state to the last fetched permissions and closes the dialog.
  9. FR-9 — Prompt groups shared with all users (`isPublic: true`) display a `EarthIcon` badge on their list card with tooltip `com_ui_sr_global_prompt`. Prompts shared by another user display a `User` icon badge with tooltip `com_ui_by_author`.
- **States & edge cases:**
  - Dialog opened while permissions are loading: skeleton placeholders shown for the principals list.
  - Permissions load error: inline error `com_ui_permissions_failed_load` shown instead of the dialog body.
  - All owners removed: warning banner appears and **Save Changes** is disabled.
  - User lacks people-picker access but can share publicly: only the Public Access section is shown.
- **Acceptance criteria:**
  1. AC-1 — Given the author opens the share dialog, then the dialog renders with any existing principals and their roles.
  2. AC-2 — Given the author searches for a user and selects them, when **Save Changes** is clicked, then the user is granted access and a success toast is shown.
  3. AC-3 — Given the **Share everyone** toggle is enabled and saved, then the prompt card in other users' libraries shows the `EarthIcon` badge.
  4. AC-4 — Given all owners are removed from the list, then **Save Changes** is disabled and the owner-required warning is visible.
  5. AC-5 — Given a non-author without `SHARE` permission views the prompt, then no Share button is rendered.

---

### Deleting a Prompt

- **Purpose:** Permanently remove a prompt group (and all its versions) from the library.
- **Preconditions / access:** The user must hold `PermissionBits.DELETE` on the specific prompt group (checked via `useResourcePermissions`). Two separate delete flows exist:
  1. **From the prompt editor page** (`DeletePrompt` component in `HeaderActions`): deletes the currently selected version (a single prompt version, not the whole group).
  2. **From the library list card** (`ChatGroupItem` component): deletes the entire prompt **group**.
- **UI elements:**
  - **Delete** button (editor header): `Trash2` icon, `variant="destructive"`, `size="icon"`, `size=9`, tooltip `com_ui_delete`. Hidden when `canDelete` is false.
  - **Delete** menu item (list card three-dot menu): `Trash` icon + label `com_ui_delete`.
  - **Confirmation dialog** (editor flow — `OGDialogTemplate`):
    - Title: `com_ui_delete_prompt`
    - Body: `com_ui_delete_confirm_prompt_version_var` with `{0: promptName}`.
    - **Delete** button: `bg-surface-destructive hover:bg-surface-destructive-hover text-white`.
    - A **Cancel** button (`com_ui_cancel`) is rendered by default (`OGDialogTemplate` defaults `showCancelButton=true`). `showCloseButton={false}` removes the X icon in the header, but the Cancel button and outside-click dismiss (Radix Dialog default) both remain.
  - **Confirmation dialog** (list card flow — `OGDialogTemplate`):
    - Title: `com_ui_delete_prompt`
    - Body: label using `com_ui_prompt_delete_confirm` with `{0: group.name}`.
    - **Delete** button with `variant="destructive"`; shows `Spinner` while `deleteGroup.isLoading`.
- **Functional behavior:**
  1. FR-1 — In the editor, clicking the **Delete** button opens the confirmation dialog; confirming calls `useDeletePrompt` with `{ _id: promptId, groupId }`.
  2. FR-2 — In the list card, selecting **Delete** from the overflow menu sets `deleteOpen: true`; confirming calls `useDeletePromptGroup` with `{ id: group._id }`.
  3. FR-3 — On successful group deletion from the list:
     - A polite live announcement is made: `com_ui_prompt_deleted_group` with `{0: group.name}`.
     - If the deleted group is the currently open prompt in the `/prompts/{id}` route, the router navigates to `/prompts/new`.
  4. FR-4 — On group deletion error: toast with `status: 'error'` and message `com_ui_prompt_delete_error`.
  5. FR-5 — The **Delete** button in the editor is disabled (`disabled={isLoadingGroup || !promptId}`) while the group is loading or no version ID is resolved.
  6. FR-6 — Deleting a single version (editor flow) removes that version from the versions list but preserves the group; if the deleted version was the production version, the production pointer is updated server-side (requires manual verification on the running product: exact API behaviour — whether `productionId` is cleared or reassigned — when the production version is deleted).
- **States & edge cases:**
  - Delete in progress: the **Delete** button in the list card shows a `Spinner` and is implicitly blocked until the mutation resolves.
  - Prompt group not found after deletion: the router replaces the current history entry with `/prompts/new`.
  - User lacks `DELETE` permission: the **Delete** button in the editor header is not rendered; the **Delete** item is absent from the list card dropdown.
- **Acceptance criteria:**
  1. AC-1 — Given the user has `DELETE` permission and clicks **Delete** on a prompt group card, when the confirmation dialog appears and the user confirms, then the group is removed from the list and a live announcement is made.
  2. AC-2 — Given the deleted group was open in the editor, when deletion succeeds, then the browser navigates to `/prompts/new`.
  3. AC-3 — Given a user without `DELETE` permission views a prompt card, then no **Delete** option appears in the card's overflow menu.
  4. AC-4 — Given an error occurs during deletion, then a toast with `status: 'error'` is shown and the group remains in the list.
