## Conversation Management & Sidebar

This section specifies the features that let users create, find, navigate, organize, and export conversations in NuFi Chat. All features documented here apply to the NuFi Chat deployment in which the following configuration flags are enabled: `sidePanel`, `bookmarks`, `multiConvo`, `temporaryChat`, and `sharedLinksEnabled`. Meilisearch-backed search (`search.enabled`) is enabled when the Meilisearch service is running.

---

### Conversation List & Navigation (Sidebar)

**Purpose:** Display the user's saved conversation history in a persistent left sidebar and allow navigation between conversations.

**Preconditions / access:** User is authenticated. Sidebar is in its expanded state (`sidebarExpanded = true` in local storage).

**UI elements:**
- Left sidebar panel labeled `"Chat History"` (`com_ui_chat_history`) rendered as `role="region"`.
- Virtualized scrollable list (`aria-label="Conversations"`, `containerRole="rowgroup"`, built with `react-virtualized`).
- Collapsible **"Chats"** section header (`com_ui_chats`) with a `ChevronDown` icon that rotates when expanded; collapse state persisted in local storage key `chatsExpanded`.
- Date-group labels: **Today**, **Yesterday**, **Previous 7 Days**, **Previous 30 Days**, then month names (e.g., **January**), then bare years (e.g., `2024`). Each group is an `<h2>` with `aria-label` announcing the date section.
- Individual conversation rows (`data-testid="convo-item"`, `role="button"`) showing endpoint icon (or a spinning loader when generation is active) and the conversation title.
- Active conversation highlighted with a left-side primary-color bar (`before:bg-primary`) and `bg-surface-active-alt` background; `aria-current="page"` set on the inner link.
- On hover or focus, an `Ellipsis` (three-dot) options button (`aria-label="com_nav_convo_menu_options"`) appears on the right.
- A **Favorites** section rendered above the Chats header when favorites exist or when the Agent Marketplace is enabled (hidden during search).
- NavToggle button on the sidebar edge (two animated bars, `aria-controls="chat-history-nav"`) that collapses/expands the sidebar.

**Functional behavior:**
1. FR-1: On initial load the sidebar fetches conversations via `useConversationsInfiniteQuery`, grouped and sorted by `updatedAt` descending within each date bucket.
2. FR-2: Conversations are grouped into the date buckets listed in the `dateKeys` map (`com_ui_date_today`, `com_ui_date_yesterday`, `com_ui_date_previous_7_days`, `com_ui_date_previous_30_days`, then months, then years).
3. FR-3: As the user scrolls to within 8 rows of the bottom of the rendered list, `loadMoreConversations` is called (throttled to 300 ms) and an additional page is fetched. A loading spinner (`com_ui_loading`) is appended to the list while fetching.
4. FR-4: Clicking a conversation row navigates to `/c/{conversationId}` and updates `document.title` to the conversation title. On mobile (`max-width: 768px`) the sidebar is auto-collapsed after navigation.
5. FR-5: Pressing `Ctrl`/`Cmd` + click on a conversation row opens it in a new browser tab.
6. FR-6: The active conversation row is determined by matching the URL param `conversationId`; if the URL is `/c/new`, the conversation at Recoil index 0 (`activeConvos[0]` from `allConversationsSelector`) is highlighted instead. This is the first entry in the current Recoil conversation slot, not necessarily the most recently visited conversation from browser navigation history. If no conversation has been opened in the current session the highlighted row may be absent.
7. FR-7: Collapsing the Chats header hides all date groups and conversation rows but leaves the Favorites section visible.
8. FR-8: Each conversation row renders a spinning SVG icon (`aria-label="com_ui_generating"`) instead of the endpoint icon while an AI generation job is active for that conversation (`activeJobIds` set).
9. FR-9: The NavToggle button toggles `sidebarExpanded` in local storage. The NavToggle button itself slides by `translate-x-[260px]` when the sidebar is visible. On mobile, the chat area shifts with `translateX(min(85vw, 380px))` to accommodate the sidebar overlay; on desktop the sidebar is always in the layout flow and no translate animation is applied to the chat area.
10. FR-10: On mobile the sidebar overlays the chat area; on desktop it persists side-by-side.

**States & edge cases:**
- **Empty history:** No date groups or conversation rows are rendered; only the Chats header and (if applicable) Favorites/Marketplace items appear.
- **All conversations in one group:** Only one date group header is shown.
- **Search active:** The Favorites section is hidden; conversation list is replaced by search results (see Search section).
- **Sidebar collapsed:** NavToggle is visible at `translate-x-0`; clicking it re-expands the sidebar.
- **Network error on load:** (verify: error state rendering—the query client may show stale data or a blank list).

