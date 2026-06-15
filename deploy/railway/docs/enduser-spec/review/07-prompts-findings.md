# Verification findings — 07 Prompts

## Summary

- Claims checked: 68 | CONFIRMED: 54 | WRONG: 8 | NEEDS-FIX: 4 | RUNTIME-ONLY: 2

---

## Findings

---

### [WRONG] Accessing — FR-2: name search is described as "client-side"

- **Spec says:** "Typing in the search bar filters the visible list **client-side** by prompt name; the filter applies after a 500 ms debounce."
- **Reality:** The 500 ms debounce is correct, but the filter is **server-side**. The debounced `name` value is stored in Recoil (`store.promptsName`) and passed as a query parameter to `usePromptGroupsInfiniteQuery`. The server's `buildPromptGroupFilter` converts it to a case-insensitive regex (`new RegExp(escapeRegExp(name), 'i')`) applied in the database query.
- **Evidence:** `client/src/hooks/Prompts/usePromptGroupsNav.ts:17-26` — `name` is passed in the query object; `packages/api/src/prompts/format.ts:94-96` — server converts it to `filter.name = new RegExp(...)`.
- **Suggested correction:** Replace "client-side" with "server-side". Search sends a new paginated API request with the debounced name as a filter parameter.

---

### [WRONG] Accessing — FR-4: "My Prompts" filter description is misleading

- **Spec says:** "When the **My Prompts** filter is active, only groups whose `author` equals the current user's ID are displayed."
- **Reality:** The actual implementation filters via `ownedPromptGroupIds` (the set of prompt groups the user *authored*, fetched from the DB with `getOwnedPromptGroupIds`), not by comparing an `author` field client-side. The client only sends `category = 'sys__my__prompts__sys'`; the server then excludes all IDs not in `ownedPromptGroupIds`. The end result is the same, but the mechanism is entirely server-side.
- **Evidence:** `api/server/routes/prompts.js:162-170`, `packages/api/src/prompts/format.ts:99-101`, `packages/api/src/prompts/format.ts:134-141`.
- **Suggested correction:** Reframe as: "the server returns only prompt groups authored by the current user."

---

### [WRONG] Accessing — FR-5: "Shared Prompts" filter description is inaccurate

- **Spec says:** "When the **Shared Prompts** filter is active, only groups shared with the current user (author is another user and `authorName` is set) are displayed."
- **Reality:** The filter logic is: return all prompt groups the user can access (via ACL) **plus** publicly accessible ones, **minus** those owned by the user (`ownedPromptGroupIds`). The `authorName` field is irrelevant to server filtering; it is only used client-side as a display hint for the "shared by author" badge on card items.
- **Evidence:** `packages/api/src/prompts/format.ts:144-158`, `client/src/components/Prompts/lists/ChatGroupItem.tsx:44` (client-side display only: `isSharedPrompt = group.author !== user?.id && Boolean(group.authorName)`).
- **Suggested correction:** Reframe as: "the server returns all ACL-accessible prompt groups the user does not own, including publicly shared ones."

---

### [WRONG] Accessing — UI elements: search bar label text

- **Spec says:** Search bar labelled **"Filter prompts name"** (`com_ui_filter_prompts_name`).
- **Reality:** The English value of `com_ui_filter_prompts_name` is **"Filter prompts by name"** (not "Filter prompts name").
- **Evidence:** `client/src/locales/en/translation.json:~"com_ui_filter_prompts_name": "Filter prompts by name"`.
- **Suggested correction:** Change the quoted label to **"Filter prompts by name"**.

---

### [WRONG] Accessing — UI elements: pagination button labels

- **Spec says:** Pagination controls **Previous** / **Next** at the bottom of the panel.
- **Reality:** The English locale strings are **"Prev"** / **"Next"** (key `com_ui_prev` = "Prev", `com_ui_next` = "Next"). The component renders `{localize('com_ui_prev')}` and `{localize('com_ui_next')}`.
- **Evidence:** `client/src/components/Prompts/sidebar/PanelNavigation.tsx:34,43`; `client/src/locales/en/translation.json`.
- **Suggested correction:** Replace "Previous" with "Prev" in the spec.

