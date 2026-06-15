## Chat Core — Conversations & Messaging

This section specifies the end-user-visible behaviour of the core chat loop in NuFi Chat: starting conversations, composing and sending messages, receiving streamed responses, and all per-message actions. All statements are grounded in the source code of the LibreChat fork at `/Users/sun/Workspace/DudajiVN/LibreChat`.

---

### New Conversation / Landing Screen

- **Purpose:** Provide a welcoming entry point when no conversation is active, and let the user begin a new conversation at any time.

- **Preconditions / access:** Any authenticated user. Displayed automatically on first load and whenever the URL is `/c/new` or no `conversationId` is present (see `ChatView.tsx` lines 64–66: `isLandingPage` is true when `messagesTree` is empty and `conversationId === Constants.NEW_CONVO || !conversationId`).

- **UI elements:**
  - **Greeting text** (`Landing.tsx` lines 135–138): rendered by `SplitText` with a word-by-word entrance animation (`easeOutCubic`, 50 ms delay per word). When `startupConfig.interface.customWelcome` is a string it is used as-is, unless it contains the `{{user.name}}` template token — in which case the user's name is substituted at that position; otherwise a time-of-day greeting is appended with `, <user.name>` if the user has a name set. NuFi Chat sets `customWelcome: "Welcome to Nufi Chat."` (no `{{user.name}}` token), so the greeting is always **"Welcome to Nufi Chat."** (no time-of-day variation, no user name appended).
  - **Endpoint icon** (`Landing.tsx` lines 147–167): a 41×41 px rounded icon for the active endpoint/agent rendered by `ConvoIcon`.
  - **Optional birthday icon** (shown only when `startupConfig.showBirthdayIcon` is true; not expected in NuFi default config).
  - **Description text** (shown only when the active entity has a `description` or `greeting` field; not applicable to the plain "Nufi" endpoint).
  - **Chat input form** (`ChatView.tsx` line 102): positioned below the greeting. When `centerFormOnLanding` is true (`ChatForm.tsx` lines 233–238) an extra bottom margin is applied on the landing page. The layout pivot from centred to bottom-aligned is controlled by `isLandingPage` (which flips when messages appear), not directly by `isSubmitting`.
  - **Conversation Starters** (`ConversationStarters.tsx`, `ChatView.tsx` line 103): rendered only when the active agent/assistant exposes `conversation_starters`. Not present for the base "Nufi" endpoint.
  - **Footer** (`Footer.tsx`): displays "NUFI \<VERSION\>" (or `config.customFooter` if set). Hidden on mobile (`sm:flex`). Renders privacy-policy and terms-of-service links if configured.
  - **"New Chat" button** (sidebar, `NewChat.tsx` `aria-label="com_ui_new_chat"`): pencil-like `NewChatIcon`. Ctrl/Cmd+Click opens `/c/new` in a new browser tab.

- **Functional behavior:**
  - FR-1. When the user navigates to `/c/new` or clicks "New Chat", `ChatView` renders the `Landing` component and the `ChatForm` instead of `MessagesView`.
  - FR-2. The greeting text "Welcome to Nufi Chat." is displayed with a staggered letter/word animation (SplitText).
  - FR-3. If the resolved entity has a non-empty `name` field, that name is shown instead of the greeting; if it additionally has a `description` or `greeting`, that text appears below the icon.
  - FR-4. Clicking "New Chat" clears the messages cache for the previous conversation (`clearMessagesCache`) and calls `newConversation()`, then navigates to `/c/new`.
  - FR-5. Ctrl/Cmd+clicking "New Chat" opens `/c/new` in a new tab without clearing the current session.

- **States & edge cases:**
  - When `messagesTree` is being fetched for an existing `conversationId`, a centered `<Spinner>` is shown instead of the landing or messages view.
  - If the `conversationId` is non-null but `messagesTree` is still empty and loading, `isNavigating` is true and a spinner is shown (prevents flash of landing screen).
  - On mobile (`max-width: 768px`) the sidebar is collapsed; the "New Chat" button is hidden (`max-md:hidden`). New conversations are started from the `OpenSidebar` menu.

- **Acceptance criteria:**
  - AC-1. Given a logged-in user navigates to `/c/new`, when the page renders, then the text "Welcome to Nufi Chat." appears in the landing area with an animated entrance.
  - AC-2. Given the user is on a conversation page with messages, when they click "New Chat", then the URL changes to `/c/new` and the landing screen is shown.
  - AC-3. Given the user Ctrl/Cmd+clicks "New Chat", when the browser handles the click, then `/c/new` opens in a new tab and the current tab remains unchanged.
  - AC-4. Given a conversation is loading (spinner visible), when loading completes with messages, then the landing screen does not flash before MessagesView appears.

---

### Composing & Sending a Message

- **Purpose:** Allow the user to type a message and submit it to the model.

- **Preconditions / access:** An authenticated user with at least one endpoint configured. The "Nufi" endpoint must be available. Input is disabled (`disableInputs`) when `requiresKey` is true (API key required but missing) or when an invalid assistant is selected.

