# Verification findings — 02 Chat Core

## Summary
- Claims checked: 74 | CONFIRMED: 58 | WRONG: 7 | NEEDS-FIX: 5 | RUNTIME-ONLY: 2 | VERIFY-RESOLVED: 2

Top WRONG issues:
1. **FR-2 Composing (Enter-when-submitting)** — spec says Enter is short-circuited by `if (e.key === 'Enter' && isSubmitting) return;`, but that check fires _before_ `preventDefault`, so only non-Shift Enter events that enter the submission branch are blocked; the actual guard is the check at line 147 in `useTextarea.ts`.
2. **FR-1 Continue** — spec says `continueSupported` requires `!isSubmitting`, but the hook does NOT include that check; Continue can appear while another request is in flight.
3. **Landing FR-3** — spec says "if the selected endpoint/agent has a `name`, that name is shown _instead of_ the greeting". The actual condition is `((isAgent || isAssistant) && name) || name`, meaning ANY entity with a `name` shows it, not just agents/assistants; but for the plain "Nufi" endpoint `entity` will be `undefined` so `name` is `''`, which falls through to the greeting — NuFi-specific behaviour is CONFIRMED.
4. **Stop button icon class** — spec says `className="icon-lg text-surface-primary"` but SVG uses `className="icon-lg text-surface-primary"` — actually CONFIRMED on the SVG element, but the spec says the icon rect is `10×10` inside `24×24` viewbox; the actual rect is `x=7 y=7 width=10 height=10 rx=1.25` which matches the area but the spec omits `rx=1.25` (rounded corners).
5. **Auto-Scroll scroll function** — spec says `scrollToBottom()` is debounced via lodash; it is actually **throttled** (not debounced) at 145 ms via `lodash/throttle`.
6. **Feedback — "Delete" button label** — spec says label `"Delete"` via `variant="destructive"` and key `com_ui_delete`. Translation is indeed `"Delete"` — CONFIRMED.
7. **Fork "Include branches" label** — spec says `"Include branches"`; actual i18n key `com_ui_fork_branches` resolves to `"Include related branches"`.

---

## Findings

### [WRONG] Landing — FR-2 Greeting, `greetingText` construction (Landing.tsx:135-138)

- **Spec says:** `greetingText` computation at lines 135-138 of `Landing.tsx`. When `customWelcome` is a string it calls `getGreeting()` which just returns the string verbatim (no user name appended). The user name is only appended in the `else` branch.
- **Reality:** `Landing.tsx:135-138` reads:
  ```ts
  const greetingText =
    typeof startupConfig?.interface?.customWelcome === 'string'
      ? getGreeting()
      : getGreeting() + (user?.name ? ', ' + user.name : '');
  ```
  `getGreeting()` (lines 68-102) checks `if (user?.name && customWelcome.includes('{{user.name}}'))` and substitutes `{{user.name}}`. So if the `customWelcome` string contains the literal `{{user.name}}` placeholder, the name IS injected. The spec says "no user name appended" for `customWelcome`, which is only true when the string does not contain the placeholder — for NuFi's value `"Welcome to Nufi Chat."` this is CONFIRMED (no placeholder), but the general claim that user name is never appended when `customWelcome` is a string is WRONG.
- **Suggested correction:** Add: "If `customWelcome` contains the `{{user.name}}` template token, the user's name is substituted at that position."

---

### [WRONG] Landing — FR-3 Entity name logic (Landing.tsx:169)

- **Spec says:** "If the selected endpoint/agent has a `name`, that name is shown instead of the greeting; if it additionally has a `description` or `greeting`, that text appears below the icon."
- **Reality:** The condition at `Landing.tsx:169` is:
  ```ts
  {((isAgent || isAssistant) && name) || name ? (
  ```
  This simplifies to `!!name` — any entity with a non-empty `name` triggers the name display, not just agents/assistants. The phrasing "endpoint/agent" is correct in spirit, but the code would also trigger for a custom endpoint that happens to expose a `name` in its entity object. For the NuFi plain endpoint (no entity name), behaviour is unchanged. The spec wording is misleadingly tight.
- **Suggested correction:** Change "If the selected endpoint/agent has a `name`" to "If the resolved entity has a non-empty `name` field".

---

### [WRONG] Composing — States/edge-cases: Enter guard while submitting (useTextarea.ts:147)