**Acceptance criteria:**
- AC-1: Given an authenticated user with 10 saved conversations, when the sidebar loads, then all 10 conversations appear grouped under appropriate date labels sorted newest-first within each group.
- AC-2: Given the list is scrolled to within 8 rows of the end and `hasNextPage` is true, when the scroll event fires, then an additional page of conversations is fetched and appended without a full re-render of existing rows.
- AC-3: Given the user clicks a conversation row that is not the current conversation, when the click is processed, then the URL changes to `/c/{conversationId}` and that row receives the active highlight style.
- AC-4: Given the user holds `Ctrl` (Windows/Linux) or `Cmd` (Mac) and clicks a row, when the click fires, then the conversation opens in a new browser tab and the sidebar closes on mobile.
- AC-5: Given the Chats header collapse button is clicked, when toggled, then all conversation rows disappear and the collapse state is persisted across page reload.

---

### New Chat

**Purpose:** Start a fresh conversation and clear any active message context.

**Preconditions / access:** User is authenticated. Button is visible in the sidebar header area.

**UI elements:**
- Icon button (`data-testid="new-chat-button"`, `aria-label="com_ui_new_chat"`) rendered with `NewChatIcon`, styled `size-9 rounded-xl`; hidden on mobile (`max-md:hidden`).
- Tooltip showing `com_ui_new_chat` on hover.
- On mobile the `NewChat` button is hidden via `max-md:hidden`. There is no separate mobile-only "New Chat" entry. Mobile users open the sidebar via the `OpenSidebar` button in the chat header (`md:hidden`) and then interact with the sidebar's existing navigation; starting a new conversation on mobile is done via URL navigation to `/c/new`.

**Functional behavior:**
1. FR-1: Clicking the New Chat button calls `clearMessagesCache`, invalidates the messages query, calls `newConversation()`, which resets conversation state, and navigates to `/c/new`.
2. FR-2: Pressing `Ctrl`/`Cmd` + click opens a new browser tab at `/c/new` without changing the current tab.
3. FR-3: The new conversation is not committed to the database until the first message is sent.

**States & edge cases:**
- **Already on `/c/new`:** Clicking New Chat again is harmless; state is reset but no duplicate navigation occurs.
- **Generation in progress:** The button remains clickable; clicking it starts a new conversation context but does not abort the in-flight generation of the previous conversation.

**Acceptance criteria:**
- AC-1: Given any conversation is open, when the user clicks "New Chat", then the URL changes to `/c/new` and the chat area is cleared.
- AC-2: Given the user holds `Ctrl`/`Cmd` and clicks "New Chat", when the click fires, then a new tab opens at `/c/new` and the current tab is unchanged.

---

### Search Conversations

**Purpose:** Find conversations by keyword across their title and message content using Meilisearch.

**Preconditions / access:** `search.enabled` is `true` (Meilisearch service is running). User is authenticated. Search bar is rendered in the sidebar.

**UI elements:**
- Search input (`aria-label="com_nav_search_placeholder"`, placeholder `com_nav_search_placeholder`) inside a container with a `Search` icon (left) and a clear (`X`) button (right, `aria-label="com_ui_clear_search"`).
- The clear button is hidden (`opacity-0`) when the input is empty.
- Loading spinner shown in the conversation list area while `isSearchLoading` is true.

**Functional behavior:**
1. FR-1: As the user types, the query is stored immediately in Recoil state (`search.query`), and a debounced copy (`search.debouncedQuery`) is set after 500 ms with `isTyping` cleared.
2. FR-2: Once `debouncedQuery` is non-empty, `useConversationsInfiniteQuery` is called with `search: debouncedQuery`, replacing the normal conversation list.
3. FR-3: While typing (before the debounce fires), the list shows a loading spinner (`isSearchLoading = true`).
4. FR-4: The URL changes to `/search` as soon as any non-empty query is entered.
5. FR-5: Clicking the clear (`X`) button or pressing `Backspace` when the input is empty clears `search.query` and `search.debouncedQuery`, hides search results, navigates back to `/c/new` if currently on `/search`, and refocuses the input.
6. FR-6: The Favorites section is hidden while a search query is active.
7. FR-7: Search results are rendered in the same virtualized conversation list with the same date-group structure. Within results, conversations are still grouped by date of `updatedAt`.

**States & edge cases:**
- **No results:** The conversation list is empty; no date groups are rendered. Only the Chats header remains visible. No "No results" empty-state message component is rendered — the list area is simply blank below the header.
- **Meilisearch unavailable:** Search input is hidden (`search.enabled = false`); normal pagination-based list is shown.
- **Single character query:** Debounce still applies; Meilisearch performs a prefix search.
- **Special characters:** The query is passed as a raw string to Meilisearch (no `encodeURIComponent` on the main sidebar search path). The sidebar search URL itself carries no query parameter to encode — it only navigates to `/search`. The archived-chats sub-query does encode its parameter. React's JSX rendering prevents client-side XSS; server-side sanitization handles the query value.