- **UI elements:**
  - **Message textarea** (`ChatForm.tsx` line 303): `TextareaAutosize`, `id="main-textarea"`, `data-testid="text-input"`, `aria-label` → `com_ui_message_input`. Starts at 44 px height, expands up to 45 vh (mobile) / 55 vh (desktop).
  - **Collapse/Expand button** (`CollapseChat`, `ChatForm.tsx` line 333): appears when textarea exceeds 3 visual rows; collapses textarea to `max-h-[52px]` with a fade mask.
  - **Attach file button** (`AttachFileChat`, `ChatForm.tsx` line 348): paper-clip icon at bottom-left.
  - **Send button** (`SendButton.tsx`, `id="send-button"`, `data-testid="send-button"`, `aria-label` → `com_nav_send_message`): rounded filled circle with `SendIcon` (24 px). Disabled state: `opacity-10`, `cursor-not-allowed`.
  - **Stop button** (`StopButton.tsx`, `aria-label` → `com_nav_stop_generating`): replaces the Send button during submission; rounded circle with a filled square icon (10×10 px rect inside 24×24 viewbox).
  - **Badge row** (`BadgeRow`): ephemeral feature badges (e.g., web search) shown for non-agents/non-assistants endpoints.
  - **Audio recorder** (`AudioRecorder`): shown only when `SpeechToText` setting is enabled.
  - **Temporary Chat toggle** (`TemporaryChat.tsx`): `MessageCircleDashed` icon, `aria-label` → `com_ui_temporary`. Visible in the header only when the conversation has no messages and is not submitting.

- **Functional behavior:**
  - FR-1. **Enter to send (default):** When `enterToSend` store atom is `true` (default, persisted in localStorage as `'enterToSend'`), pressing `Enter` without `Shift` calls `submitButtonRef.current?.click()` which submits the form. Pressing `Shift+Enter` inserts a newline.
  - FR-2. **Enter to send disabled:** When `enterToSend` is `false`, pressing `Enter` inserts a newline. `Ctrl/Cmd+Enter` submits regardless of the `enterToSend` setting.
  - FR-3. **IME/Composition guard:** While an IME composition is active (`isComposing.current`, `e.key === 'Process'`, or `e.keyCode === 229`), Enter does not submit. This prevents accidental submission during CJK input.
  - FR-4. **Send button state:** The send button is disabled when: (a) `text.trim()` is empty — checked inside `SendButton.tsx:44` via `!content`; or (b) `filesLoading` is true, (c) `isSubmitting` is true, (d) `disableInputs` is true, or (e) `isNotAppendable` is true — conditions (b)–(e) arrive via the `disabled` prop from `ChatForm.tsx:386`.
  - FR-5. **Stop button visibility:** While `isSubmitting && showStopButton` is true, the Stop button is rendered in place of the Send button. `showStopButton` is a per-index Recoil atom (`store.showStopButtonByIndex(index)`).
  - FR-6. **Auto-save:** The `useAutoSave` hook persists draft text and attached files for the current `conversationId` while composing. Drafts are restored if the user navigates away and returns before submitting.
  - FR-7. **Temporary Chat mode:** When enabled (purple border and background: `border-violet-800/60 bg-violet-950/10`), the conversation is not saved to history. The toggle is only accessible before the first message is sent.
  - FR-8. **RTL support:** When `chatDirection` is `'rtl'`, the flex row is reversed and text is right-aligned.
  - FR-9. **Ctrl/Cmd+Enter in edit mode:** Within the edit-message form (`EditMessage.tsx` line 134), `Ctrl/Cmd+Enter` triggers Save & Submit, and `Ctrl/Cmd+S` triggers Save only.

- **States & edge cases:**
  - Empty text: Send button disabled; pressing Enter has no effect.
  - Files uploading: Send button shows `disabled` until `filesLoading` becomes false.
  - Already submitting: the textarea remains enabled during submission (`disabled={disableInputs || isNotAppendable}` in `ChatForm.tsx:310` — `isSubmitting` is not in that expression); only the Enter keydown handler short-circuits at `if (e.key === 'Enter' && isSubmitting) return;` (`useTextarea.ts:147`).
  - Very long message (>3 visual rows): Collapse button appears; when collapsed, textarea shows a fade-out gradient mask.
  - Requires API key: both textarea and send button are disabled; `cursor-not-allowed` is shown.

- **Acceptance criteria:**
  - AC-1. Given the textarea is empty, when the user presses Enter, then no message is sent and the send button remains disabled.
  - AC-2. Given `enterToSend` is true and the textarea contains text, when the user presses Enter (without Shift), then the message is submitted.
  - AC-3. Given `enterToSend` is true and the textarea contains text, when the user presses Shift+Enter, then a newline is inserted and no submission occurs.
  - AC-4. Given `enterToSend` is false and the textarea contains text, when the user presses Ctrl/Cmd+Enter, then the message is submitted.
  - AC-5. Given a generation is in progress, when the user looks at the input area, then the Stop button (filled square icon) is visible in place of the Send button.
  - AC-6. Given Temporary Chat is toggled on before any message is sent, when a message is submitted, then the conversation is not saved to history and the input container shows a purple border.

---

### Streaming Response & Live Rendering

- **Purpose:** Display the model's response token-by-token as it is generated, providing real-time feedback.

- **Preconditions / access:** A message has been submitted. The selected endpoint must be reachable. The SSE stream must be established.

- **UI elements:**
  - **Streaming cursor / thinking indicator** (`Markdown.tsx` lines 66–73): when `content === ''` (initializing), a `<span className="result-thinking">` is rendered as a pulsing placeholder.
  - **Message bubble:** the latest assistant message is progressively updated in `MessagesView` via `MultiMessage` → `Message` → `MessageRender` → `MessageContent`.
  - **PlaceholderRow** (`ui/PlaceholderRow.tsx`): shown in `MessageRender` (`lines 237–239`) while `hasNoChildren && isSubmitting`; replaces the hover-buttons row during generation so layout does not shift.

