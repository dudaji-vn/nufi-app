# Verification findings — 04 Agents & RAG

## Summary

- Claims checked: 78 | CONFIRMED: 60 | WRONG: 8 | NEEDS-FIX: 5 | RUNTIME-ONLY: 3 | VERIFY-RESOLVED: 5

---

## Findings

### [WRONG] Concept overview — "retrieved automatically at chat time"

- **Spec says:** "documents are embedded via the `rag_api` service into a pgvector database and are retrieved automatically at chat time"
- **Reality:** Retrieval is NOT automatic. The `file_search` capability works as an **LLM tool**. The model is primed with a list of filenames in its system context, then autonomously decides to call the `file_search` tool with a natural-language query. The backend POSTs to `RAG_API_URL/query` only when the LLM issues that tool call.
- **Evidence:** `api/app/clients/tools/util/fileSearch.js:88-131` — `createFileSearchTool` wraps the query logic in a standard tool callable by the model; `handleTools.js:295-325` — tool is registered and called at LLM discretion.
- **Suggested correction:** Replace "retrieved automatically at chat time" with "retrieved when the agent decides to invoke the `file_search` tool, which is triggered by the LLM during inference."

---

### [WRONG] Chatting with agent — FR-1, FR-2

- **Spec FR-1 says:** "the backend identifies `file_search` in the agent's tools list and queries the pgvector database using the user's message as the query vector"
- **Spec FR-2 says:** "Retrieved document chunks are injected into the LLM context as additional context before the model generates its response."
- **Reality:** The backend does not proactively query pgvector before generation. The model receives a system-context note listing available filenames ("Use the `file_search` tool to find relevant information within: …"). The LLM then optionally calls the tool; only at that point does the backend hit `RAG_API_URL/query`. Results are returned to the model as a **tool call result**, not pre-injected context.
- **Evidence:** `api/app/clients/tools/util/fileSearch.js:56-76` (primeFiles sets toolContext string listing filenames); `fileSearch.js:88-131` (tool call actually queries RAG); `handleTools.js:295-325` (wires tool).
- **Suggested correction:** FR-1 → "When the agent decides to use the `file_search` tool, the backend sends the tool's query string to `RAG_API_URL/query`, scoped to the `entity_id` (agent_id)." FR-2 → "Retrieved chunks are returned to the LLM as a tool call result, which the model uses to compose its response."

---

### [WRONG] Chatting with agent — FR-3 (citation behavior)

- **Spec says:** "Whether explicit citations (e.g., filename annotations) appear depends on the LLM and RAG API configuration."
- **Reality:** Citation annotations are controlled by the `FILE_CITATIONS` **permission** (`PermissionTypes.FILE_CITATIONS`). If the user's role has the `USE` permission for `FILE_CITATIONS`, the tool embeds anchor markers in results and instructs the model to cite them. Neither LLM choice nor RAG API config is the gate.
- **Evidence:** `api/app/clients/tools/util/handleTools.js:304-323` — `checkAccess({ permissionType: PermissionTypes.FILE_CITATIONS, permissions: [Permissions.USE] })`; `fileSearch.js:183-194` (citation instructions are conditionally appended based on `fileCitations` flag).
- **Suggested correction:** "Whether citation markers appear depends on whether the user's role has the `FILE_CITATIONS > USE` permission."

---

### [WRONG] Creating an agent — FR-3 (create toast text)

- **Spec says:** `toast "Agent created: {name}" appears (com_assistants_create_success)`
- **Reality:** The toast text is **"Successfully created {name}"** — `com_assistants_create_success` = `"Successfully created"` (English). The code concatenates that string with `data.name`, producing "Successfully created {name}".
- **Evidence:** `client/src/components/SidePanel/Agents/AgentPanel.tsx:384-386`; `client/src/locales/en/translation.json:125`.
- **Suggested correction:** Change toast description to `"Successfully created {name}"`.

---

### [WRONG] Editing an agent — FR-3 ("no update is sent")