**Acceptance criteria:**
- AC-1: Given the user types "invoice" into the search bar, when 500 ms elapses, then the conversation list updates to show only conversations matching "invoice" and the URL is `/search`.
- AC-2: Given search results are displayed, when the user clicks the `X` clear button, then the query is cleared, the normal conversation list is restored, and focus returns to the search input.
- AC-3: Given a query that matches no conversations, when results load, then the conversation list is empty with no error message shown in the list area.

---

### Rename Conversation

**Purpose:** Allow the user to give a conversation a custom title.

**Preconditions / access:** User is authenticated and owns the conversation.

**UI elements:**
- **Rename** menu item (label `com_ui_rename`, icon `Pen`) in the conversation's three-dot `ConvoOptions` dropdown.
- On desktop, double-clicking the conversation title text also triggers rename (disabled on small screens).
- Inline rename form (`role="form"`, `aria-label="com_ui_rename_conversation"`) overlays the conversation row: a single text input (`aria-label="com_ui_new_conversation_title"`, `maxLength={100}`) pre-filled with the current title, a cancel button (`X` icon, `aria-label="com_ui_cancel"`), and a save button (`Check` icon, `aria-label="com_ui_save"`).

**Functional behavior:**
1. FR-1: When rename mode activates, the input is auto-focused and existing text is selected.
2. FR-2: Pressing `Enter` submits the new title; pressing `Escape` cancels without saving.
3. FR-3: On submission, `useUpdateConversationMutation` is called with `{ conversationId, title: newTitle.trim() || 'Untitled' }`. The fallback label is `com_ui_untitled`.
4. FR-4: If the submitted title is identical to the current title, the rename request is skipped and the form closes.
5. FR-5: On API success the UI updates inline. On failure a toast notification appears with `com_ui_rename_failed` and the original title is restored in the input.
6. FR-6: The title field is capped at 100 characters (enforced by `maxLength`).

**States & edge cases:**
- **Empty submission:** The title is set to `com_ui_untitled` (i.e., trimming produces an empty string).
- **Rename while generating:** Rename can be initiated; it does not interrupt the generation.
- **Network error:** Error toast shown; input reverts to original title and form closes.

**Acceptance criteria:**
- AC-1: Given rename mode is active, when the user types a new title and presses `Enter`, then the conversation title updates in the sidebar and the rename form closes.
- AC-2: Given rename mode is active, when the user presses `Escape`, then the form closes and the title is unchanged.
- AC-3: Given the user submits an empty string (all spaces), when saved, then the title is set to "Untitled" (localized `com_ui_untitled`).
- AC-4: Given the API call fails, when the error is returned, then a toast with `com_ui_rename_failed` appears and the sidebar shows the original title.

---

### Delete Conversation

**Purpose:** Permanently remove a conversation and all its messages from the server.

**Preconditions / access:** User is authenticated and owns the conversation.

**UI elements:**
- **Delete** menu item (label `com_ui_delete`, icon `Trash`) in the `ConvoOptions` dropdown (`ariaHasPopup="dialog"`, `ariaControls="delete-conversation-dialog"`).
- Confirmation dialog (`OGDialog`): title `com_ui_delete_conversation`, body showing `com_ui_delete_confirm_strong` with the conversation title bolded, a **Cancel** button (`variant="outline"`, `aria-label="cancel"`), and a **Delete** button (`variant="destructive"`).
- **Shift-key shortcut:** When the **currently active** (highlighted) conversation row has the keyboard `Shift` key held, the three-dot menu for that row is replaced by direct **Archive** and **Delete** icon buttons; clicking Delete in this mode skips the dialog and deletes immediately. The shortcut only activates on the currently active conversation row (`isActiveConvo === true`), not on any other hovered row.

**Functional behavior:**
1. FR-1: Clicking **Delete** in the three-dot menu opens the confirmation dialog without performing any action.
2. FR-2: In the confirmation dialog, clicking **Delete** calls `useDeleteConversationMutation` with `{ conversationId, thread_id, endpoint, source: 'button' }`.
3. FR-3: On success: dialog closes, the conversation is removed from the list, a success toast (`com_ui_convo_delete_success`) is shown, and if the deleted conversation was the active one the user is navigated to `/c/new`.
4. FR-4: On error: an error toast (`com_ui_convo_delete_error`) is shown.
5. FR-5: The Shift shortcut instant-delete path (FR in `handleInstantDelete`) also calls `deleteMutation.mutate` but skips the dialog.
6. FR-6: The Delete button in the dialog shows a `Spinner` while `deleteMutation.isLoading` is true and is `disabled`.

**States & edge cases:**
- **Deleting the only conversation:** After deletion the list is empty; user lands on `/c/new`.
- **Deleting a conversation currently being generated:** Deletion proceeds; the in-flight request may still complete on the server side (requires manual verification on the running product: whether the server aborts the SSE stream for the deleted conversation).
- **Dialog dismissed via Cancel or backdrop:** No deletion occurs.