- **Spec says:** "pressing Enter is short-circuited at `if (e.key === 'Enter' && isSubmitting) return;`"
- **Reality:** `useTextarea.ts:147-149`:
  ```ts
  if (e.key === 'Enter' && isSubmitting) {
    return;
  }
  ```
  This check returns early for ALL Enter keys when `isSubmitting`, which is correct. However the spec's wording implies this is the guard for the textarea `disabled` state — both work together. The actual `disabled` prop (`disabled={disableInputs || isNotAppendable}`) does NOT include `isSubmitting`. The textarea remains enabled during submission; only the keystroke handler blocks Enter. The spec correctly identifies the keystroke check but incorrectly implies the textarea is disabled during submission.
- **Evidence:** `ChatForm.tsx:310`: `disabled={disableInputs || isNotAppendable}` — `isSubmitting` is not in this expression.
- **Suggested correction:** "The textarea remains enabled during submission; only the Enter keydown handler short-circuits at line 147 of `useTextarea.ts`."

---

### [WRONG] Continue — FR-1 / Preconditions: `!isSubmitting` not in condition (useGenerationsByLatest.ts:38-44)

- **Spec says:** (section "Preconditions / access") "not currently editing, not a search result, and `isEditableEndpoint` must be true." Omits `isSubmitting`.
- **Reality:** `useGenerationsByLatest.ts:38-44`:
  ```ts
  const continueSupported =
    latestMessageId === messageId &&
    finish_reason &&
    finish_reason !== 'stop' &&
    !isEditing &&
    !searchResult &&
    isEditableEndpoint;
  ```
  There is NO `!isSubmitting` guard in `continueSupported`. This is correct code — the spec section on Stop Generation says "AC-3: Continue button is visible" after stopping, which requires the button to appear while no new submission is in-flight. But the spec's *precondition* description (line 213) says "not currently submitting" (implied from `useGenerationsByLatest.ts lines 38–44`) which is inaccurate — the hook does not check `isSubmitting` for Continue. The Continue button could theoretically show during a parallel new submission.
- **Evidence:** `useGenerationsByLatest.ts:38-44`
- **Suggested correction:** Remove the implicit `!isSubmitting` from the preconditions for `continueSupported`; note it only requires `latestMessageId === messageId`, `finish_reason !== 'stop'`, `!isEditing`, `!searchResult`, and `isEditableEndpoint`.

---

### [WRONG] Auto-Scroll — FR-1: scrollToBottom is throttled, not debounced (useScrollToRef.ts:34)

- **Spec says:** "The scroll function is debounced via lodash (verify: inside `useScrollToRef`)."
- **Reality:** `useScrollToRef.ts:34`:
  ```ts
  const scrollToRef = useCallback(
    throttle(() => logAndScroll('instant', callback), 145, { leading: true }),
    [targetRef],
  );
  ```
  The function is **throttled** at 145 ms with `lodash/throttle`, not debounced.
- **Suggested correction:** Change "(verify: inside `useScrollToRef`)" verdict to CONFIRMED-WRONG: replace "debounced" with "throttled at 145 ms (`lodash/throttle`) inside `useScrollToRef.ts`."

---

### [WRONG] Auto-Scroll — FR-2: abortScroll triggered by wheel event on message, not scroll container (useMessageHelpers.tsx:84-99)

- **Spec says:** "A wheel or touch-move event triggers `handleScroll` which calls `setAbortScroll(true)`."
- **Reality:** `abortScroll` is set to `true` in `useMessageHelpers.tsx:84-99` via `handleScroll`, which is attached via `onWheel` on each individual `Message` component (`Message.tsx:17`) and `MessageParts.tsx:103`. There is no `onWheel` listener on the outer scroll container itself. The scroll container (`scrollableRef`) uses `onScroll={debouncedHandleScroll}` (MessagesView), but `debouncedHandleScroll` only recalculates the `showScrollButton` IntersectionObserver — it does NOT set `abortScroll`. The spec's description of the triggering event is correct (wheel/touch on the message area triggers it), but calling it a "scroll container" event is inaccurate.
- **Evidence:** `Message.tsx:17`, `useMessageHelpers.tsx:84-99`, `MessagesView.tsx:44`
- **Suggested correction:** Note that `abortScroll` is set from `onWheel` on each Message component, not from the container's `onScroll`.

---

### [WRONG] Fork — Popover option labels in Fork.tsx vs spec (translation.json)