- **Functional behavior:**
  - FR-1. **SSE transport selection (`useAdaptiveSSE.ts`):** For all non-Assistants endpoints (including "Nufi"), the **resumable SSE** path (`useResumableSSE`) is active. For Assistants endpoints, the standard `useSSE` is active. Both hooks are always mounted to comply with React's Rules of Hooks; the inactive one receives a `null` submission to remain inert.
  - FR-2. **Resume on navigation:** `useResumeOnLoad` (called in `ChatView.tsx` line 61) detects an active job for the current `conversationId` after navigation and resumes streaming. It waits until `!isLoading` to avoid a race condition.
  - FR-3. **Markdown rendered live:** As tokens arrive, the `Markdown` component re-renders with the growing `content` string. `rehype-highlight` syntax-highlights code; `rehype-katex` / `remark-math` renders LaTeX (when `LaTeXParsing` setting is on); `remark-gfm` enables tables, strikethrough, and task lists.
  - FR-4. **Auto-scroll during streaming:** `useMessageScrolling` calls `scrollToBottom()` on every tree update while `isSubmitting && abortScroll !== true`. If the user scrolls up manually, `abortScroll` is set to true and auto-scroll stops.
  - FR-5. **Memoisation:** `MessageRender` uses a custom `areMessageRenderPropsEqual` comparator so only the actively streaming message re-renders on each SSE event; older messages in the thread remain stable.
  - FR-6. **Text-to-speech playback:** When `TextToSpeech && automaticPlayback` are both true, `StreamAudio` plays the assistant response audio automatically.

- **States & edge cases:**
  - Network drop mid-stream: the resumable SSE mechanism tracks a `streamId`; if the user reloads or navigates away and returns, `useResumeOnLoad` attempts to reconnect to the in-progress job.
  - Empty first token: the `result-thinking` pulsing span is shown until the first non-empty content chunk arrives.
  - Error from server: `message.error = true` is set; the message text shows the error; only a Regenerate button is rendered in place of the full hover-button row (`HoverButtons.tsx` lines 162–176).
  - Very long response: the message container is scrollable; the `ScrollToBottom` chevron button appears when the user scrolls up far enough that the `messagesEndRef` sentinel exits the viewport (IntersectionObserver threshold 0.85).

- **Acceptance criteria:**
  - AC-1. Given a message has been submitted, when the first token arrives, then the pulsing `result-thinking` indicator disappears and text begins rendering.
  - AC-2. Given the response is streaming, when the user scrolls up, then auto-scroll stops and the "scroll to bottom" chevron button appears.
  - AC-3. Given the response is streaming and the user is at the bottom, when new tokens arrive, then the viewport scrolls automatically to show the new content.
  - AC-4. Given the user navigates away mid-stream and returns to the same conversation, when the page loads, then streaming resumes from the point it left off (resumable SSE path).
  - AC-5. Given a server error occurs, when the error is received, then the assistant message shows the error text and a Regenerate button; no other hover buttons are shown.

---

### Stop Generation

- **Purpose:** Allow the user to immediately halt an in-progress AI response.

- **Preconditions / access:** A generation is in progress (`isSubmitting === true && showStopButton === true`).

- **UI elements:**
  - **Stop button** (`StopButton.tsx`): replaces the Send button; rounded circle, `aria-label` → `com_nav_stop_generating`; icon is a filled 10×10 square (`rect` SVG element, `className="icon-lg text-surface-primary"`). Tooltip shows the localized label on hover.

- **Functional behavior:**
  - FR-1. Clicking the Stop button calls `setShowStopButton(false)` then `stop(e)` (i.e., `handleStopGenerating`), which sends a cancellation signal to the backend stream.
  - FR-2. After stop, `isSubmitting` becomes false. The Stop button is replaced by the Send button.
  - FR-3. The partially delivered message remains in the conversation; it is not deleted. It may carry `unfinished: true` or a non-`'stop'` `finish_reason`, making the **Continue** button eligible to appear.

- **States & edge cases:**
  - Double-click: The button hides itself immediately on first click (`setShowStopButton(false)`), preventing a second click.
  - Very fast response: If the response completes before the user clicks Stop, the button transitions back to Send naturally.
  - Network already lost: The abort signal is sent; UI transitions to idle state even if the server does not acknowledge.

- **Acceptance criteria:**
  - AC-1. Given a generation is streaming, when the user clicks the Stop button, then the Stop button disappears and the Send button reappears within one render cycle.
  - AC-2. Given the Stop button has been clicked, when the UI settles, then the partially generated assistant message is visible and not deleted.
  - AC-3. Given the Stop button is clicked, when the response was truncated mid-sentence, then the Continue button is visible on the last assistant message (see Continue section).

---

### Regenerate Response

- **Purpose:** Request a new response to the same user turn, discarding the current assistant message.

- **Preconditions / access:** The message must be an assistant message (`isCreatedByUser === false`). `regenerateEnabled` is true when: not a user message, not a search result, not currently editing, not currently submitting, and the endpoint is one of: `openAI`, `custom`, `google`, `agents`, `bedrock`, `anthropic`, `azureOpenAI` (see `useGenerationsByLatest.ts` lines 46–59). "Nufi" uses a `custom` endpoint type, so regenerate is supported.

- **UI elements:**
  - **Regenerate button** (`HoverButtons.tsx` lines 252–260): `RegenerateIcon` (19 px), `title` → `com_ui_regenerate`. Hover buttons are hidden at `md:opacity-0` and revealed on `group-hover` / `group-focus-within` / `group-[.final-completion]`. The Regenerate button has class `active` so it may be always visible on the last message.

