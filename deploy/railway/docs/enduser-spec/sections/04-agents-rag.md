## Agents & File Search (RAG)

### Concept overview

NuFi Chat exposes two distinct ways to talk with an AI:

**Plain Nufi endpoint** — the default chat mode. The user selects "Nufi" from the
endpoint/model selector. Files attached via the 📎 button are sent as message
attachments and are scoped to that single message; they are not stored
persistently and are unavailable in any future conversation or new session.
There is no retrieval-augmented generation (RAG) in this mode.

**Agents endpoint** — an advanced mode that adds a persistent, configurable AI
assistant ("agent"). Agents are the *only* mechanism through which RAG operates
in NuFi. An agent can have documents uploaded into its **Knowledge** store; those
documents are embedded via the `rag_api` service into a pgvector database. At
inference time, the model receives the list of available filenames as system
context and may autonomously invoke the `file_search` tool, which then queries
`RAG_API_URL/query` and returns matching chunks back to the model as a tool
result—across **all** conversations with that agent, not just the current one.
Retrieval is **not** automatic: it occurs only when the LLM decides to call the
`file_search` tool.

**Critical distinction that testers must internalize:**

| Dimension | Knowledge file (agent) | Message attachment (📎) |
|---|---|---|
| Where uploaded | Agent editor → File Search section | Chat input 📎 |
| Scope | All conversations with this agent, forever | Current conversation / message only |
| Retrieval | Embedded in pgvector; retrieved when the LLM calls the `file_search` tool | Sent inline in the context window |
| RAG? | Yes | No |

**NuFi capability scope.** The Agents endpoint in NuFi is configured with
`capabilities: ["file_search"]` only (see `librechat.yaml` lines 34-36). This means
Code Interpreter, Web Search, and Actions/Tools buttons are **not available** in
the agent editor. The only capability a user can enable is File Search.

> Note: The **MCP Tools section** may also appear in the agent editor if any MCP
> servers are configured server-side. Its visibility is guarded only by
> `availableMCPServers.length > 0` and is independent of the `capabilities` array.

---

### Selecting the Agents endpoint

**Purpose:** Route a conversation through the Agents infrastructure instead of
the plain Nufi chat endpoint.

**Preconditions / access:** `interface.agents: true` and `interface.endpointsMenu: true`
must be set in `librechat.yaml` (both are enabled). All authenticated users can
switch endpoints.

**UI elements:**
- Endpoint / model selector in the top toolbar (labelled "Nufi" by default)
- Dropdown entry labelled **"Agents"** (`com_ui_agents`)
- After selection, the right-side panel shows the Agent builder panel

**Functional behavior:**
1. FR-1 — Clicking the endpoint selector opens a dropdown listing available
   endpoints; "Agents" appears as an entry.
2. FR-2 — Selecting "Agents" loads the Agent builder panel (side panel) and
   switches the active endpoint for new messages to `EModelEndpoint.agents`.
3. FR-3 — If no agent has been created yet, the side panel shows the agent selector
   dropdown (with "Create New Agent" as placeholder text) and a blank agent form.
   The "Create New Agent" reset button appears only after an existing agent has been
   loaded; no conversation can be started until an agent is selected.
4. FR-4 — If at least one agent exists, the dropdown pre-selects the last-used
   agent and displays it in the panel.

**States & edge cases:**
- If `interface.endpointsMenu` were set to `false`, the selector would be hidden
  and the Agents endpoint would be unreachable.
- Switching away from Agents to Nufi mid-conversation does not delete the
  conversation; it changes the endpoint for the next message only.

**Acceptance criteria:**
- AC-1 — Given the user is on any endpoint, when they open the endpoint selector
  and click "Agents", then the right-side panel shows the Agent builder UI.
- AC-2 — Given no agent exists, when the Agents endpoint is selected, then the
  conversation start button is disabled / inactive until an agent is selected.

---

### Creating an agent

**Purpose:** Define a new persistent agent with a name, description, category,
instructions, model, and optionally an avatar.