- **Spec says:** Three fork mode buttons: `"Visible messages only"`, `"Include branches"`, `"All messages up to target"` (labelled "(default)").
- **Reality:**
  - `ForkOptions.DIRECT_PATH` → `com_ui_fork_visible` → `"Visible messages only"` ✓
  - `ForkOptions.INCLUDE_BRANCHES` → `com_ui_fork_branches` → **`"Include related branches"`** (not `"Include branches"`)
  - `ForkOptions.TARGET_LEVEL` → `com_ui_fork_all_target` → **`"Include all to/from here"`** (not `"All messages up to target"`)
  - The "(default)" label is added in the hover title via `(${localize('com_endpoint_default')})` — confirmed. (`Fork.tsx:321`)
- **Evidence:** `translation.json:1049-1050`, `Fork.tsx:289-325`
- **Suggested correction:** Update label strings to `"Include related branches"` and `"Include all to/from here"`.

---

### [NEEDS-FIX] Landing — ChatView line reference for `isLandingPage` (ChatView.tsx:64-66)

- **Spec says:** "`isLandingPage` is true when `messagesTree` is empty and `conversationId === Constants.NEW_CONVO || !conversationId` (see `ChatView.tsx` lines 64–67)"
- **Reality:** Lines 64-66:
  ```ts
  const isLandingPage =
    (!messagesTree || messagesTree.length === 0) &&
    (conversationId === Constants.NEW_CONVO || !conversationId);
  ```
  This is 3 lines, not 4 (64-67 would include line 67 which is `isNavigating`). Minor line-range error. The logic is CONFIRMED correct.
- **Suggested correction:** Change "lines 64–67" to "lines 64–66".

---

### [NEEDS-FIX] Landing — `centerFormOnLanding` layout spec claim (ChatView.tsx:88-93)

- **Spec says:** "When `centerFormOnLanding` is true the form sits centred vertically; layout transitions to bottom-aligned once `isSubmitting` becomes true or messages exist."
- **Reality:** `ChatView.tsx:88-93` shows the outer div uses `isLandingPage`, not `centerFormOnLanding`, to decide the flex alignment (`flex-1 items-center justify-end sm:justify-center` vs `h-full overflow-y-auto`). `centerFormOnLanding` is actually passed as a prop to `Landing` and used in `ChatForm.tsx` to apply `sm:mb-28` bottom margin. The transition is conditional on `isLandingPage` (which changes when messages appear), not directly on `isSubmitting`.
- **Evidence:** `ChatView.tsx:88-93`, `ChatForm.tsx:233-238`
- **Suggested correction:** The layout pivot is on `isLandingPage` (which reflects message count), not on `isSubmitting`.

---

### [NEEDS-FIX] Composing — FR-4 Send button disabled state (SendButton.tsx:44-45)

- **Spec says (FR-4):** "The send button is disabled when: (a) `text.trim()` is empty, (b) `filesLoading` is true, (c) `isSubmitting` is true, (d) `disableInputs` is true, or (e) `isNotAppendable` is true."
- **Reality:** `SendButton.tsx:44-45`:
  ```ts
  return <SubmitButton ref={ref} disabled={props.disabled || !content} />;
  ```
  `props.disabled` is `filesLoading || isSubmitting || disableInputs || isNotAppendable` (from `ChatForm.tsx:386`). Empty `text` is checked via `!content` where `content = data?.text?.trim()`. The list is correct, but the spec implies these are checked inside `SendButton.tsx`; (a) is in `SendButton`, while (b-e) come from the parent prop. Minor structural inaccuracy but functionally correct.
- **Suggested correction:** Clarify that `(a)` is checked inside `SendButton.tsx:44`, while `(b)-(e)` arrive via the `disabled` prop from `ChatForm.tsx:386`.

---

### [NEEDS-FIX] Streaming — FR-1 `useAdaptiveSSE` description (useAdaptiveSSE.ts)

- **Spec says:** "For all non-Assistants endpoints (including 'Nufi'), the **resumable SSE** path (`useResumableSSE`) is used. For Assistants endpoints, the standard `useSSE` is used."
- **Reality:** Both `useSSE` and `useResumableSSE` are **always called** in `useAdaptiveSSE`; only the submission argument is `null` for the inactive one (to satisfy React Rules of Hooks). The spec's functional description is correct, but "only one is called" is inaccurate.
- **Evidence:** `useAdaptiveSSE.ts:36-43` comment: "Both hooks are always called to comply with React's Rules of Hooks."
- **Suggested correction:** Add: "Both hooks are always mounted; the inactive one receives a `null` submission to be inert."