**Acceptance criteria:**
- AC-1: Given the user selects "Delete" from the three-dot menu, when the dialog appears, then no deletion has occurred and the conversation remains in the list.
- AC-2: Given the confirmation dialog is open and the user clicks the "Delete" button, when the API call succeeds, then the conversation disappears from the list and a success toast is displayed.
- AC-3: Given the currently viewed conversation is deleted, when deletion succeeds, then the browser navigates to `/c/new`.
- AC-4: Given the user presses Cancel in the dialog, when dismissed, then the conversation remains and the list is unchanged.

---

### Archive / Unarchive Conversation

**Purpose:** Move a conversation out of the active list without permanently deleting it; retrieve it later.

**Preconditions / access:** User is authenticated and owns the conversation.

**UI elements:**
- **Archive** menu item (label `com_ui_archive`, icon `Archive`) in the `ConvoOptions` dropdown.
- Shift-key shortcut: when `Shift` is held on the active conversation, an **Archive** icon button is shown directly (same as the Delete shortcut path).
- **Settings > General > Archived Chats** section (label `com_nav_archived_chats`) with a **Manage** button that opens the archived chats dialog.
- Archived chats dialog: `DataTable` with columns **Name** (sortable), **Created At** (sortable), and **Actions** (Unarchive `ArchiveRestore` icon, Delete `TrashIcon` icon). A search/filter input is available in the table header.
- Screen-reader live region announces `com_ui_convo_archived` after archiving.

**Functional behavior:**
1. FR-1: Clicking **Archive** calls `useArchiveConvoMutation` with `{ conversationId, isArchived: true }`.
2. FR-2: On success: the conversation is removed from the active sidebar list; if it was the active conversation the user is navigated to `/c/new`; a screen-reader announcement `com_ui_convo_archived` fires for 10 seconds; the options popover closes.
3. FR-3: On error: a toast (`com_ui_archive_error`) is shown.
4. FR-4: In the Archived Chats table, clicking the `ArchiveRestore` icon calls `useArchiveConvoMutation` with `{ conversationId, isArchived: false }`, returning the conversation to the active list.
5. FR-5: The archived chats table supports sorting by Name and Created At (ascending/descending); the default sort is `createdAt` descending.
6. FR-6: Infinite scrolling is used within the archived chats table (`fetchNextPage` when `hasNextPage`).
7. FR-7: Each row's **Name/title cell** contains an inline `ExternalLink` icon; clicking the conversation title (or the icon) opens it in a new browser tab. The `ExternalLink` icon is embedded within the title cell, not a standalone button in a separate Actions column. The Actions column contains only the Unarchive (`ArchiveRestore`) and Delete (`TrashIcon`) buttons.

**States & edge cases:**
- **No archived conversations:** Table is empty; only the column headers are visible. No custom empty-state message component is rendered.
- **Archive of the only active conversation:** Active list becomes empty; user navigates to `/c/new`.
- **Unarchive restores conversation:** Conversation reappears in the active sidebar under the correct date group on the next query refresh.

**Acceptance criteria:**
- AC-1: Given the user selects "Archive" from the three-dot menu, when the API succeeds, then the conversation disappears from the active sidebar list and appears in the Archived Chats table.
- AC-2: Given an archived conversation is displayed in the Archived Chats table, when the user clicks the Unarchive icon, then the conversation is removed from the table and reappears in the active sidebar.
- AC-3: Given the archived conversation was the currently viewed one, when archived, then the URL changes to `/c/new`.

---

### Bookmarks / Tags

**Purpose:** Let users create named bookmark tags, assign them to conversations, and filter the conversation list by one or more tags.

**Preconditions / access:** `bookmarks` feature enabled (`PermissionTypes.BOOKMARKS`, `Permissions.USE` granted). User is authenticated with an active (non-new, non-search) conversation.

**UI elements:**
- **BookmarkNav** dropdown in the sidebar toolbar: a `BookmarkIcon`/`BookmarkFilledIcon` toggle button (`data-testid="bookmark-menu"`, `aria-label="com_ui_bookmarks"` or `com_ui_bookmarks_count_selected` when tags are selected). Tooltip shows current selection or `com_ui_bookmarks`.
- BookmarkNav dropdown items: **Clear All** (icon `CrossCircledIcon`, label `com_ui_clear_all`), then one item per existing tag that has at least one conversation (`count > 0`). If no tags exist, a disabled item `com_ui_no_bookmarks` is shown.
- **BookmarkMenu** in the chat header (in-conversation): a `BookmarkIcon`/`BookmarkFilledIcon` button (`data-testid="bookmark-menu"`, `aria-label="com_ui_bookmarks_add"` or `com_ui_bookmarks_count_selected`). Visible only when a real conversation is open and the conversation is not temporary (`expiredAt` must be null).
- BookmarkMenu dropdown: **New Bookmark** item (label `com_ui_bookmarks_new`, icon `BookmarkPlusIcon`), then all existing bookmark tags each shown as toggleable items.
- **BookmarkEditDialog**: titled `com_ui_bookmarks_new` (create) or `com_ui_bookmarks_edit` (edit). Fields: **Title** input (`id="bookmark-tag"`, max 128 characters, required), **Description** textarea (`id="bookmark-description"`, max 1048 characters), optional **"Add to conversation"** checkbox (`com_ui_bookmarks_add_to_conversation`, shown only when `conversationId` is provided). A **Save** button submits the form.
- **Edit** (`EditBookmarkButton`) and **Delete** (`DeleteBookmarkButton`) buttons on bookmark management views (verify: exact location—sidebar tag management UI).