- **Functional behavior:**
  - FR-1. Clicking Regenerate calls `regenerateMessage()` → `handleRegenerateMessage()` which calls `ask()` with the parent user message's context. A new streaming response replaces the current assistant message.
  - FR-2. The old response is not deleted from history; the conversation tree branches (a sibling node is created). The `SiblingSwitch` component (`SiblingSwitch.tsx`) allows navigation between the original and regenerated responses.
  - FR-3. Regenerate is disabled (`regenerateEnabled = false`) while `isSubmitting` is true, preventing concurrent submissions.

- **States & edge cases:**
  - Multiple regenerations: each creates a sibling branch; `siblingCount` increases. The `SiblingSwitch` shows `<idx>/<total>` navigation.
  - Error message: when `message.error === true`, a Regenerate button is shown alone without the other hover buttons (`HoverButtons.tsx` lines 162–176).
  - Non-branching endpoint (e.g., Assistants): `branchingSupported` is false; Regenerate button is hidden.

- **Acceptance criteria:**
  - AC-1. Given the last assistant message is visible and no generation is in progress, when the user hovers the message and clicks Regenerate, then a new streaming response begins.
  - AC-2. Given a regeneration completes, when the user looks at the message, then a sibling switcher (`1/2`, `2/2`, etc.) is visible to navigate between responses.
  - AC-3. Given a generation is in progress, when the user hovers any message, then the Regenerate button is not clickable/visible (opacity-0 or disabled).

---

### Edit a Sent Message & Resubmit

- **Purpose:** Allow the user to correct a previously sent message and re-run the conversation from that point.

- **Preconditions / access:** The button `isEditableEndpoint` must be true (same endpoint list as Regenerate; "Nufi"/custom qualifies). `hideEditButton` is false (not submitting, not an error, not a search result). Both user messages and assistant messages can be edited.

- **UI elements:**
  - **Edit button** (`HoverButtons.tsx` lines 223–235): `EditIcon` (19 px), `id="edit-<messageId>"`, `title` → `com_ui_edit`. Hidden/disabled via `isVisible={!hideEditButton}`. Active state when `isEditing === true`.
  - **Edit textarea** (`EditMessage.tsx` line 160): `TextareaAutosize`, `data-testid="message-text-editor"`, `aria-label` → `com_ui_message_input`. Max height 65 vh (mobile) / 75 vh (desktop). Focused and caret placed at end on mount.
  - **Save & Submit button** (`EditMessage.tsx` line 184): labelled `com_ui_save_submit`. Tooltip: `Ctrl + Enter / ⌘ + Enter`. Disabled while `isSubmitting`.
  - **Save button** (`EditMessage.tsx` line 196): labelled `com_ui_save`. The working keyboard shortcut is **`Ctrl/Cmd+S`** (`EditMessage.tsx:138`). Note: the in-UI tooltip (`description` prop at `EditMessage.tsx:195`) misleadingly shows `"Shift + Enter"`, which does not match the actual shortcut — testers should use `Ctrl/Cmd+S` and expect the tooltip to be incorrect.
  - **Cancel button** (`EditMessage.tsx` line 207): labelled `com_ui_cancel`. Tooltip: `Esc`.

- **Functional behavior:**
  - FR-1. Clicking Edit enters edit mode (`enterEdit()`). The message content is replaced by an editable `TextareaAutosize` pre-populated with the current message text.
  - FR-2. **Save & Submit** (user message): calls `ask()` with `{ text: newText, parentMessageId, conversationId }`, overriding files and manual skills from the original message. `setSiblingIdx(siblingIdx - 1)` branches the tree. The keyboard shortcut is `Ctrl/Cmd+Enter`.
  - FR-3. **Save & Submit** (assistant message): calls `ask()` with the parent user message, passing `editedText`, `editedMessageId`, `isRegenerate: true`, `isEdited: true`. The keyboard shortcut is the same.
  - FR-4. **Save only** (no resubmit): calls `updateMessageMutation.mutate()` to persist the edited text in the database without triggering a new generation. The keyboard shortcut is `Ctrl/Cmd+S`.
  - FR-5. **Cancel**: calls `enterEdit(true)` restoring the original display. Keyboard shortcut: `Escape`.
  - FR-6. Editing a message that is not the latest creates a branch; the `SiblingSwitch` allows navigation between the original and the edited fork.

- **States & edge cases:**
  - Clicking Edit again while in edit mode: `onEdit` detects `isEditing === true` and calls `enterEdit(true)` (cancels).
  - Submitting another message while edit is open: `isSubmitting` becomes true, disabling the Save & Submit button.
  - Very long pre-existing text: textarea is pre-scrolled to end; max-height prevents page overflow.
  - Empty edit: "Save & Submit" validates `required: true`; submitting empty text is prevented by react-hook-form.

- **Acceptance criteria:**
  - AC-1. Given a user message is displayed, when the user clicks Edit, then the message text becomes editable in a textarea focused at the end.
  - AC-2. Given the edit textarea is open with modified text, when the user presses Ctrl/Cmd+Enter, then the edited message is submitted and a new assistant response streams in.
  - AC-3. Given the edit textarea is open, when the user presses Escape, then the textarea closes and the original message text is restored.
  - AC-4. Given an assistant message is edited and Save & Submit is clicked, then a new assistant response is generated using the same parent user prompt with the edited assistant text injected.
  - AC-5. Given Save (not Submit) is clicked on any message, when the save completes, then the message text is updated in-place and no new generation is triggered.