- **Spec says:** "If no fields have changed (no dirty fields), a 'No changes' toast (`com_ui_no_changes`) appears and **no update is sent**."
- **Reality:** The PATCH API call (`update.mutate`) **is always sent** for non-avatar-only changes. The "No changes" determination is server-side: if the returned `data.version` equals the version captured before the call (`previousVersionRef.current`), `noVersionChange` is `true` and the toast is shown. The client does not skip the API call based on dirty fields (only the avatar-upload-only case is short-circuited via `isAvatarUploadOnlyDirty`).
- **Evidence:** `client/src/components/SidePanel/Agents/AgentPanel.tsx:326-378` (update mutation always fires); `AgentPanel.tsx:334` (version comparison post-response); `AgentPanel.tsx:427-444` (avatar-only short-circuit is the sole skip path).
- **Suggested correction:** "If the server determines no persisted change occurred (same version returned), a 'No changes' info toast appears. The API call is still made."

---

### [WRONG] Selecting the Agents endpoint — FR-3 ("Create New Agent button")

- **Spec says:** "If no agent has been created yet, the side panel shows a 'Create New Agent' button and a dropdown placeholder."
- **Reality:** The **"Create New Agent" button** (`com_ui_create_new_agent`) is rendered only when `agent_id` is truthy — i.e., only when an existing agent is already loaded. With no agents at all (`agent_id = ''`), only the `AgentSelect` dropdown (showing "Create New Agent" as its **placeholder**) renders along with the blank form fields below it.
- **Evidence:** `client/src/components/SidePanel/Agents/AgentPanel.tsx:502` — `{agent_id && (<div>...<Button>Create New Agent</Button>...</div>)}`.
- **Suggested correction:** "If no agent has been created yet, the side panel shows the agent selector dropdown (with 'Create New Agent' as placeholder text) and a blank agent form. The 'Create New Agent' reset button appears only after an agent has been loaded."

---

### [WRONG] Uploading Knowledge documents — "progress bar" visual indicator

- **Spec says (uploading state table):** "Progress bar on the file chip (`file.progress < 1`)"
- **Reality:** The visual indicator is a **spinner overlay** (Lucide/`@librechat/client` `Spinner` component), not a progress bar. When `file.progress < 1`, a `Spinner` is absolutely positioned over the file icon area.
- **Evidence:** `client/src/components/Chat/Input/Files/FilePreview.tsx:24-29`.
- **Suggested correction:** Replace "Progress bar" with "Spinner overlay on the file chip icon".

---

### [WRONG] Uploading Knowledge documents — embedding failure leaves chip in error state

- **Spec says:** "The client's file handling will show a toast or leave the chip in an error state."
- **Reality:** On embedding failure the chip is **removed** entirely (`deleteFileById(file_id)` is called in `onError`). An error toast is shown, but no chip remains in the UI — there is no persistent "error state" chip.
- **Evidence:** `client/src/hooks/Files/useFileHandling.ts:171` — `deleteFileById(file_id as string)` in `onError`; `useFileHandling.ts:97-100` — `showToast({ message, status: 'error' })`.
- **Suggested correction:** "On embedding failure, the file chip is removed and an error toast is shown."

---

### [NEEDS-FIX] Concept overview / Capabilities — MCP tools section omitted

- **Spec says:** "Code Interpreter, Web Search, and Actions/Tools buttons are **not available** in the agent editor. The only capability a user can enable is File Search."
- **Reality:** This is correct for the named capability-gated sections. However, the **MCP Tools section** (`MCPTools` component) is rendered regardless of capabilities — it appears whenever `availableMCPServers != null && availableMCPServers.length > 0`. If any MCP server is configured in NuFi, that section would be visible. The spec silently omits this.
- **Evidence:** `client/src/components/SidePanel/Agents/AgentConfig.tsx:347-353` — MCP section guarded only by `availableMCPServers.length > 0`, not by capabilities.
- **Suggested correction:** Add a note: "The MCP Tools section may also appear if any MCP servers are configured server-side; this is independent of the `capabilities` array."

---

### [NEEDS-FIX] Uploading Knowledge documents — verify marker on fileConfig inheritance