**Preconditions / access:** User must be on the Agents endpoint. The agent builder
side panel must be open. Standard (non-admin) users can create their own agents.

**UI elements (sourced from `AgentConfig.tsx` and `AgentPanel.tsx`):**
- **Agent selector** (top of panel) — `ControlCombobox`, aria-label `com_ui_agent`;
  placeholder shows "Create New Agent" (`com_ui_create_new_agent`) when blank
- **"Create New Agent" button** — appears when an existing agent is loaded; resets
  the form to blank for a new agent
- **Avatar** — 80×80 px clickable image (`com_ui_upload_agent_avatar_label`); opens
  a menu for upload or reset
- **Name** field — required (`*`), label `com_ui_name`, placeholder
  `com_agents_name_placeholder` ("Optional: The name of the agent"), maxLength 256
- **Description** field — optional, label `com_ui_description`, placeholder
  `com_agents_description_placeholder` ("Optional: Describe your Agent here"),
  maxLength 512
- **Category** selector — required (`*`), label `com_ui_category`; a `ControlCombobox`
  with categories: General, Finance, HR, IT, R&D, Sales, After Sales (and possibly
  others defined by admin). Defaults to "general".
- **Instructions** textarea — label `com_ui_instructions`, placeholder
  `com_agents_instructions_placeholder` ("The system instructions that the agent uses"),
  min height 100 px, resizable. A "Variables" button (`com_ui_variables`) opens a
  dropdown to insert dynamic special variables (e.g., `{{current_date}}`).
- **Model** button — label `com_ui_model` (required `*`); navigates to the Model
  Parameters sub-panel to choose provider + model
- **Support Contact** section (optional) — fields: Name (min 3 chars) and Email
  (validated format)
- **Create / Save** button at footer — renders "Create" (`com_ui_create`) when no
  `agent_id` exists, "Save" (`com_ui_save`) when editing

**Functional behavior:**
1. FR-1 — Submitting without a **Name** triggers an inline error message
   (`com_ui_agent_name_is_required`).
2. FR-2 — Submitting without selecting a **Provider** and **Model** triggers a
   toast error (`com_agents_missing_provider_model`).
3. FR-3 — On successful creation, a toast **"Successfully created {name}"** appears
   (`com_assistants_create_success` + agent name concatenated) and the new agent ID
   appears in the agent selector.
4. FR-4 — Avatar upload is separate from agent create/update: uploading an avatar
   triggers `POST /api/agents/:id/avatar` after the agent is persisted; a
   success toast `com_ui_upload_agent_avatar` is shown.
5. FR-5 — Category defaults to "general" for new agents.
6. FR-6 — The agent ID (assigned by the server) appears in small italic text
   below the Name field immediately after creation.
7. FR-7 — Support Contact name requires minimum 3 characters; email must be a
   valid email format; violations show inline error messages.

**States & edge cases:**
- Creating a second agent while viewing the first: click "Create New Agent" to
  reset the form; the existing agent is not deleted.
- Avatar upload fails: toast `com_agents_avatar_upload_error` is shown; the agent
  itself is still saved without an avatar.
- Name exceeding 256 chars: browser-enforced `maxLength`; no additional server
  error is expected.

**Acceptance criteria:**
- AC-1 — Given the form is blank, when the user submits without filling in Name,
  then an inline error (`"Agent name is required"`) appears below the Name field and
  no API call is made.
- AC-2 — Given Name is filled but Model is not selected, when the user submits,
  then a toast error appears and no agent is created.
- AC-3 — Given all required fields are valid, when the user clicks Create, then
  a success toast shows the new agent name and the panel updates to edit mode for
  that agent.
- AC-4 — Given an agent exists, when the user uploads an avatar image, then a
  success toast "Successfully updated agent avatar" appears and the avatar renders
  in the 80×80 circle.

---

### Configuring the agent model

**Purpose:** Choose which LLM provider and model powers the agent, and optionally
tune inference parameters.

**Preconditions / access:** Agent builder must be open. The Model sub-panel is
reached by clicking the **Model** button in the main builder.