---

### Continue a Truncated Response

- **Purpose:** Request the model to continue generating from where a truncated response ended (e.g., after hitting token limit or after Stop).

- **Preconditions / access:** `continueSupported` is true. From `useGenerationsByLatest.ts` lines 38–44: the message must be the latest (`latestMessageId === messageId`), `finish_reason` must be set and must not be `'stop'`, not currently editing (`!isEditing`), not a search result (`!searchResult`), and `isEditableEndpoint` must be true. There is no `!isSubmitting` check in `continueSupported` — the Continue button can appear even while another request is in flight.

- **UI elements:**
  - **Continue button** (`HoverButtons.tsx` lines 263–271): `ContinueIcon` (rotated 180°, `className="w-19 h-19 -rotate-180"`), `title` → `com_ui_continue`. Shown only when `continueSupported` is true.

- **Functional behavior:**
  - FR-1. Clicking Continue calls `handleContinue(e)`, which submits a continuation request to the backend using the existing conversation context. The response continues from the truncated point.
  - FR-2. Once a continuation completes with `finish_reason === 'stop'`, the Continue button disappears.
  - FR-3. The continuation appends to (or replaces, depending on backend handling) the existing assistant message.

- **States & edge cases:**
  - If the user edits a message, `isEditing` becomes true and Continue is hidden.
  - If another request is in progress, `continueSupported` evaluates to false because `latestMessageId` changes.

- **Acceptance criteria:**
  - AC-1. Given an assistant message has `finish_reason` that is not `'stop'` (e.g., `'length'`), when the user hovers that message, then the Continue button is visible.
  - AC-2. Given the user clicks Continue, when the continuation finishes with `finish_reason === 'stop'`, then the Continue button disappears.
  - AC-3. Given a message completed normally (`finish_reason === 'stop'`), when the user hovers it, then the Continue button is not shown.

---

### Copy Message

- **Purpose:** Let the user copy the full text content of any message to the system clipboard.

- **Preconditions / access:** Any rendered message (user or assistant).

- **UI elements:**
  - **Copy button** (`HoverButtons.tsx` lines 209–220): `Clipboard` icon (19 px) in idle state; `CheckMark` icon (18×18 px) after copy. Title toggles between `com_ui_copy_to_clipboard` and `com_ui_copied_to_clipboard`. Has `className="ml-0 flex items-center gap-1.5 text-xs"`.

- **Functional behavior:**
  - FR-1. Clicking the button calls `copyToClipboard(setIsCopied)`. The full message text is extracted by `extractMessageContent(message)` (`HoverButtons.tsx` lines 40–70), which handles three content shapes: plain `string`, array of content parts (extracting `text` and `think` fields), and the legacy `message.text` field.
  - FR-2. On successful copy, `setIsCopied(true)` is called, switching the icon to CheckMark. The icon reverts to Clipboard after a short timeout (requires manual verification on the running product: timeout duration is managed inside `useCopyToClipboard`, not visible from `HoverButtons.tsx`).
  - FR-3. The copy button is always visible on the latest message; on older messages it is hidden at `md:opacity-0` and revealed on hover/focus.

- **States & edge cases:**
  - Message with mixed content (text + think blocks): all text portions are concatenated in order.
  - Message currently streaming: Copy is available; the partial content up to that point is copied.
  - Clipboard API unavailable (non-HTTPS or denied permission): error is caught internally (requires manual verification on the running product: the catch block is inside the `copyToClipboard` hook and is not visible from `HoverButtons.tsx`).

- **Acceptance criteria:**
  - AC-1. Given an assistant message is rendered, when the user clicks the Copy button, then the CheckMark icon appears confirming the copy.
  - AC-2. Given the Copy button was clicked, when a moment passes, then the icon returns to the Clipboard icon.
  - AC-3. Given a multi-part message (text + reasoning blocks), when copied, then the clipboard contains all text portions concatenated.

---

### Fork Conversation

- **Purpose:** Create a new independent conversation branch starting from a selected message, preserving the original conversation intact.

- **Preconditions / access:** `forkingSupported` is true (`useGenerationsByLatest.ts` line 68): endpoint must not be an Assistants endpoint, and the message must not be a search result. `conversationId` and `messageId` must be non-empty (`Fork.tsx` line 269).

- **UI elements:**
  - **Fork button** (`Fork.tsx` line 332): `GitFork` icon (19 px, from `lucide-react`), `aria-label` → `com_ui_fork_open_menu`. Hover-button style (hidden at `md:opacity-0`, revealed on group-hover).
  - **Fork options popover** (`Fork.tsx` lines 356–443): 240 px wide rounded card with three fork mode buttons plus two checkboxes:
    - **"Visible messages only" (`ForkOptions.DIRECT_PATH`)**: `GitCommit` icon rotated 90°; copies only the direct path of messages leading to the selected message.
    - **"Include related branches" (`ForkOptions.INCLUDE_BRANCHES`)**: `GitBranchPlus` icon rotated 180°; includes all sibling branches up to the selected message.
    - **"Include all to/from here" (`ForkOptions.TARGET_LEVEL`)**: `ListTree` icon; includes all messages at the same depth level. Labelled "(default)" in the hover card.
    - **"Split at target" checkbox** (`id="split-target-checkbox"`): when checked, the fork starts at the selected message rather than including it.
    - **"Remember" checkbox** (`id="remember-checkbox"`): when checked, saves the chosen fork mode as the global default and bypasses the popover on future forks.