**Functional behavior:**
1. FR-1: Clicking a tag in the BookmarkNav dropdown toggles it in the active filter set; multiple tags can be selected simultaneously (OR filter logic is applied at the API query level via `tags` parameter).
2. FR-2: When one or more tags are selected, `useConversationsInfiniteQuery` is called with `{ tags: [...selectedTags] }`; only conversations matching any selected tag are shown.
3. FR-3: Clicking **Clear All** in BookmarkNav removes all selected tags and restores the unfiltered conversation list.
4. FR-4: Clicking **New Bookmark** in the BookmarkMenu opens `BookmarkEditDialog` in create mode.
5. FR-5: Submitting the BookmarkEditDialog calls `useConversationTagMutation`; on success a toast `com_ui_bookmarks_create_success` is shown; if **Add to conversation** is checked the new tag is also assigned to the current conversation.
6. FR-6: Clicking an existing tag in the BookmarkMenu calls `useTagConversationMutation` to toggle that tag on the current conversation; if already assigned it is removed, if not assigned it is added.
7. FR-7: Tag names must be unique globally; submitting a duplicate name shows a warning toast `com_ui_bookmarks_create_exists` and the form is not submitted.
8. FR-8: Tags are shown with `BookmarkFilledIcon` when selected on a conversation and `BookmarkIcon` when not.

**States & edge cases:**
- **No bookmarks exist:** BookmarkNav dropdown shows a disabled `com_ui_no_bookmarks` item.
- **Temporary conversation open:** BookmarkMenu is not rendered at all (`isTemporary === true` check).
- **New conversation (`/c/new`):** BookmarkMenu is not rendered (`isActiveConvo === false`).
- **Tag name > 128 characters:** Form shows a field error and submission is blocked.
- **Duplicate tag name:** Warning toast and no API call.

**Acceptance criteria:**
- AC-1: Given no bookmark tags exist, when the user opens the BookmarkNav dropdown, then a disabled "No bookmarks" item is shown.
- AC-2: Given two bookmark tags exist and the user selects both in BookmarkNav, when the conversation list reloads, then only conversations tagged with either tag are displayed.
- AC-3: Given the BookmarkEditDialog is open, when the user submits a tag name that already exists, then a warning toast appears and no new tag is created.
- AC-4: Given a conversation is open with no tags, when the user clicks an existing tag in BookmarkMenu, then that tag is assigned to the conversation and the BookmarkFilledIcon is shown for that tag.
- AC-5: Given a temporary chat is active, when the chat header is inspected, then the BookmarkMenu button is not present.

---

### Share Conversation (Public Link)

**Purpose:** Generate a publicly accessible, read-only link to a conversation that can be shared with anyone without an account.

**Preconditions / access:** `sharedLinksEnabled = true` in startup config. User is authenticated with a saved conversation open.

**UI elements:**
- **Share** menu item (label `com_ui_share`, icon `Share2`) in the conversation three-dot `ConvoOptions` dropdown (only shown when `startupConfig.sharedLinksEnabled` is true).
- **Export & Share** menu in the chat header (icon `Share2`, label `com_endpoint_export_share`), with dropdown items **Share** (`com_ui_share`) and **Export** (`com_endpoint_export`).
- **Share Link to Chat** dialog (`com_ui_share_link_to_chat`): shows either `com_ui_share_create_message` (no link yet) or `com_ui_share_update_message` (link exists). Contains the shareable URL in a read-only display box with a **Copy** button (`aria-label="com_ui_copy_link"`, `Copy` / `CopyCheck` icons), and when a link exists: a **Refresh link** button (`RotateCw` icon, `aria-label="com_ui_refresh_link"`), a **QR code** button (`QrCode` icon, toggles `com_ui_show_qr` / `com_ui_hide_qr`), and a **Delete** button (`Trash2` icon, `aria-label="com_ui_delete"`, opens nested delete confirmation dialog).
- **Create Link** button (`com_ui_create_link`, `variant="submit"`) shown when no link exists.
- QR code rendered via `QRCodeSVG` at 200 px, shown below the URL when toggled.
- **Settings > Data > Shared Links** section (`com_nav_shared_links`) with a **Manage** button listing all public links in a `DataTable` with Name, Date, and Actions columns; supports search/filter and infinite scroll.