---

### [WRONG] Creating — UI elements: Prompt Text panel header label

- **Spec says:** Header shows `FileText` icon and label **"Prompt text"** (`com_ui_prompt_text`).
- **Reality:** The English value of `com_ui_prompt_text` is **"Text"** (not "Prompt text"). The key and icon are correct but the quoted English label is wrong.
- **Evidence:** `client/src/locales/en/translation.json:~"com_ui_prompt_text": "Text"`.
- **Suggested correction:** Change the quoted label to **"Text"** or note that the i18n key is `com_ui_prompt_text`.

---

### [WRONG] Deleting — UI elements: editor delete dialog cancel path

- **Spec says:** "No explicit cancel button; the dialog close (`showCloseButton=false`) is the only cancel path."
- **Reality:** `OGDialogTemplate` defaults `showCancelButton = true`. The editor's delete dialog (`DeleteConfirmDialog`) passes `showCloseButton={false}` but does **not** pass `showCancelButton={false}`, so the template renders a **Cancel** button via `OGDialogClose`. Clicking outside the dialog also closes it (Radix Dialog default). There is both a Cancel button and an outside-click dismiss path.
- **Evidence:** `client/src/components/Prompts/dialogs/DeletePrompt.tsx:47` (`showCloseButton={false}` only); `packages/client/src/components/OGDialogTemplate.tsx:80,131` (`showCancelButton = true` default, Cancel button always rendered unless overridden).
- **Suggested correction:** Remove the "No explicit cancel button" claim. State: "A **Cancel** button (`com_ui_cancel`) is rendered by default. `showCloseButton={false}` removes the X icon in the header but the Cancel button and outside-click dismiss remain."

---

### [NEEDS-FIX] Creating — Form dirty check includes `!isValid`

- **Spec says:** "**Create Prompt** button: disabled (opacity 50%) when the form is not dirty, is submitting, or fails validation."
- **Reality:** The code condition is `(!isDirty || isSubmitting || !isValid)`. The spec correctly lists all three conditions, but the phrasing "fails validation" could be clearer: the button is also visually inactive on initial render before any field is touched because `isDirty` is false. The disable logic is accurate.
- **Evidence:** `client/src/components/Prompts/forms/CreatePromptForm.tsx:215,219,221`.
- **Note:** The spec is functionally correct but misleadingly implies all three are independent gates; in practice the form can be `isDirty` but `!isValid` (e.g., name cleared after typing) and still be blocked. No change strictly needed; flagged for clarity.

---

### [NEEDS-FIX] Variables — FR-1: dropdown trigger description slightly off

- **Spec says:** "two or more pipe-separated options trigger a `select` (combobox) input."
- **Reality:** `VariableForm.parseFieldConfig` triggers `select` type when `options.includes('|')` — meaning **at least one pipe character** is present, regardless of how many non-empty options result. For the *display* panel (`PromptVariables`), the condition is `options.length > 1` (more than one post-split element). These are practically equivalent (one pipe yields two elements), but technically a trailing pipe `{{x:a|}}` would trigger the select with one real option in `VariableForm` while PromptVariables would mark it a dropdown too (two elements including the empty string).
- **Evidence:** `client/src/components/Prompts/forms/VariableForm.tsx:54`; `client/src/components/Prompts/display/PromptVariables.tsx:27`.
- **Suggested correction:** "At least one pipe character in the options list triggers a `select` (combobox) input." (In normal usage the spec statement is correct; this is a minor edge-case note.)

---

### [NEEDS-FIX] Editing — UI elements: PromptEditor hover chip and edit icon

- **Spec says:** In view mode, hover reveals a centred chip **"Click to edit"** and a **pencil icon** button (`com_ui_edit`).
- **Reality:** The toolbar button uses `EditIcon` (the lucide-react `Edit` icon — a pen-and-square), not `Pencil`. The inline overlay chip also uses `EditIcon`. There is no `Pencil` icon in this component.
- **Evidence:** `client/src/components/Prompts/editor/PromptEditor.tsx:8,29,130` — `import { EditIcon, Check } from 'lucide-react'`; no `Pencil` import.
- **Suggested correction:** Replace "pencil icon button" with "`EditIcon` button" (or "edit/pen-square icon button").