- **Functional behavior:**
  - FR-1. If `rememberGlobal` is true (from `store.rememberDefaultFork`), clicking the Fork button immediately executes a fork using the stored `forkSetting`, skipping the popover.
  - FR-2. Otherwise, clicking the Fork button toggles the options popover.
  - FR-3. Selecting a fork option calls `forkConvo.mutate({ messageId, conversationId, option, splitAtTarget, latestMessageId })`.
  - FR-4. On success, the user is navigated to the new forked conversation (`navigateToConvo(data.conversation)`) and a success toast (`com_ui_fork_success`) is shown.
  - FR-5. An info toast (`com_ui_fork_processing`) is shown while the mutation is in flight.
  - FR-6. On rate-limit error (HTTP 429), an error toast (`com_ui_fork_error_rate_limit`) is shown. Other errors show `com_ui_fork_error`.

- **States & edge cases:**
  - Assistants endpoint: Fork button is not rendered at all.
  - During submission: Fork button is visible but the hover buttons group has `md:opacity-0` on non-last messages; the user must hover to reveal it.
  - Remember checked during session: a toast informs the user (`com_ui_fork_remember_checked`).

- **Acceptance criteria:**
  - AC-1. Given a conversation with messages, when the user hovers a non-Assistants message and clicks Fork, then a popover with three fork-mode options appears.
  - AC-2. Given the user selects a fork mode, when the fork succeeds, then the browser navigates to the new forked conversation and a success toast is shown.
  - AC-3. Given the "Remember" checkbox is checked and a fork mode selected, when the user later clicks Fork on any message, then the fork executes immediately without showing the popover.
  - AC-4. Given a rate limit error, when forking fails, then the error toast `com_ui_fork_error_rate_limit` is shown and the user remains on the current conversation.

---

### Message Feedback (Thumbs Up / Thumbs Down)

- **Purpose:** Capture qualitative user feedback on assistant responses for moderation or improvement purposes.

- **Preconditions / access:** `handleFeedback` is non-null AND `isCreatedByUser` is false (feedback is only on assistant messages, `HoverButtons.tsx` lines 247–249).

- **UI elements:**
  - **Thumbs Up button** (`Feedback.tsx` line 149): `ThumbUpIcon` (19 px), `title` → `com_ui_feedback_positive`, `aria-pressed` reflects current rating.
  - **Thumbs Down button** (`Feedback.tsx` line 181): `ThumbDownIcon` (19 px), `title` → `com_ui_feedback_negative`, `aria-pressed` reflects current rating.
  - **Tag popover** (Ariakit `Popover`, `gutter={8}`): appears on first click of either button when no rating is yet recorded. Contains a list of `FeedbackOptionButton` items with icons and localised labels from `getTagsForRating('thumbsUp')` / `getTagsForRating('thumbsDown')`.
  - **"More information" dialog** (`OGDialog`, `Feedback.tsx` line 316): shown when the "Other" tag is selected. Contains a `textarea` (max 500 chars, `placeholder` → `com_ui_feedback_placeholder`) plus "Delete" (`variant="destructive"`) and "Save" (`variant="submit"`, disabled until text is non-empty) buttons.
  - **Single consolidated button** (`renderSingleFeedbackButton`): once a rating is recorded, both thumbs buttons collapse into a single active button showing only the selected icon.

- **Functional behavior:**
  - FR-1. First click on Thumbs Up (no prior rating): the tag popover opens for positive tags.
  - FR-2. First click on Thumbs Down (no prior rating): the tag popover opens for negative tags.
  - FR-3. Selecting a non-"other" tag from the popover: calls `onFeedback({ rating, tag })`, closes popover, persists feedback via `handleFeedback`. The two-button group collapses to a single active button.
  - FR-4. Selecting the "other" tag: records the rating and opens the text dialog for additional context.
  - FR-5. Clicking Thumbs Up again when already rated thumbs-up: clears the feedback (`onFeedback(undefined)`).
  - FR-6. Clicking Thumbs Down again when already rated thumbs-down: opens the text dialog (re-edits the negative feedback).
  - FR-7. In the dialog, "Save" is disabled until the free-text field is non-empty (for "other" tag). "Delete" clears the rating entirely.
  - FR-8. Feedback state (`TFeedback` object with `rating`, `tag`, optional `text`) is propagated upward and stored per message.

- **States & edge cases:**
  - Hover buttons hidden until hover: on non-last messages the entire hover row is `md:opacity-0`; the feedback buttons follow the same visibility rules.
  - `initialFeedback` prop synced via `useEffect`: if the server returns an updated feedback state, the local state is updated.
  - Dialog save with empty text: button is disabled; feedback is not propagated.
  - Rapid toggling: each click synchronously updates local state and fires `handleFeedback`; race conditions are unlikely but the last call wins.

- **Acceptance criteria:**
  - AC-1. Given an assistant message with no prior feedback, when the user clicks Thumbs Up, then a tag selection popover appears with positive tag options.
  - AC-2. Given the user selects a tag from the popover, when the popover closes, then a single active Thumbs Up button is shown and the feedback is recorded.
  - AC-3. Given the active Thumbs Up button is shown, when the user clicks it again, then the feedback is cleared and both Thumbs Up/Down buttons reappear.
  - AC-4. Given the user selects the "Other" tag from the Thumbs Down popover, when the dialog opens, then the Save button is disabled until the user types in the text area.
  - AC-5. Given the user clicks "Delete" in the feedback dialog, when it closes, then the rating is cleared and the two-button row is restored.