**Functional behavior:**
1. FR-1: Opening the Share dialog calls `useGetSharedLinkQuery(conversationId)` to check for an existing share.
2. FR-2: If no link exists, a **Create Link** button is shown; clicking it calls `useCreateSharedLinkMutation({ conversationId, targetMessageId })` where `targetMessageId` is the latest message ID.
3. FR-3: On successful link creation the URL is displayed, the Copy button becomes enabled, and the Refresh/QR/Delete buttons appear.
4. FR-4: Clicking **Refresh link** calls `useUpdateSharedLinkMutation({ shareId })`, generating a new `shareId` and URL; a live-region announcement `com_ui_link_refreshed` fires.
5. FR-5: Clicking **Copy** writes the URL to the clipboard; the icon changes to `CopyCheck` briefly; a live-region announces `com_ui_link_copied`.
6. FR-6: Clicking **Delete** (the `Trash2` button) opens a nested confirmation dialog (`com_ui_delete_shared_link_heading`); confirming calls `useDeleteSharedLinkMutation({ shareId })`; on success a toast `com_ui_shared_link_delete_success` is shown and the dialog reverts to the "create" state.
7. FR-7: The shared link URL is built as `new URL('{apiBaseUrl}/share/{shareId}', window.location.origin)` via `buildShareLinkUrl`, where `apiBaseUrl` comes from `librechat-data-provider` (defaults to `/api`). In a standard `/api`-prefixed deployment this resolves to `{origin}/api/share/{shareId}`. The exact URL depends on how `apiBaseUrl` is configured.
8. FR-8: In Settings > Data > Shared Links, individual links can be deleted (single row delete) and there is no bulk-delete checkbox (`showCheckboxes={false}`). Bulk delete is partially implemented at the handler level (`handleDelete` accepts an array and shows `com_ui_shared_link_bulk_delete_success`) but is not exposed via the UI.
9. FR-9: The Share menu item in the three-dot dropdown is hidden entirely when `startupConfig.sharedLinksEnabled` is false.

**States & edge cases:**
- **Link creation API error:** A toast `com_ui_share_error` is shown; no link is stored.
- **Link deletion API error:** A toast `com_ui_share_delete_error` is shown; the existing link remains valid.
- **New or unsaved conversation:** The `ExportAndShareMenu` component checks `conversation.conversationId != null && conversationId !== 'new' && conversationId !== 'search'`; if any condition fails the menu is not rendered.
- **Shared link visited by unauthenticated user:** The shared link (`/share/{shareId}`) is accessible publicly without authentication. The route is defined outside the authenticated route tree (`AuthLayout`) and `ShareView` performs no auth check.

**Acceptance criteria:**
- AC-1: Given `sharedLinksEnabled` is true and no link exists, when the user opens the Share dialog, then a "Create Link" button is visible and no URL is displayed.
- AC-2: Given the user clicks "Create Link", when the API succeeds, then a URL is displayed and the Copy, Refresh, QR, and Delete buttons appear.
- AC-3: Given a shared link exists, when the user clicks Refresh, then a new URL is generated and the old URL becomes invalid (verify: server invalidation behavior).
- AC-4: Given a shared link exists, when the user clicks Delete and confirms, then the link is revoked and the dialog shows "Create Link" again.
- AC-5: Given `sharedLinksEnabled` is false, when the user opens the three-dot menu, then the "Share" menu item is not shown.

---

### Export Conversation

**Purpose:** Download the conversation in one of several file formats for offline use or archival.

**Preconditions / access:** A saved conversation is open (`conversationId` is non-null, not `"new"`, not `"search"`). The **Export & Share** menu is rendered.

**UI elements:**
- **Export** item (label `com_endpoint_export`, icon `Upload`) in the `ExportAndShareMenu` dropdown.
- **Export Conversation** dialog (`com_nav_export_conversation`): two-column form with:
  - **Filename** field (`id="filename"`, Label `com_nav_export_filename`, placeholder `com_nav_export_filename_placeholder`). Default is the conversation title passed through `filenamify`.
  - **Type** dropdown (`id="type"`, Label `com_nav_export_type`) with options:
    - `screenshot (.png)` (value `screenshot`)
    - `text (.txt)` (value `text`)
    - `markdown (.md)` (value `markdown`)
    - `json (.json)` (value `json`)
    - `csv (.csv)` (value `csv`)
    - `webpage (.html)` (value `webpage`)
  - **Include endpoint options** checkbox (`id="includeOptions"`, Label `com_nav_export_include_endpoint_options`); disabled and labeled `com_nav_not_supported` for `csv` and `screenshot` types.
  - **Export all message branches** checkbox (`id="exportBranches"`, Label `com_nav_export_all_message_branches`); disabled for types other than `json`, `csv`, and `webpage`; labeled `com_nav_not_supported` when disabled.
  - **Recursive** section (shown only when type is `json`): section header Label `com_nav_export_recursive_or_sequential`; checkbox (`id="recursive"`) with label text `com_nav_export_recursive`.