**UI elements (sourced from `ModelPanel.tsx`):**
- **"Back to builder" button** (chevron-left icon, `com_ui_back_to_builder`) — returns
  to the main agent config panel
- **Model Parameters** heading (`com_ui_model_parameters`)
- **Provider** combobox — label `com_ui_provider` (required `*`); lists all
  configured non-assistant endpoints except `agents` itself. In NuFi the only
  selectable provider is **"Nufi"** (the custom OpenAI-compatible endpoint).
- **Model** combobox — label `com_ui_model` (required `*`); populated from models
  fetched for the selected provider. Disabled until a provider is chosen
  (placeholder: `com_ui_select_provider_first`).
- **Model parameter controls** — dynamically rendered grid of settings (e.g.,
  temperature, max tokens) based on provider/model capabilities
- **Reset Parameters** button — `com_ui_reset_var` ("Reset Model Parameters");
  resets all parameter overrides to defaults

**Functional behavior:**
1. FR-1 — Selecting a Provider populates the Model dropdown with that provider's
   available models; the first model is auto-selected.
2. FR-2 — Changing the provider clears the previously selected model and
   auto-selects the first model of the new provider.
3. FR-3 — The last-used model and provider are persisted to localStorage
   (`LocalStorageKeys.LAST_AGENT_MODEL`, `LocalStorageKeys.LAST_AGENT_PROVIDER`)
   so new agents start from the previous selection.
4. FR-4 — Clicking "Reset Model Parameters" clears all inference overrides and
   announces "Model Parameters have been reset." to screen readers.

**States & edge cases:**
- If the Nufi backend is unreachable, the model list shows the placeholder
  "loading..." (from `librechat.yaml` default) until fetch succeeds or times out.
- In NuFi there is only one provider ("Nufi"); the Provider combobox still renders
  but with a single option.

**Acceptance criteria:**
- AC-1 — Given the Model sub-panel is open and Provider is "Nufi", when the user
  opens the Model dropdown, then the list contains at least one model fetched from
  the backend.
- AC-2 — Given a model is selected, when the user clicks "Back to builder", then
  the main builder shows the selected model name in the Model button.
- AC-3 — Given model parameters have been changed, when the user clicks
  "Reset Model Parameters", then all parameters return to empty/default and a
  live-region announcement confirms the reset.

---

### Enabling File Search capability

**Purpose:** Turn on the RAG capability for an agent, which makes the agent able
to retrieve context from its uploaded Knowledge documents.

**Preconditions / access:**
- An agent must already be **saved** (have a real `agent_id`; not an ephemeral/unsaved
  agent). Uploading files is disabled until the agent is persisted.
- The NuFi deployment has `rag_api` running with `RAG_API_URL` configured and
  pgvector available.

**UI elements (sourced from `FileSearch.tsx`, `FileSearchCheckbox.tsx`,
`AgentConfig.tsx`):**
- **"File Search"** section header (`com_assistants_file_search`) inside the
  **Capabilities** block (`com_assistants_capabilities`)
- **"Enable File Search" checkbox** (`com_agents_enable_file_search`) — a `Checkbox`
  control bound to `AgentCapabilities.file_search`