---

### Markdown & Code Block Rendering

- **Purpose:** Render AI responses with rich formatting: headings, lists, tables, inline code, fenced code blocks with syntax highlighting, LaTeX math, and more.

- **Preconditions / access:** Any assistant message. User messages are displayed as plain text (they use `MarkdownLite` or a simpler renderer; verify: check `MessageContent.tsx` for user-message rendering path).

- **UI elements:**
  - **Markdown component** (`Markdown.tsx`): `ReactMarkdown` with remark/rehype plugin stack:
    - `remark-gfm`: GitHub Flavored Markdown (tables, task lists, strikethrough, autolinks).
    - `remark-math` + `rehype-katex`: LaTeX math (`$...$` inline disabled via `singleDollarTextMath: false`; `$$...$$` display math enabled).
    - `remark-supersub`: superscript/subscript.
    - `remark-directive` + `artifactPlugin`: artifact blocks.
    - `mcpUIResourcePlugin`: MCP UI resource cards/carousels.
    - `unicodeCitation`: citation rendering.
    - `rehype-highlight`: syntax highlighting with language auto-detection (`detect: true`), using a subset of highlight.js languages.
  - **CodeBlock** (`CodeBlock.tsx`): rendered by the `code` component override. Wraps each fenced code block in a `div.rounded-md.border.border-border.bg-card`.
  - **CodeBar** (`CodeBar.tsx`): top bar of each code block showing language name, optional `LangIcon`, a "Copy code" button, and optionally a "Run" button.
  - **Copy code button** (`CopyButton`, `CodeBar.tsx` line 28): `label` → `com_ui_copy_code`. Uses `useCopyCode(codeRef)` to write the code element's `textContent` to the clipboard.
  - **FloatingCodeBar** (`FloatingCodeBar.tsx`): a sticky duplicate of CodeBar that floats at the top of the code block when the user scrolls the block out of view while hovering (`showFloating = isHovered && !isCodeBarVisible` from `CodeBlock.tsx` line 99).
  - **Thinking/initializing placeholder**: when `content === ''`, a `<span className="result-thinking">` pulsing animation is shown.
  - **MarkdownErrorBoundary** (`MarkdownErrorBoundary.tsx`): wraps the renderer; on error, falls back to raw text display.

- **Functional behavior:**
  - FR-1. Fenced code blocks are rendered with syntax highlighting. The language is shown in the CodeBar.
  - FR-2. Clicking "Copy code" in the CodeBar copies the raw code text to the clipboard. The `isCopied` state briefly shows a confirmation icon.
  - FR-3. When the user hovers a code block and scrolls until the CodeBar is off-screen, a floating duplicate CodeBar appears fixed to the top of the block.
  - FR-4. LaTeX math (double-dollar `$$...$$`) is rendered by KaTeX when `LaTeXParsing` is enabled (user setting, default: **true**, persisted in localStorage as `'LaTeXParsing'` — confirmed in `store/settings.ts:45`).
  - FR-5. When code execution is enabled (`allowExecution === true`) for a block, a `RunCode` button appears in the CodeBar. Execution results appear in a bordered output section below the code, with a `ResultSwitcher` for multiple runs.
  - FR-6. Artifacts (`artifactPlugin`) are rendered inline when the assistant generates artifact directives; clicking the artifact opens the Artifacts side panel.
  - FR-7. On render error, `MarkdownErrorBoundary` displays the raw content as plain text and logs the error.

- **States & edge cases:**
  - Code block without language tag: `rehype-highlight` attempts auto-detection.
  - Very long code block: the inner `div` is `overflow-y-auto`; the block scrolls independently.
  - LaTeX with syntax errors: KaTeX may render an error span inline; the rest of the message continues to render.
  - Streaming mid-code-block: markdown parser may show incomplete code before the closing triple-backtick arrives. The partial block is rendered as best-effort.

- **Acceptance criteria:**
  - AC-1. Given an assistant message containing a fenced code block labelled `python`, when rendered, then the block shows a "python" label and syntax-highlighted code.
  - AC-2. Given a code block is rendered, when the user clicks "Copy code", then the clipboard contains the raw code text.
  - AC-3. Given a code block whose CodeBar is scrolled out of view while the user hovers the block, when the IntersectionObserver fires, then the FloatingCodeBar appears at the top of the block.
  - AC-4. Given an assistant message containing a GFM table, when rendered, then the table appears with proper rows and columns (not as raw Markdown syntax).
  - AC-5. Given LaTeX is enabled and the response contains `$$E=mc^2$$`, when rendered, then a KaTeX-formatted equation is displayed.

---

### Auto-Scroll Behavior

- **Purpose:** Keep the user's view at the bottom of the conversation during streaming; resurface a "scroll to bottom" control when the user scrolls up.

- **Preconditions / access:** `MessagesView` is rendered (i.e., at least one message exists or is being generated).

- **UI elements:**
  - **Scroll container** (`MessagesView.tsx` lines 42–59): `div` with `overflow-y: auto`, `height: 100%`. Observed by `debouncedHandleScroll`.
  - **`messagesEndRef` sentinel** (`MessagesView.tsx` line 76): `id="messages-end"`, a 0-height div at the bottom of the messages list used as an `IntersectionObserver` target.
  - **ScrollToBottom button** (`ScrollToBottom.tsx`): `ChevronDown` icon (16×16 px), `aria-label` → `com_ui_scroll_to_bottom`. Positioned absolutely at `bottom-5`, `right` aligned within `md:max-w-3xl xl:max-w-4xl`. Shown/hidden via `CSSTransition` (`scroll-animation` classNames, 300 ms enter / 250 ms exit). Only rendered when `showScrollButton && scrollButtonPreference` are both true.
  - **`scrollButtonPreference` setting** (`store.showScrollButton`): user preference controlling whether the button is displayed at all.