- **Export** submit button (`com_endpoint_export`, `variant="submit"`).

**Functional behavior:**
1. FR-1: Each time the dialog opens, defaults reset to: type = `screenshot`, includeOptions = `true`, exportBranches = `false`, recursive = `true`, filename = `filenamify(conversation.title ?? 'file')`.
2. FR-2: Changing the type adjusts checkbox availability: `exportBranches` is enabled for `json`, `csv`, and `webpage`; `includeOptions` is disabled for `csv` and `screenshot`; the `recursive` checkbox is shown only for `json`. When switching to a type that enables `exportBranches`, the value is also automatically set to `true`; switching to a type that does not support it sets the value to `false`.
3. FR-3: Clicking **Export** calls `useExportConversation({ conversation, filename: filenamify(filename), type, includeOptions, exportBranches, recursive })` which triggers a client-side download.
4. FR-4: The filename is sanitized via `filenamify` before download to remove OS-invalid characters.

**States & edge cases:**
- **Screenshot type selected:** `includeOptions` and `exportBranches` checkboxes are both disabled and show `com_nav_not_supported`.
- **CSV type selected:** `includeOptions` is disabled; `exportBranches` is enabled and auto-set to `true`.
- **Webpage type selected:** `exportBranches` is enabled and auto-set to `true`; `includeOptions` is enabled.
- **Empty filename field:** `filenamify` of an empty string defaults to `'file'` (verify: exact fallback).
- **Unsaved / new conversation:** `ExportAndShareMenu` is not rendered, so the export option is inaccessible.

**Acceptance criteria:**
- AC-1: Given the export dialog is open and type is set to `json`, when `Export all message branches` is checked and `Recursive` is checked, then clicking Export downloads a `.json` file containing branched messages in recursive format.
- AC-2: Given type is `screenshot`, when the dialog renders, then both `Include endpoint options` and `Export all message branches` checkboxes are disabled and labeled "Not supported".
- AC-3: Given the conversation title is "Q3 Report / Analysis", when the dialog opens, then the filename field contains a sanitized version of that title (forward slash removed by `filenamify`).
- AC-4: Given the user is on `/c/new`, when they inspect the chat header, then the Export & Share menu button is not rendered.

---

### Multi-Conversation Mode

**Purpose:** Send the same prompt simultaneously to two or more conversations side by side, each potentially using a different model or configuration. This is a power-user feature for comparing responses.

**Preconditions / access:** `PermissionTypes.MULTI_CONVO`, `Permissions.USE` granted (enabled in NuFi config). The current endpoint must not be an Assistants endpoint.

**UI elements:**
- **Add Multi-Conversation** button (`data-testid="add-multi-convo-button"`, `aria-label="com_ui_add_multi_conversation"`, icon `PlusCircle`) in the chat header, shown only when `hasAccessToMultiConvo` is true and the active endpoint is not an Assistants endpoint.
- When a second conversation is added, the chat area splits into side-by-side panels; each panel has its own `ModelSelector` and conversation context (`conversationByIndex(0)` and `conversationByIndex(1)`).

**Functional behavior:**
1. FR-1: Clicking the `AddMultiConvo` button copies the settings of the primary conversation (index 0) into a second conversation slot (index 1), stripping the title, and sets it in `conversationByIndex(1)` via Recoil.
2. FR-2: After adding, focus is moved to the `mainTextareaId` text input.
3. FR-3: A prompt typed in the shared input area is submitted to all active conversation slots simultaneously.
4. FR-4: Each conversation panel in multi-convo mode maintains its own message history, conversation ID, and model selection independently.
5. FR-5: The button is not rendered when `endpoint` is null (e.g., no conversation loaded yet) or when `isAssistantsEndpoint(endpoint)` is true.
6. FR-6: Each conversation pane generates and saves its response independently; both conversations appear in the sidebar history.

**States & edge cases:**
- **Assistants endpoint active:** The AddMultiConvo button is not rendered.
- **No endpoint configured:** Button is not rendered.
- **Removing a panel:** A secondary panel is closed via the `×` close button (`aria-label="Close added conversation"`) rendered in the `AddedConvo` chip inside the textarea header (`AddedConvo.tsx`). Clicking it calls `setAddedConvo(null)`, removing the secondary panel from the UI. The close button is not in `AddMultiConvo.tsx`.
- **Maximum panes:** The maximum is 2 simultaneous panes (primary at index 0 and one added pane at index 1). `AddMultiConvo` only ever writes to `conversationByIndex(1)`; clicking it multiple times overwrites the same slot rather than adding a third pane.