---

### [NEEDS-FIX] Editing — FR-3: category change payload

- **Spec says:** "Changing the category calls `updatePromptGroup` with `{ name, category }` immediately on dropdown selection."
- **Reality:** In the edit form, the category change calls `updateGroupMutation.mutate({ id: group._id, payload: { name: group.name, category: value } })` — the payload uses `{ name, category }` under a `payload` key, not directly. More importantly, in the `CategorySelector` component when inside a form context, `setValue('category', value, { shouldDirty: false })` is called with `shouldDirty: false`, which means if category is the **only** change, the form will not be marked dirty. The actual API call goes through `handleCategoryChange` → `updateGroupMutation.mutate`. This is correct — the spec's claim is accurate in effect, but the `shouldDirty: false` nuance is worth noting.
- **Evidence:** `client/src/components/Prompts/forms/PromptForm.tsx:415-425`; `client/src/components/Prompts/fields/CategorySelector.tsx:65`.
- **Suggested correction:** Minor — clarify that the category change is saved immediately via `updateGroupMutation` independent of the form's dirty state.

---

### [VERIFY-RESOLVED] Editing — "unsaved changes / onBlur fires on route change"

- **Spec marker:** "(verify: whether `onBlur` fires reliably on route change)."
- **Resolution (RUNTIME-ONLY):** The `PromptEditor` sets editing to false on `onBlur`, which triggers `handleSubmit` → `onSave`. Browser behavior varies: on React Router navigation `onBlur` typically fires for the focused element before unmount, but this is not guaranteed across all browsers/React versions. The code has no explicit "save before navigate" guard.
- **Evidence:** `client/src/components/Prompts/forms/PromptForm.tsx:325-329` — save triggers when `isEditing` transitions false; `client/src/components/Prompts/editor/PromptEditor.tsx:92` — `onBlur={() => setIsEditing(false)}`.
- **Verdict:** RUNTIME-ONLY — cannot be confirmed without browser testing. The concern is real and the spec's note is valid.

---

### [VERIFY-RESOLVED] Editing — "empty prompt text: no toast in current build"

- **Spec marker:** "(verify: confirm no toast appears in current build)."
- **Resolution (CONFIRMED):** The code at `client/src/components/Prompts/forms/PromptForm.tsx:281-284` has an explicit `// TODO: show toast, cannot be empty.` comment with no toast implementation. The guard `if (!value) return` silently skips saving. No toast is shown.
- **Evidence:** `client/src/components/Prompts/forms/PromptForm.tsx:281-284`.
- **Verdict:** CONFIRMED — no toast is shown when the prompt text is cleared and blurred. The TODO comment is present but unimplemented.

---

### [VERIFY-RESOLVED] Using — FR-7: Auto-Send downstream consumption

- **Spec marker:** "(verify: exact submission path — `submitPrompt` vs separate send trigger)" and "(verify: `AutoSendPrompt` sets `store.autoSendPrompts` but the downstream consumption point should be confirmed in `ChatForm` or equivalent)."
- **Resolution (CONFIRMED):** The `store.autoSendPrompts` Recoil atom (set by `AutoSendPrompt` component) is consumed directly inside `useSubmitMessage.ts`. When `autoSendPrompts` is true, `submitPrompt()` calls `submitMessage({ text: parsedText })` (fires the `ask()` API call immediately). When false, it calls `setActivePrompt(newText)` which places the text into the textarea.
- **Evidence:** `client/src/hooks/Messages/useSubmitMessage.ts:16,48-56`.
- **Verdict:** CONFIRMED — the consumption is in `useSubmitMessage`, not `ChatForm`. The mechanism is `submitPrompt → ask()` (auto-send on) or `submitPrompt → setActivePrompt` (textarea insert, no auto-send).

---

### [VERIFY-RESOLVED] Deleting — FR-6: production version deletion API behaviour