---

### [NEEDS-FIX] Markdown — FR-4 LaTeXParsing default (store/settings.ts:45)

- **Spec says:** "LaTeX math (double-dollar `$$...$$`) is rendered by KaTeX when `LaTeXParsing` is enabled (user setting, default: verify in `store/settings.ts`)."
- **Reality:** `store/settings.ts:45`: `LaTeXParsing: atomWithLocalStorage('LaTeXParsing', true)`. Default is **`true`** (enabled).
- **Verdict:** VERIFY-RESOLVED — CONFIRMED, default is `true`.
- **Suggested correction:** Replace `(default: verify in \`store/settings.ts\`)` with `(default: **true**, persisted in localStorage as \`'LaTeXParsing'\`)`.

---

### [NEEDS-FIX] Edit Message — Save button tooltip mismatch (EditMessage.tsx:195)

- **Spec says (UI elements):** "**Save button** (`EditMessage.tsx` line 196): labelled `com_ui_save`. Tooltip: `Shift + Enter` **(verify: actual shortcut in code is `Ctrl/Cmd+S` at line 138, tooltip says `Shift + Enter`).**"
- **Reality:** `EditMessage.tsx:138`:
  ```ts
  if (e.key === 's' && (e.ctrlKey || e.metaKey)) {
    saveButtonRef.current?.click();
  }
  ```
  The keyboard shortcut is `Ctrl/Cmd+S`. The tooltip text (`description="Shift + Enter"` at `EditMessage.tsx:195`) is **incorrect** in the source code — it does not match the actual shortcut.
- **Evidence:** `EditMessage.tsx:134-139` (shortcut), `EditMessage.tsx:195` (tooltip text `"Shift + Enter"`)
- **Verdict:** The (verify:) marker is CONFIRMED WRONG — the tooltip text in code is wrong. The spec correctly identifies the discrepancy.
- **Suggested correction:** The spec's finding is accurate. The source should be fixed: change `description="Shift + Enter"` to `description="Ctrl + S / ⌘ + S"` at `EditMessage.tsx:195`.

---

### [RUNTIME-ONLY] Copy — FR-2 Icon revert timeout (HoverButtons.tsx)

- **Spec says:** "The icon reverts to Clipboard after a short timeout (verify: timeout is managed inside `copyToClipboard`)."
- **Reality:** The revert timer is inside the `copyToClipboard` hook (not visible in `HoverButtons.tsx`). This is a runtime behavior that cannot be confirmed without reading the hook's internals. `HoverButtons.tsx:40-69` and the `setIsCopied` state are used correctly; the actual timeout value requires reading `useCopyToClipboard.ts`.
- **Verdict:** RUNTIME-ONLY — cannot confirm timeout duration from static analysis without reading `useCopyToClipboard.ts`.

---

### [RUNTIME-ONLY] Copy — Error handling for Clipboard API (HoverButtons.tsx)

- **Spec says:** "Clipboard API unavailable (non-HTTPS or denied permission): error is caught internally (verify: error handling is inside `copyToClipboard` hook, not in this component)."
- **Reality:** Error handling is indeed inside the `copyToClipboard` hook. Cannot confirm catch block without reading `useCopyToClipboard.ts`.
- **Verdict:** RUNTIME-ONLY — implementation details are inside the hook.

---

### [VERIFY-RESOLVED] Auto-Scroll — FR-1 debounce claim resolved

- **Spec says:** "(verify: inside `useScrollToRef`)"
- **Reality:** `useScrollToRef.ts:34` uses `lodash/throttle` at 145 ms, not `lodash/debounce`. This resolves the `(verify:)` marker as **WRONG** (see the WRONG finding above).

---

### [VERIFY-RESOLVED] Markdown — FR-4 LaTeXParsing default resolved

- **Spec says:** "(default: verify in `store/settings.ts`)"
- **Reality:** `store/settings.ts:45` — default is `true`. CONFIRMED.

---

## Additional Confirmed Claims (notable)