- **Spec marks:** `(verify: confirm agents endpoint inherits Nufi fileConfig limits or uses separate config)`
- **Resolution: CONFIRMED.** When the agent's provider is "Nufi", `useAgentFileConfig` calls `getEndpointFileConfig({ endpoint: "Nufi", ... })`. Since "Nufi" is a custom endpoint type, the resolver's branch at `file-config.ts:594-622` looks up `mergedFileConfig.endpoints["Nufi"]` and returns the merged Nufi config with all its limits (fileLimit 5, fileSizeLimit 20 MB, totalSizeLimit 50 MB).
- **Evidence:** `client/src/hooks/Agents/useAgentFileConfig.ts:29-33`; `packages/data-provider/src/file-config.ts:594-622`.

---

### [NEEDS-FIX] Deleting an agent — verify marker on vector cascade

- **Spec marks:** `(verify: whether agent deletion cascades to vector embeddings via rag_api)`
- **Resolution: NOT cascaded.** The `deleteAgentHandler` only calls `db.deleteAgent({ id })`. No `deleteVectors` / RAG API call is made. Knowledge file embeddings remain in pgvector after agent deletion.
- **Evidence:** `api/server/controllers/agents/v1.js:815-828`; compare with `api/server/services/Files/VectorDB/crud.js:20-48` (`deleteVectors` exists but is not called from the agent-delete path).
- **Suggested correction:** Change the spec's FR-5 from "(verify:…)" to: "Knowledge files are NOT deleted from the vector database when an agent is deleted. Their pgvector embeddings are orphaned."

---

### [NEEDS-FIX] Uploading Knowledge documents — verify marker on storage rollback

- **Spec marks:** `(verify: whether partial storage result is rolled back or left orphaned)`
- **Resolution: LEFT ORPHANED.** Storage (`handleFileUpload`) runs first (lines 744–752 in `process.js`). If `uploadVectors` then throws (lines 757–762), the error propagates up and no rollback of the already-stored file occurs. The file remains in storage (S3/local) with no DB record and no vector embeddings.
- **Evidence:** `api/server/services/Files/process.js:742-792`; `api/server/services/Files/VectorDB/crud.js:113-119` (throws on error).
- **Suggested correction:** "If vector embedding fails after storage succeeds, the storage file is orphaned (no rollback). Operators should periodically clean up orphaned storage objects."

---

### [NEEDS-FIX] Uploading Knowledge documents — verify on UI error display for embedding failure

- **Spec marks:** `(verify: exact UI error display for embedding failure)`
- **Resolution:** Server returns 4xx/5xx. Client `onError` in the upload mutation: (1) calls `deleteFileById(file_id)` to remove the chip; (2) calls `setError(errorMessage)` which shows a toast (`status: 'error'`, duration 5 s) with the server error message (e.g., "File embedding failed. The filetype … is not supported").
- **Evidence:** `client/src/hooks/Files/useFileHandling.ts:159-180`; `useFileHandling.ts:97-101`.

---

### [RUNTIME-ONLY] Chatting with agent — FR-3 (citation annotations in NuFi)

- **Spec marks:** `(verify: whether citation annotations are surfaced in NuFi's current deployment)`
- **Resolution: RUNTIME-ONLY.** Citations require the `FILE_CITATIONS > USE` permission to be granted to the user's role in NuFi's role configuration. Cannot be resolved statically; requires a live permission audit.

---

### [RUNTIME-ONLY] Chatting with agent — FR-4 (no error when no match)

- **Spec says:** "If no relevant chunks are found, the model answers from training knowledge without RAG context; no error is shown."
- **Resolution: RUNTIME-ONLY.** The code path when `formattedResults.length === 0` returns the string `"No content found in the files…"` to the model as a tool result. The model then responds. Whether this surfaces as an error to the user depends on how the model uses that result. Likely matches spec intent but needs live validation.
- **Evidence:** `api/app/clients/tools/util/fileSearch.js:151-156`.

---