- **Spec marker:** "(verify: confirm API behaviour when the production version is deleted)."
- **Resolution (RUNTIME-ONLY):** The client calls `useDeletePrompt` with `{ _id: promptId, groupId }` (a single version). The server-side behaviour when deleting the production version (whether it clears `productionId` or picks a new one) is not visible in the client code and requires API/model inspection.
- **Evidence:** `client/src/components/Prompts/dialogs/DeletePrompt.tsx:85-88`.
- **Verdict:** RUNTIME-ONLY / server-side — needs API endpoint and Mongoose model inspection to fully confirm.

---

## Confirmed-correct claims (selected highlights)

The following spec claims were verified as accurate:

- `PROMPTS › USE` permission gating in `CreatePromptForm.tsx` with 1-second redirect to `/c/new` (`CreatePromptForm.tsx:52-62`).
- 500 ms debounce on search (`FilterPrompts.tsx:25`, `useDebounce`).
- `localStorage` key `LAST_PROMPT_CATEGORY` for category persistence (`CategorySelector.tsx:67`, `LocalStorageKeys.LAST_PROMPT_CATEGORY`).
- Command field: lowercase, `[a-z0-9-]` only, spaces → hyphens, max 56 chars (`Command.tsx:32-39`, `Constants.COMMANDS_MAX_LENGTH = 56`).
- Description field: max 120 chars enforced in handler (`Description.tsx:33`).
- `oneliner` and `command` only included in payload when length > 0 (`CreatePromptForm.tsx:97-101`).
- Navigate to `/prompts/{groupId}` with `replace: true` on success (`CreatePromptForm.tsx:84`).
- Variable syntax: `{{name}}` for text, `{{name:opt1|opt2}}` for dropdown (`VariableForm.tsx:50-63`).
- Special variables resolved via `replaceSpecialVars` before dialog opens (`VariableForm.tsx:77`); `detectVariables` excludes special vars so no dialog field is shown (`utils/prompts.ts:15`).
- `extractUniqueVariables` deduplicates (`utils/prompts.ts:20-28`).
- Empty field on submit: placeholder token preserved (no replacement when `!value`, `VariableForm.tsx:129`).
- `recordUsage.mutate(group._id)` called after successful non-variable use (`ChatGroupItem.tsx:99`, `PromptsCommand.tsx:123`).
- Version badge: **Live** uses slow-pulse dot + `com_ui_live`; **Latest** uses `Zap` icon + `com_ui_latest` (`PromptVersions.tsx:35,40`).
- `alwaysMakeProd` check: `addPromptToGroupMutation.onSuccess` calls `makeProductionMutation` when true (`PromptForm.tsx:260-266`).
- Description/command debounce: 950 ms (`PromptForm.tsx:369,381`).
- Versions sidebar only in `ADVANCED` mode (`PromptForm.tsx:552`).
- Mobile versions panel: `role="dialog"`, `aria-modal="true"`, focus trap via `useFocusTrap`, `Escape` closes (`PromptForm.tsx:597-599,356`).
- Share button rendered only when `(author === user.id || ADMIN || canShareThisPrompt) && hasAccessToSharePrompts && !permissionsLoading` (`SharePrompt.tsx:41-44`).
- Share dialog title uses `com_ui_share_var` (`GenericGrantAccessDialog.tsx:274`).
- `isPublic` groups display `EarthIcon`; shared-by-another-user groups display `User` icon (`ChatGroupItem.tsx:163-194`).
- Editor delete uses `useDeletePrompt` (single version); list delete uses `useDeletePromptGroup` (whole group) (`DeletePrompt.tsx:85`, `ChatGroupItem.tsx:78`).
- On group deletion, router navigates to `/prompts/new` only if the deleted group was currently open (`ChatGroupItem.tsx:65-67`).
- Command palette triggered by `/`, positioned `absolute bottom-28 z-10`, uses `react-virtualized`, row height 44 px, max height 160 px (`PromptsCommand.tsx:53,202`).
- Popover closes on `Escape`, `Backspace` (empty search), and blur with 150 ms delay (`PromptsCommand.tsx:211,225,234`).