- **Info icon button** (circle-help icon) — on hover, shows a HoverCard tooltip:
  `com_agents_file_search_info` ("When enabled, the agent will be informed of the
  exact filenames listed below, allowing it to retrieve relevant context from these files.")
- **"Upload for File Search" button** (`com_ui_upload_file_search`) — with an
  attachment icon; disabled when the checkbox is unchecked or agent is unsaved

**Functional behavior:**
1. FR-1 — The Capabilities section renders only when `fileSearchEnabled` is true
   in the server capabilities config (set via `capabilities: ["file_search"]` in
   `librechat.yaml`).
2. FR-2 — Checking the checkbox sets `AgentCapabilities.file_search = true` in the
   form state; unchecking sets it to `false`.
3. FR-3 — When saved with `file_search: true`, the server adds `Tools.file_search`
   to the agent's tools array (handled in `AgentPanel.onSubmit`).
4. FR-4 — When the checkbox is **unchecked**, the "Upload for File Search" button
   is disabled (`disabledUploadButton = fileSearchChecked === false`).
5. FR-5 — When the agent has not yet been saved (ephemeral agent), the Upload
   button is also disabled and a message below reads:
   `com_agents_file_search_disabled` ("Agent must be created before uploading
   files for File Search.").

**States & edge cases:**
- Disabling File Search after files have already been uploaded does not delete the
  already-embedded Knowledge files; they remain associated with the agent.
- If `RAG_API_URL` is not configured, `uploadVectors` will throw
  "RAG_API_URL not defined" and any subsequent upload will fail at the server level.

**Acceptance criteria:**
- AC-1 — Given an unsaved agent form, when the user looks at the File Search
  section, then the Upload button is disabled and a hint message is shown.
- AC-2 — Given a saved agent, when the user checks "Enable File Search" and saves
  the agent, then the agent's tools list includes `file_search`.
- AC-3 — Given File Search is unchecked, when the user tries to click the Upload
  button, then the button is visually disabled and no file picker opens.
- AC-4 — Given File Search is enabled, when the user hovers over the info icon,
  then a tooltip explains the retrieval behavior.

---

### Uploading Knowledge documents

**Purpose:** Embed documents into the agent's persistent Knowledge store so the
agent can retrieve relevant excerpts at chat time via RAG.

**Preconditions / access:**
- Agent must be saved (have a real `agent_id`).
- "Enable File Search" checkbox must be checked.
- `rag_api` service must be reachable.

**File limits (from `librechat.yaml` `fileConfig.endpoints.Nufi`):**
- Maximum **5 files** per agent (`fileLimit: 5`)
- Per-file size limit: **20 MB** (`fileSizeLimit: 20`)
- Total size limit across all files: **50 MB** (`totalSizeLimit: 50`)

**Supported types (from `librechat.yaml` `supportedMimeTypes`):**
- Images: `image/png`, `image/jpeg`, `image/webp`, `image/gif`
- Documents: `application/pdf`, `text/plain`, `text/markdown`, `text/csv`,
  `application/vnd.openxmlformats-officedocument.wordprocessingml.document` (`.docx`),
  `application/json`

> Note: The NuFi file config is applied under the "Nufi" provider key; the Agents
> endpoint inherits these limits when the agent's provider is Nufi. **CONFIRMED:**
> `useAgentFileConfig` resolves to the merged Nufi config (fileLimit 5,
> fileSizeLimit 20 MB, totalSizeLimit 50 MB) via the `endpoints["Nufi"]` branch in
> `file-config.ts`.

**UI elements (sourced from `FileSearch.tsx`):**
- **"Upload for File Search" button** — with `AttachmentIcon`; label
  `com_ui_upload_file_search`. Triggers a hidden `<input type="file" multiple>`.
- **File chips / rows** — rendered by `FileRow` and `FileContainer` below the button;
  each chip shows the filename and file type. Non-image files show a `FileContainer`
  chip; images show an `Image` thumbnail.
- **Remove button** on each chip — `RemoveFile` (X button); triggers deletion from
  both the storage backend and the vector database.

**Backend processing (dual-storage pattern, sourced from `processAgentFileUpload`
in `process.js` and `uploadVectors` in `VectorDB/crud.js`):**

The server executes two sequential steps when a file is uploaded to
`EToolResources.file_search`:

1. **Storage upload** — The file is saved to the configured file storage backend
   (local filesystem, S3, Firebase, etc.) via `handleFileUpload`. This provides a
   permanent backup of the original file.
2. **Vector embedding** — The file is POSTed to `RAG_API_URL/embed` with:
   - `file_id` — UUID for the document
   - `file` — the raw file stream
   - `entity_id` — the `agent_id` (scopes the embeddings to this agent)
   
   The RAG API response includes `known_type` and `status`. If `known_type` is
   `false`, an error "File embedding failed. The filetype ... is not supported" is
   thrown. If `status` is falsy, "File embedding failed." is thrown.
   
3. The database record is written with `embedded: Boolean(responseData.known_type)`
   and `source: FileSources.vectordb`. The agent's resource file list is updated
   via `db.addAgentResourceFile`.

**File upload states visible to the user:**

| State | Visual indicator |
|---|---|
| Uploading | **Spinner overlay** on the file chip icon (`file.progress < 1`) |
| Embedded / Ready | Chip visible with vectordb source styling (amber/yellow badge, `FileSources.vectordb`) |
| Embedding failure | File chip is **removed** entirely; an error toast is shown with the server error message |

> Note on embedding failure: The server returns 4xx/5xx. The client `onError` handler
> calls `deleteFileById(file_id)` — removing the chip — and then shows an error toast
> (e.g., "File embedding failed. The filetype … is not supported"). No chip remains
> in the UI in an error state.

**Functional behavior:**
1. FR-1 — Clicking "Upload for File Search" opens the OS file picker with `multiple`
   selection enabled.
2. FR-2 — Selected files are uploaded one at a time; while uploading (`file.progress < 1`),
   a spinner overlay is shown on the chip icon.
3. FR-3 — The server rejects image files for the `file_search` tool resource
   (`"Image uploads are not supported for file search tool resources"`).
4. FR-4 — After successful embedding, the file chip remains in the Knowledge section
   across agent editor sessions (persisted in the database, loaded via
   `useGetAgentFiles(agent_id)`).
5. FR-5 — Deleting a Knowledge file chip triggers `DELETE RAG_API_URL/documents`
   (sending the `file_id`) to remove embeddings, and removes the file from storage
   and the database.
6. FR-6 — If the agent ID is ephemeral (unsaved agent), the upload button is
   disabled; uploading is not possible.
7. FR-7 — Uploading a file with a MIME type not in `supportedMimeTypes` is rejected
   by the server filter (`filterFile`) with "Unsupported file type".
8. FR-8 — Uploading a file exceeding `fileSizeLimit` (20 MB) is rejected with
   a size-limit error before the file reaches the vector embedding step.
9. FR-9 — Uploading when the total uploaded size would exceed `totalSizeLimit`
   (50 MB) is enforced at the server level.
10. FR-10 — The Knowledge file list is merged from both the in-memory upload
    state and the persisted agent files fetched from the API, preventing duplicates
    by `file_id`.

**States & edge cases:**
- **Unsupported file type**: Server returns error; the file chip is removed and an
  error toast is shown. `.docx`, `.pdf`, `.txt`, `.md`, `.csv`, `.json` are
  supported; `.pptx`, `.xlsx`, `.zip` are not.
- **Oversize file** (> 20 MB per file): Server `filterFile` rejects before any
  storage or embedding occurs.
- **Total size exceeded** (> 50 MB across all files): Server rejects the upload.
- **Embedding failure** (RAG API rejects or returns `known_type: false`): Server
  throws; the file chip is removed and an error toast is shown. If storage had
  already succeeded before the embedding step, the storage file is **orphaned** —
  no rollback is performed. Operators should periodically clean up orphaned storage
  objects.
- **Empty Knowledge** (no files uploaded): The agent operates without retrieval;
  it answers from its training / instructions alone, with no document context.
- **RAG_API_URL unreachable**: Upload fails with "RAG_API_URL not defined" or a
  network error. Storage runs **first** (confirmed); if the RAG call then fails,
  the stored file is orphaned with no DB record and no vector embeddings.
- **File already embedded** (same file re-uploaded): No deduplication is enforced
  client-side beyond `file_id`; duplicate embedding at the vector DB level is the
  responsibility of the RAG API service.

**Acceptance criteria:**
- AC-1 — Given File Search is enabled and the agent is saved, when the user clicks
  "Upload for File Search" and selects a `.pdf` under 20 MB, then a chip with a
  spinner overlay appears while uploading, then it transitions to an embedded chip
  with amber/vectordb styling.
- AC-2 — Given File Search is enabled, when the user selects a `.pptx` file, then
  the server returns an error and a toast indicates unsupported file type; no chip
  remains.
- AC-3 — Given File Search is enabled, when the user selects a file larger than
  20 MB, then an error is returned and no chip is added.
- AC-4 — Given Knowledge files have been uploaded and the agent editor is closed
  then reopened, when the user views the agent, then previously uploaded files
  still appear as chips in the File Search section.
- AC-5 — Given a Knowledge file chip is displayed, when the user clicks its remove
  button, then the chip disappears and a "deleting file" toast is shown; the file
  no longer appears on page reload.
- AC-6 — Given the RAG API is unavailable, when the user attempts a Knowledge
  upload, then an error is surfaced and the file is not shown as embedded.

---

### Chatting with the agent (retrieval behavior)

**Purpose:** Use an agent with File Search enabled to get answers grounded in the
uploaded Knowledge documents.

**Preconditions / access:**
- An agent is selected in the Agents endpoint.
- The agent has File Search enabled (`file_search` in its tools) and at least one
  embedded Knowledge file.

**UI elements:**
- Chat input — standard message box; no special UI changes are required to trigger
  retrieval.
- Per-message 📎 attachment button — available for sending per-message file
  attachments (conversation-scoped only; not added to Knowledge).
- Agent name / avatar displayed in the conversation header or side panel.

**Functional behavior:**
1. FR-1 — When the user sends a message, the model receives a system-context note
   listing the available Knowledge filenames ("Use the `file_search` tool to find
   relevant information within: …"). The model may then autonomously invoke the
   `file_search` tool; only at that point does the backend send the tool's query
   string to `RAG_API_URL/query`, scoped to the `entity_id` (agent_id).
2. FR-2 — Retrieved document chunks are returned to the LLM as a **tool call
   result**, which the model uses to compose its response. Chunks are not
   pre-injected into the context before generation.
3. FR-3 — The model's response may reference file content. Whether explicit
   citation markers (e.g., filename annotations) appear depends on whether the
   user's role has the `FILE_CITATIONS > USE` permission. (requires manual
   verification on the running product: confirm `FILE_CITATIONS` permission is
   granted to the appropriate role in NuFi's role configuration).
4. FR-4 — If no relevant chunks are found in the Knowledge store (no match), the
   model answers from training knowledge without RAG context; no error is shown to
   the user.
5. FR-5 — Per-message attachments (📎) are sent as inline context for that message
   only and do not affect the persistent Knowledge store.
6. FR-6 — Switching to a new conversation with the **same agent** gives access to
   the same Knowledge documents; Knowledge is agent-scoped, not conversation-scoped.
7. FR-7 — Switching to a new conversation with a **different agent** (or no agent)
   gives no access to the first agent's Knowledge.

**States & edge cases:**
- **Empty Knowledge**: **CONFIRMED** — when `files.length === 0`, the tool
  immediately returns "No files to search. Instruct the user to add files for the
  search." to the model; no exception is thrown and no error is shown to the user.
- **Retrieval with no match**: When no chunks are found, the tool returns "No
  content found in the files…" as a tool result; the model responds using that
  context. Whether this surfaces as a visible error depends on the model's
  response. (requires manual verification on the running product: confirm the
  model's behavior when no chunks are found).
- **Knowledge file deleted mid-conversation**: Future turns in the same conversation
  will no longer retrieve from that file; past assistant messages are unaffected.
- **Very large Knowledge store**: Retrieval latency may increase; response time may
  be noticeably longer.

**Acceptance criteria:**
- AC-1 — Given an agent with a `.pdf` Knowledge file containing the text "Project
  Alpha budget is $500,000", when the user asks "What is the Project Alpha budget?",
  then the assistant's response includes information from the document (e.g., the
  budget figure).
- AC-2 — Given an agent with File Search enabled but no Knowledge files, when the
  user asks a question about a topic only a document could answer, then the agent
  responds without error (possibly acknowledging lack of information).
- AC-3 — Given a conversation using Agent A, when the user starts a new
  conversation with Agent A, then the same Knowledge documents are available for
  retrieval without re-uploading.
- AC-4 — Given a conversation using Agent A, when the user switches to the plain
  Nufi endpoint for a new message, then no RAG retrieval occurs.

---

### Editing an agent

**Purpose:** Modify an existing agent's name, description, instructions, model,
capabilities, Knowledge files, or avatar.

**Preconditions / access:**
- The agent must already exist. The current user must be the agent's author, an
  admin, or have `EDIT` permission on the agent resource.
- Non-owners who lack `EDIT` permission see a "not available" message
  (`com_agents_not_available`, `com_agents_no_access`).

**UI elements:**
- Agent selector (top of side panel) — choose an existing agent from the dropdown
- All fields in the main builder panel are editable (same as creation)
- **Save** button (`com_ui_save`) — replaces "Create" once an agent_id exists
- **Advanced** button — opens Advanced settings panel (agent chaining, recursion
  limits etc.; not File Search related in NuFi)
- **Version History** button — access previous agent versions (`VersionButton`)

**Functional behavior:**
1. FR-1 — Loading an existing agent populates all form fields from the persisted
   agent data, including current `file_search` checkbox state and Knowledge files.
2. FR-2 — Clicking "Save" calls `PATCH /api/agents/:id` with the updated payload;
   on success, a toast `com_assistants_update_success_name` appears.
3. FR-3 — The PATCH API call is **always sent** (except for the avatar-upload-only
   case). If the server determines no persisted change occurred (the returned
   `data.version` equals the previously captured version), a "No changes" info
   toast (`com_ui_no_changes`) is shown.
4. FR-4 — Removing a Knowledge file from the editor and saving does **not**
   automatically delete the file from the vector DB; deletion is triggered
   separately by clicking the file chip's remove (X) button.
5. FR-5 — Avatar changes follow the same two-step flow as creation: agent config
   is saved first, then the avatar is uploaded via a separate endpoint.

**States & edge cases:**
- Editing an agent that is currently in use (active conversation): changes take
  effect for the **next** message; the current in-flight response is unaffected.
- Version history: previous versions can be viewed but the spec for version
  management is covered separately.

**Acceptance criteria:**
- AC-1 — Given the user is the agent author, when they open the agent editor and
  change the Name field, then the Save button is active (dirty state detected).
- AC-2 — Given no fields have changed, when the user clicks Save, then a "No
  changes" info toast appears.
- AC-3 — Given the user edits the Instructions field and clicks Save, then a
  success toast includes the agent name and subsequent conversations use the
  updated instructions.
- AC-4 — Given a user who is not the author and has no EDIT permission, when they
  select the agent from the dropdown, then all form fields are not editable and a
  message indicating no access is shown.

---

### Deleting an agent

**Purpose:** Permanently remove an agent and its associated metadata from the
system.

**Preconditions / access:**
- Agent must be saved (non-ephemeral).
- User must be the agent's author, an admin, or have `DELETE` permission on the
  agent resource.

**UI elements (sourced from `DeleteButton.tsx`):**
- **Delete Agent** button — trash icon (`TrashIcon`), in the agent footer; visible
  only to users with delete permission; aria-label `com_ui_delete_agent`
- **Confirmation dialog** — `OGDialogTemplate` with:
  - Title: `com_ui_delete_agent`
  - Body: `com_ui_delete_agent_confirm` ("Are you sure you want to delete this agent?")
  - Confirm button: `com_ui_delete` (destructive red styling)

**Functional behavior:**
1. FR-1 — Clicking the trash button opens the confirmation dialog; no deletion
   occurs until confirmed.
2. FR-2 — Confirming calls `DELETE /api/agents/:id`; on success, a success toast
   `com_ui_agent_deleted` appears.
3. FR-3 — After deletion, the panel loads the next available agent in the list,
   or resets to a blank "Create New Agent" form if no agents remain.
4. FR-4 — If the deleted agent was the one in the active conversation, the
   conversation's `agent_id` is updated to the first available agent.
5. FR-5 — **CONFIRMED:** Knowledge files are **not** deleted from the vector
   database when an agent is deleted. `deleteAgentHandler` only calls
   `db.deleteAgent({ id })`; no RAG API delete call is made. Their pgvector
   embeddings remain orphaned after agent deletion.

**States & edge cases:**
- Delete API error: toast `com_ui_agent_delete_error` is shown; agent is not removed.
- Deleting an ephemeral agent: The Delete button is hidden (`isEphemeralAgent`
  check returns `null`).

**Acceptance criteria:**
- AC-1 — Given the user has DELETE permission, when they click the trash icon and
  cancel the dialog, then the agent is not deleted and the editor remains open.
- AC-2 — Given the user confirms deletion, then a success toast appears, the agent
  no longer appears in the selector dropdown, and the form resets.
- AC-3 — Given a user without DELETE permission, when they view the agent editor,
  then the trash icon button is not rendered.

---

### Sharing an agent

**Purpose:** Grant other users or groups access to view or use an existing agent.
Optionally make the agent public (available to all users).

**Preconditions / access:**
- Agent must be saved (non-ephemeral).
- The system must have `permissions.agents.share: true` configured for the user's
  role.
- The current user must be the author, an admin, or have the `SHARE` permission
  bit on the agent resource.

**UI elements (sourced from `AgentFooter.tsx`, `GenericGrantAccessDialog.tsx`):**
- **Share button** — `Share2Icon` icon button in the agent footer; aria-label
  `com_ui_share_var` ("Share {agent name}"). Shows a count badge when the agent
  is already shared with N principals.
- **Grant Access dialog** — opens on Share button click:
  - Title: "Share {agent name}" with a `Users` icon
  - **People search** — `UnifiedPeopleSearch` input; search for users/groups to add
  - **Permissions list** — shows existing shares with role; supports removing
    individuals
  - **Public sharing toggle** — `PublicSharingToggle`; when enabled, all users can
    see/use the agent (admin-controlled via `permissions.agents.allowSharePublic`)
  - **Save button** — applies changes

- **Remote Access button** — separate `Globe` icon button; opens a second
  `GenericGrantAccessDialog` with `ResourceType.REMOTE_AGENT`; grants access via
  the API (not UI chat). This allows external API consumers to use the agent.
  Only visible when `permissions.remote_agents.share: true`.

**Functional behavior:**
1. FR-1 — The Share button renders only when the user has `SHARE` permission and
   `hasAccessToShareAgents` is true.
2. FR-2 — After adding a user/group in the dialog and saving, those principals can
   see and use the agent from their own Agents endpoint.
3. FR-3 — The share count badge on the button increments to reflect the total
   number of principals with access.
4. FR-4 — Public sharing (if allowed) makes the agent visible to all authenticated
   users; the agent appears in their agent selector with a globe icon
   (`EarthIcon`, green).
5. FR-5 — The Duplicate Agent button (`CopyPlus` icon, `com_ui_duplicate_agent`)
   is separately available to users with EDIT permission; it creates a copy of the
   agent owned by the duplicating user, with a success toast
   `com_ui_agent_duplicated`.
6. FR-6 — Removing a user from the share list and saving revokes their access.

**States & edge cases:**
- No sharing permissions: Share button is not rendered.
- `permissions.agents.allowSharePublic: false`: The public toggle is hidden in
  the dialog; agents can only be shared with named individuals/groups.
- Sharing with oneself: Not expected to be prevented at the UI level; behavior
  is system-defined.

**Acceptance criteria:**
- AC-1 — Given the user has SHARE permission, when they click the Share button,
  then the Grant Access dialog opens showing a people search and existing shares.
- AC-2 — Given the user searches for and adds "User B" in the dialog and saves,
  then User B can find and select the agent from their own Agents endpoint.
- AC-3 — Given the user removes User B from the share list and saves, then User B
  can no longer access the agent.
- AC-4 — Given public sharing is enabled by admin, when the user toggles "share
  with everyone" and saves, then all authenticated users see the agent in their
  selector with a globe icon.
- AC-5 — Given the user has no SHARE permission, when they view the agent footer,
  then the Share icon button is not present in the DOM.