### [VERIFY-RESOLVED] Chatting with agent — RAG retrieval on empty Knowledge store

- **Spec marks** (edge case): "Empty Knowledge: Agent responds from model training only; no retrieval error is expected."
- **Resolution: CONFIRMED.** When `files.length === 0`, the tool immediately returns `['No files to search. Instruct the user to add files for the search.', undefined]`. The model receives this and responds normally; no exception is thrown.
- **Evidence:** `api/app/clients/tools/util/fileSearch.js:91-93`.

---

### [MINOR] Creating an agent — Category "required" asterisk has no validation

- **Spec says:** "Category selector — required (`*`)"
- **Reality:** The `*` asterisk is displayed in the label, but no React Hook Form `rules.required` is applied to the category field. The field always has a value (`'general'` default from `defaultAgentFormValues`), so submission never fails for a missing category in practice.
- **Evidence:** `client/src/components/SidePanel/Agents/AgentConfig.tsx:290-295`; `packages/data-provider/src/schemas.ts:291` — `category: 'general'`.
- **Suggested correction:** Note that the asterisk reflects UX intent (always a value), not a form validation gate; alternatively add `rules={{ required: true }}` to the controller.

---

## Confirmed claims (spot-checked)

| Claim | Evidence |
|---|---|
| `capabilities: ["file_search"]` at librechat.yaml lines 34-36 | `nufi-chat/librechat.yaml:34-36` |
| fileLimit 5 / fileSizeLimit 20 MB / totalSizeLimit 50 MB under `Nufi` endpoint | `nufi-chat/librechat.yaml:61-64` |
| supportedMimeTypes list (pdf, txt, md, csv, docx, json, images) | `nufi-chat/librechat.yaml:65-77` |
| Image uploads rejected for `file_search` tool resource | `api/server/services/Files/process.js:553-554` |
| Dual storage pattern: storage first, then vectors | `api/server/services/Files/process.js:742-792` |
| `uploadVectors` POSTs to `RAG_API_URL/embed` with `file_id`, `file`, `entity_id` | `api/server/services/Files/VectorDB/crud.js:74-88` |
| `known_type: false` throws embedding-failure error | `api/server/services/Files/VectorDB/crud.js:99-101` |
| `embedded: Boolean(responseData.known_type)` written to DB | `api/server/services/Files/VectorDB/crud.js:111` |
| `source: FileSources.vectordb` (filepath value) | `api/server/services/Files/VectorDB/crud.js:110` |
| vectordb source badge: yellow-700/yellow-900 + Database icon | `client/src/components/Chat/Input/Files/SourceIcon.tsx:17,52-59` |
| spinner appears on chip while `file.progress < 1` | `client/src/components/Chat/Input/Files/FilePreview.tsx:24-29` |
| File chip removed and `com_ui_deleting_file` toast on knowledge file deletion | `client/src/components/Chat/Input/Files/FileRow.tsx:119-124` |
| `deleteVectors` calls `DELETE RAG_API_URL/documents` with `[file.file_id]` | `api/server/services/Files/VectorDB/crud.js:27-34` |
| Agent deletion does NOT cascade to vectors | `api/server/controllers/agents/v1.js:815-828` |
| `isEphemeralAgentId` returns true for any ID not starting with `agent_` | `packages/data-provider/src/parsers.ts:566-568` |
| Upload button `disabledUploadButton = isEphemeralAgent(agent_id) \|\| fileSearchChecked === false` | `client/src/components/SidePanel/Agents/FileSearch.tsx:72` |
| Disabled message shown when `agent_id` is falsy | `client/src/components/SidePanel/Agents/FileSearch.tsx:181-184` |
| Name field required via `rules={{ required: localize('com_ui_agent_name_is_required') }}` | `client/src/components/SidePanel/Agents/AgentConfig.tsx:229` |
| `com_ui_agent_name_is_required` text = inline error below name field | `client/src/locales/en/translation.json` |
| Missing provider/model toast = `com_agents_missing_provider_model` | `client/src/components/SidePanel/Agents/AgentPanel.tsx:451` |
| `file_search: true` pushes `Tools.file_search` to tools array in `onSubmit` | `client/src/components/SidePanel/Agents/AgentPanel.tsx:417-419` |
| Avatar 80×80 px (`h-20 w-20`) | `client/src/components/SidePanel/Agents/AgentAvatar.tsx:87` |
| Avatar aria-label = `com_ui_upload_agent_avatar_label` | `client/src/components/SidePanel/Agents/AgentAvatar.tsx:88` |
| Avatar success toast = `com_ui_upload_agent_avatar` = "Successfully updated agent avatar" | `AgentPanel.tsx:263`; `en/translation.json:1643` |
| Avatar upload error toast = `com_agents_avatar_upload_error` | `AgentPanel.tsx:355` |
| Model localStorage keys `LAST_AGENT_MODEL` / `LAST_AGENT_PROVIDER` | `client/src/components/SidePanel/Agents/ModelPanel.tsx:57-58` |
| Provider combobox `disabled` until provider chosen (placeholder `com_ui_select_provider_first`) | `ModelPanel.tsx:192-195` |
| Reset Parameters = `com_ui_reset_var` + live-region announcement | `ModelPanel.tsx:254-257` |
| Agent selector `ControlCombobox` aria-label = `com_ui_agent` | `client/src/components/SidePanel/Agents/AgentSelect.tsx:239` |
| EarthIcon (`text-status-ok` = green, HSL 150 65% 45%) for public agents | `AgentSelect.tsx:54`; `style.css:121` |
| Share count badge = `totalCurrentShares` (includes public toggle) | `GenericGrantAccessDialog.tsx:225,258-263` |
| `DuplicateAgent` button visible to author/admin/canEditThisAgent | `AgentFooter.tsx:122-123` |
| `com_ui_duplicate_agent` success toast on duplicate | `client/src/components/SidePanel/Agents/DuplicateAgent.tsx:14` |
| Delete confirmation dialog body = `com_ui_delete_agent_confirm` | `DeleteButton.tsx:109`; `en/translation.json:936` |
| Delete success toast = `com_ui_agent_deleted` = "Successfully deleted agent" | `DeleteButton.tsx:43-46`; `en/translation.json:687` |
| Delete error toast = `com_ui_agent_delete_error` | `DeleteButton.tsx:75-79` |
| DeleteButton returns null for ephemeral agents | `DeleteButton.tsx:83-85` |
| `codeEnabled`, `webSearchEnabled`, `actionsEnabled`, `toolsEnabled` all false with `["file_search"]` only | `client/src/hooks/Agents/useAgentCapabilities.ts:21-63` |
| Default categories: general, hr, rd, finance, it, sales, aftersales | `packages/data-schemas/src/methods/agentCategory.ts:159-202` |
| Instructions textarea: `min-h-[100px] resize-y` | `client/src/components/SidePanel/Agents/Instructions.tsx:88` |
| Instructions placeholder = `com_agents_instructions_placeholder` = "The system instructions that the agent uses" | `Instructions.tsx:90`; `en/translation.json:73` |
| Description `maxLength={512}`, Name `maxLength={256}` | `AgentConfig.tsx:279,239` |
| Support Contact name `minLength: 3`, email `validateEmail` | `AgentConfig.tsx:529-532,573-575` |
| Version History button (`VersionButton`) rendered when `agent_id` exists | `AgentFooter.tsx:81` |
| `com_ui_no_changes` = "No changes were made" (info toast) | `AgentPanel.tsx:49`; `en/translation.json:1255` |
| Update success toast = `com_assistants_update_success_name` = "Successfully updated {name}" | `AgentPanel.tsx:51`; `en/translation.json:148` |
| `"Select" button` disabled when `isEphemeralAgent(agent_id)` | `AgentPanel.tsx:520` |
| Files uploaded sequentially (for loop with `await startUpload`) | `client/src/hooks/Files/useFileHandling.ts:306-436` |
| file_search Knowledge files merged from in-memory + persisted `useGetAgentFiles` | `AgentConfig.tsx:114-164` |