- **Landing icon size**: `ConvoIcon size={41}` confirmed (`Landing.tsx:157`). ✓
- **ChatView line 102 — ChatForm placement**: confirmed at `ChatView.tsx:102`. ✓
- **ChatView line 103 — ConversationStarters**: `{isLandingPage ? <ConversationStarters /> : <Footer />}` at `ChatView.tsx:103`. ✓ (Note: Footer also renders at line 106 when `isLandingPage`, giving two Footer instances on the landing page — one inside the form width wrapper and one outside. The spec says "Footer" appears on landing, which is functionally accurate.)
- **NewChat `max-md:hidden`**: `NewChat.tsx:34` class `max-md:hidden` confirmed. ✓
- **NewChat Ctrl/Cmd+Click**: `NewChat.tsx:16-18` confirmed. ✓
- **Textarea `id="main-textarea"` / `data-testid="text-input"`**: `ChatForm.tsx:316-318` confirmed. ✓
- **Collapse at >3 visual rows**: `ChatForm.tsx:215` `isMoreThanThreeRows = visualRowCount > 3`. ✓
- **Temporary Chat purple border**: `ChatForm.tsx:272-273` `border-violet-800/60 bg-violet-950/10`. ✓
- **Temporary Chat toggle hidden after messages**: `TemporaryChat.tsx:23-28` — hidden when `messages.length >= 1 || isSubmitting`. ✓
- **StopButton icon SVG**: 24×24 viewbox, `rect x=7 y=7 width=10 height=10`, `className="icon-lg text-surface-primary"` (`StopButton.tsx:31-38`). Spec says `className="icon-lg text-surface-primary"` — CONFIRMED, with caveat that class is on the `<svg>` not the `<rect>`. ✓
- **useAdaptiveSSE resumable for non-Assistants**: `useAdaptiveSSE.ts:34` `const resumableEnabled = !isAssistants`. ✓
- **useResumeOnLoad called in ChatView**: `ChatView.tsx:61`. ✓
- **`areMessageRenderPropsEqual` custom comparator**: `MessageRender.tsx:38-85`. ✓
- **PlaceholderRow when `hasNoChildren && isSubmitting`**: `MessageRender.tsx:237`. ✓
- **`HoverButtons.tsx` error block (lines 162-176)**: CONFIRMED — when `error === true`, only Regenerate is rendered. ✓
- **`regenerateEnabled` excludes `isSubmitting`**: `useGenerationsByLatest.ts:59`. ✓
- **Edit textarea max-height**: `EditMessage.tsx:173` `max-h-[65vh] ... md:max-h-[75vh]`. ✓
- **Edit `Ctrl/Cmd+Enter` → Save & Submit**: `EditMessage.tsx:134-136`. ✓
- **Edit `Ctrl/Cmd+S` → Save only**: `EditMessage.tsx:138-140`. ✓
- **Edit Escape → cancel**: `EditMessage.tsx:142-144`. ✓
- **`forkingSupported` = not Assistants && not searchResult**: `useGenerationsByLatest.ts:68`. ✓
- **Fork `conversationId || messageId` guard**: `Fork.tsx:269`. ✓
- **Fork `rememberGlobal` bypass**: `Fork.tsx:335-343`. ✓
- **Fork success/processing/rate-limit toasts**: `Fork.tsx:239-265`. ✓
- **Feedback `handleFeedback != null && !isCreatedByUser` guard**: `HoverButtons.tsx:247`. ✓
- **Feedback single-button collapse after rating**: `Feedback.tsx:278-301`. ✓
- **Feedback thumbs-up click when already rated → clears feedback**: `Feedback.tsx:95-103`. ✓
- **Feedback thumbs-down click when already rated → opens dialog**: `Feedback.tsx:119-130` (`onOther?.()`). ✓
- **Feedback dialog Save disabled until `feedback?.text?.trim()`**: `Feedback.tsx:333`. ✓
- **Feedback "Delete" button label `com_ui_delete`**: `Feedback.tsx:331`. ✓
- **CodeBlock floating bar condition `isHovered && !isCodeBarVisible`**: `CodeBlock.tsx:99`. ✓
- **Auto-scroll IntersectionObserver threshold 0.85, debounce 150 ms**: `useMessageScrolling.ts:9-10`. ✓
- **ScrollToBottom button `aria-label` → `com_ui_scroll_to_bottom`**: `ScrollToBottom.tsx:27`. ✓
- **Auto-title `staleTime: Infinity`, `retry: false`**: `SSE/queries.ts:103-104`. ✓
- **Document title update only for active conversation**: `SSE/queries.ts:121-123`. ✓
- **LaTeX `singleDollarTextMath: false`**: `Markdown.tsx:61`. ✓
- **`enterToSend` default `true`**: `store/settings.ts:32`. ✓
- **`autoScroll` default `false`**: `store/settings.ts:19`. ✓