- **Functional behavior:**
  - FR-1. **During streaming:** `useMessageScrolling` calls `scrollToBottom()` on every `messagesTree` update when `isSubmitting && abortScroll !== true`. The scroll function is **throttled** at 145 ms via `lodash/throttle` (not debounced) inside `useScrollToRef.ts`.
  - FR-2. **User scrolls up during streaming:** A wheel event on any `Message` component (`onWheel` handler, `Message.tsx:17` / `MessageParts.tsx:103`) triggers `handleScroll` in `useMessageHelpers.tsx:84–99` which calls `setAbortScroll(true)`, stopping auto-scroll. (Note: the outer scroll container's `onScroll` handler only recalculates `showScrollButton` and does not set `abortScroll`.) The `ScrollToBottom` button appears when the sentinel leaves the viewport (IntersectionObserver threshold 0.85, debounce 150 ms).
  - FR-3. **Clicking ScrollToBottom:** Calls `handleSmoothToRef` which scrolls smoothly to `messagesEndRef` and calls `setAbortScroll(false)`, re-enabling auto-scroll.
  - FR-4. **Conversation navigation:** When `autoScroll` is enabled and `conversationId` changes (not `NEW_CONVO`), `scrollToBottom()` is called once to jump to the bottom of the loaded conversation.
  - FR-5. **Scroll button preference:** If `scrollButtonPreference` is false, the `ScrollToBottom` button is never rendered regardless of scroll position.

- **States & edge cases:**
  - Very fast streaming: multiple `scrollToBottom()` calls are coalesced by throttling (145 ms) to avoid jank.
  - Landing page: `MessagesView` is not rendered; no scroll logic applies.
  - Short conversation fitting on screen: `messagesEndRef` is always in viewport; `showScrollButton` stays false.

- **Acceptance criteria:**
  - AC-1. Given a response is streaming, when the user is at the bottom of the view, then the viewport automatically scrolls to show new tokens as they arrive.
  - AC-2. Given a response is streaming, when the user scrolls up, then auto-scroll stops and the `ChevronDown` scroll-to-bottom button appears.
  - AC-3. Given the scroll-to-bottom button is visible, when the user clicks it, then the viewport scrolls smoothly to the latest message and auto-scroll resumes.
  - AC-4. Given the user navigates to an existing conversation with many messages, when the page loads, then the viewport is positioned at the bottom of the conversation.
  - AC-5. Given the user has disabled the scroll button in settings, when they scroll up during streaming, then the scroll-to-bottom button does not appear.

---

### Conversation Auto-Titling

- **Purpose:** Automatically assign a descriptive title to a new conversation after the first exchange, so the conversation is identifiable in the sidebar history.

- **Preconditions / access:** `titleConvo: true` in the NuFi server config. The conversation must have at least one completed exchange. The title generation runs server-side (API route `/conversation/title`, called via `dataService.genTitle`).

- **UI elements:**
  - **Conversation title in sidebar**: updated in-place as soon as the title query resolves. The document (`<title>`) is also updated if the conversation is currently active (`window.location.pathname.includes(conversationId)`, `queries.ts` line 121).
  - **No visible spinner or placeholder** in the title area during generation (title update is silent, background).

- **Functional behavior:**
  - FR-1. After a new conversation's first response completes, the `conversationId` is added to a `titleQueue`.
  - FR-2. Once the conversation is "ready" (stream finished), `setReadyToFetch` moves the ID into the React Query batch (`useQueries`, `queries.ts` lines 95–106), calling `genTitle` for each pending conversation.
  - FR-3. On success, the title is written into the conversation cache (`queryClient.setQueryData`) and propagated to all query lists via `updateConvoInAllQueries`. The sidebar updates without a full re-fetch.
  - FR-4. If `genTitle` returns an error, the conversation is marked as processed and no retry is attempted (`staleTime: Infinity`, `retry: false`). The conversation retains its default title (typically the first few words of the user's message, or "New Chat"; verify: default title logic is server-side).
  - FR-5. The document `<title>` is updated to the generated title only for the currently active conversation.

- **States & edge cases:**
  - Very long first message: the generated title is a server-side summarisation; length is controlled by the model and any system prompt. Client receives a plain string.
  - Network error during title generation: silently fails; no retry; no user-visible error.
  - Multiple tabs: title update in one tab does not propagate to other tabs (no cross-tab broadcast at the client layer).
  - Resumed conversation (navigating back to existing): title is already set; no new `genTitle` call is made because the ID is not in the queue.

- **Acceptance criteria:**
  - AC-1. Given a new conversation is started and the first assistant response completes, when a moment passes, then the conversation in the sidebar changes from its placeholder title to a descriptive auto-generated title.
  - AC-2. Given the auto-title resolves successfully, when the user is viewing that conversation, then the browser tab title also updates to the generated title.
  - AC-3. Given the title API call fails (e.g., network error), then no error is shown to the user and the sidebar title remains unchanged (no infinite retry).
  - AC-4. Given the user navigates away from the conversation while the title is being generated, when the title resolves, then only the sidebar entry is updated (the document title is not changed for the non-active conversation).