**Acceptance criteria:**
- AC-1: Given a non-Assistants endpoint is selected, when the user clicks the `PlusCircle` "Add Multi-Conversation" button, then a second conversation panel appears alongside the first.
- AC-2: Given two conversation panels are open, when the user types a message and submits, then the same prompt is sent to both conversations and each generates an independent response.
- AC-3: Given an Assistants endpoint is active, when the chat header is inspected, then the "Add Multi-Conversation" button is not present.
- AC-4: Given multi-convo mode is active, when both responses complete, then two separate conversations appear in the sidebar history.

---

### Temporary Chat

**Purpose:** Conduct a chat session that is deliberately not persisted to conversation history. Suitable for sensitive or one-off queries.

**Preconditions / access:** `PermissionTypes.TEMPORARY_CHAT`, `Permissions.USE` granted (enabled in NuFi config). The toggle is only shown when there are no existing messages in the current conversation and no submission is in progress.

**UI elements:**
- **Temporary Chat** toggle button (`aria-label="com_ui_temporary"`, `aria-pressed={isTemporary}`, icon `MessageCircleDashed`) in the chat header. Style: `bg-surface-active` (pressed/on) vs `bg-presentation shadow-sm hover:bg-surface-active-alt` (off).
- Tooltip shows `com_ui_temporary` on hover.
- The button is hidden (`return null`) once `conversation.messages.length >= 1` or while a submission is in progress (`isSubmitting`).
- **Settings > Chat > Default Temporary Chat** toggle (`switchId="defaultTemporaryChat"`) persists the preference in local storage so new conversations automatically start as temporary.

**Functional behavior:**
1. FR-1: Clicking the toggle flips the `isTemporary` Recoil atom (backed by local storage key `isTemporary`).
2. FR-2: When `isTemporary` is `true` at the time of the first message submission, `isTemporary: true` is sent in the request body to the API.
3. FR-3: The server does not save the conversation to the database when `isTemporary` is true; no conversation ID is persisted in history.
4. FR-4: Because no conversation is saved, the conversation does not appear in the sidebar history after the session ends.
5. FR-5: The `BookmarkMenu` in the chat header is hidden for temporary conversations (`conversation?.expiredAt != null` is used as the detection signal).
6. FR-6: The toggle disappears once the first message is sent (the component checks `conversation.messages.length >= 1`), preventing the user from toggling mid-conversation.
7. FR-7: The `defaultTemporaryChat` setting in Settings > Chat pre-sets `isTemporary = true` for every new conversation, eliminating the need to manually toggle.

**States & edge cases:**
- **Temporary mode toggled on, then toggled off before sending:** The chat proceeds as a normal, saved conversation.
- **Temporary mode with file uploads / RAG:** (requires manual verification on the running product: whether file attachments in a temporary chat are stored or discarded — requires server-side investigation of `api/` routes.)
- **Browser refresh mid-temporary-chat:** Since `isTemporary` is in local storage it persists across refreshes; however the messages in memory are lost. The conversation was never saved, so history is unrecoverable.
- **Multi-convo + temporary:** Temporary mode applies globally to all panels. `isTemporary` is a single global Recoil atom read by both `ChatForm` and the secondary pane submission flow; both panes send `isTemporary: true` in their request bodies.
- **Share button on a temporary chat:** The `ExportAndShareMenu` requires a non-null, non-`"new"` `conversationId`. During a temporary chat before the first message, `conversationId` is `"new"`, so Export & Share is not rendered. After the first message the client receives a `conversationId` from the server SSE response and the menu may render, but any share creation would fail server-side because the conversation is not persisted. (requires manual verification on the running product: whether the Share dialog appears and how the server responds to a share mutation for a temporary conversation.)

**Acceptance criteria:**
- AC-1: Given temporary chat mode is off, when the user clicks the `MessageCircleDashed` toggle, then `aria-pressed` changes to `true` and the button background changes to `bg-surface-active`.
- AC-2: Given temporary chat mode is on and the user sends a message, when the conversation completes, then no entry appears in the sidebar conversation history.
- AC-3: Given temporary chat mode is on and a conversation is active, when the chat header is inspected, then the BookmarkMenu button is absent.
- AC-4: Given temporary chat mode is on and the user has typed but not yet sent a message, when they click the toggle again, then `aria-pressed` changes to `false` and the conversation would be saved normally upon sending.
- AC-5: Given the user has enabled "Default Temporary Chat" in Settings > Chat, when they open a new conversation, then the toggle is pre-set to the active (pressed) state.
- AC-6: Given a temporary chat is in progress, when the first message response completes, then the temporary chat toggle button is no longer rendered in the header.
