# Verification findings — 05 Files (File Upload & Attachments)

## Summary

- Claims checked: 47 | CONFIRMED: 37 | WRONG: 7 | NEEDS-FIX: 2 | RUNTIME-ONLY: 1 | VERIFY-RESOLVED: 3

---

## Findings

### [WRONG] Attach Button — FR-1, AC-1: First dropdown item is "Upload to Provider", not "Upload Image"

**Spec says:** The Nufi endpoint attach dropdown shows at minimum **"Upload Image"** (`com_ui_upload_image_input`) and **"Upload as Text"** (`com_ui_upload_ocr_text`).

**Reality:** The Nufi endpoint is `EModelEndpoint.custom`, which is a member of `documentSupportedProviders`. The branch at `AttachFileMenu.tsx:164-185` uses `isDocumentSupportedProvider(endpointType)` to decide which first item to render. Because `custom` is in that set (`schemas.ts:53`), the first item rendered is **"Upload to Provider"** (`com_ui_upload_provider`) with icon `FileImageIcon`, not "Upload Image" with `ImageUpIcon`. The "Upload Image" label only appears for endpoints that are **not** document-supported.

**Evidence:**
- `client/src/components/Chat/Input/Files/AttachFileMenu.tsx:164-185`
- `packages/data-provider/src/schemas.ts:49-64`

**Suggested correction:** In FR-1 and AC-1, replace "Upload Image" (`com_ui_upload_image_input`) with "Upload to Provider" (`com_ui_upload_provider`) as the primary upload option for the Nufi endpoint.

---

### [WRONG] Attach Button — FR-2, AC-2: Accept filter for the primary upload option

**Spec says:** Clicking "Upload Image" sets the `accept` filter to `image/*,.heif,.heic`.

**Reality:** The Nufi endpoint uses the "Upload to Provider" path, which sets `fileType = 'image_document'` and triggers `inputRef.current.accept = 'image/*,.heif,.heic,.pdf,application/pdf'` — images **and** PDFs, not images-only.

**Evidence:**
- `client/src/components/Chat/Input/Files/AttachFileMenu.tsx:128-130` (image_document accept string)
- `client/src/components/Chat/Input/Files/AttachFileMenu.tsx:171-183` (fileType assigned as 'image_document' for custom endpoint)

**Suggested correction:** In FR-2 and AC-2, the accept attribute for the primary Nufi upload option is `image/*,.heif,.heic,.pdf,application/pdf`.

---

### [WRONG] Attach Button — "Upload as Text" option availability for Nufi endpoint

**Spec says:** The Nufi endpoint dropdown shows at minimum "Upload as Text" (`com_ui_upload_ocr_text`).

**Reality:** "Upload as Text" only renders when `capabilities.contextEnabled === true` (`AttachFileMenu.tsx:197`). `contextEnabled` is `true` only when `AgentCapabilities.context` is present in the agents endpoint capabilities array (`useAgentCapabilities.ts:41-43`). The `nufi-chat/librechat.yaml` sets `agents.capabilities: ["file_search"]` — `context` is absent. Therefore `contextEnabled = false` and "Upload as Text" is **not shown** in the Nufi endpoint attach menu unless the server-side agents config is changed.

**Evidence:**
- `client/src/components/Chat/Input/Files/AttachFileMenu.tsx:197-205`
- `client/src/hooks/Agents/useAgentCapabilities.ts:41-44`
- `client/src/hooks/Agents/useGetAgentsConfig.ts:22-32`
- `nufi-chat/librechat.yaml:34-36`

**Suggested correction:** The menu for the Nufi endpoint shows only "Upload to Provider" (and "Upload for File Search" when fileSearch is enabled). "Upload as Text" requires adding `context` to `agents.capabilities` in `librechat.yaml`.

---

### [WRONG] Drag-and-Drop — FR-3, FR-4: Modal appears for ALL files (not just images) when File Search is enabled

**Spec says (FR-3):** "For the Nufi endpoint, if the dragged files are images, the 'Select Upload Type' modal appears."

**Spec says (FR-4):** "If no modal is needed (e.g., non-image files where only one destination is valid), files are processed directly."

**Reality:** `useDragHelpers.ts:133-137` shows the modal whenever:
```
shouldShowModal = allImages || (fileSearchEnabled && fileSearchAllowedByAgent) || (codeEnabled && codeAllowedByAgent) || contextEnabled
```
With nufi-chat `agents.capabilities: ["file_search"]`, `fileSearchEnabled = true` and `fileSearchAllowedByAgent = true` (default when no agent is selected). So the modal appears for **any** dropped files — including non-image documents — not just for images.

**Evidence:**
- `client/src/hooks/Files/useDragHelpers.ts:108-145`
- `nufi-chat/librechat.yaml:34-36`

**Suggested correction:** Revise FR-3 and FR-4 to state that the modal appears whenever any enabled capability applies (images, file-search, etc.) — not only for images.

---

### [WRONG] Drag-and-Drop — FR-3: DragDropModal shows "Upload to Provider", not "Upload Image"

**Spec says (FR-3):** The "Select Upload Type" modal offers "Upload Image" for the Nufi endpoint.

**Reality:** `DragDropModal.tsx:77-118` applies the same `isDocumentSupportedProvider(endpointType)` test. For the Nufi custom endpoint, the first option label is `localize('com_ui_upload_provider')` ("Upload to Provider"), not `localize('com_ui_upload_image_input')` ("Upload Image"). The "Upload Image" label only renders when the provider is NOT document-supported.

**Evidence:**
- `client/src/components/Chat/Input/Files/DragDropModal.tsx:77-118`
- `packages/data-provider/src/schemas.ts:49-64`

**Suggested correction:** In FR-3 (Drag-and-Drop section), replace "Upload Image" with "Upload to Provider" as the modal option for the Nufi endpoint.

---

### [WRONG] File Preview & Removal — AC-6: CSV chip label is "Document", not "Spreadsheet"

**Spec says (AC-6):** "Spreadsheet for CSV" in the document chip type label.

**Reality:** `getFileType()` in `client/src/utils/files.ts:108-138` resolves `text/csv` as follows:
1. No direct match in `fileTypes['text/csv']`.
2. `excelMimeTypes` regex does not match `text/csv`.
3. Partial match `'text/x-'` does not match.
4. Category split yields `'text'` → `fileTypes['text'] = textDocument` → `title: 'Document'`.

The key `fileTypes.csv` exists (→ `spreadsheet`) but is only reachable if the type string is literally `'csv'` (a bare string, not a MIME type), which never occurs from browser file uploads.

**Evidence:**
- `client/src/utils/files.ts:60-138` (fileTypes map and getFileType logic)
- `client/src/utils/files.ts:32-34` (spreadsheet title defined)

**Suggested correction:** CSV files show the label **"Document"** (via the `text` category fallback), not "Spreadsheet". The "Spreadsheet" label appears only for Excel MIME types matching `excelMimeTypes` regex. Update AC-6 accordingly.

---

### [WRONG] Validation — FR-7 / error message: Duplicate error uses i18n key, not raw string

**Spec says (FR-7):** Reject with `com_error_files_dupe` → "Duplicate file detected." — the note acknowledges the raw-string vs i18n distinction applies to FR-3–FR-6 only.

**Reality:** This is actually **consistent** with code (`files.ts:314` calls `setError('com_error_files_dupe')`; the `displayToast` in `useFileHandling.ts:84-104` runs `localize(error)` which resolves it to "Duplicate file detected."). However, **the spec table in the Validation section lists the duplicate error as "Duplicate file detected."** (translated text) while the actual raw value set in `setError` is the i18n key `com_error_files_dupe`. This is internally consistent (because localize resolves it) but the spec's explanatory note on FR-3–FR-6 being "raw strings" implies FR-7 is a key — this nuance is already captured in the spec. **No action needed.**

---

### [NEEDS-FIX] Validation — FR-3: Count error format omits literal newline; FR-2 empty error resolves via i18n

**Spec says (FR-3):** Error shown is `"File limit reached: 5 files"` (raw string). Spec note correctly states count, MIME, size, and total-size messages are raw strings, not i18n keys.

**Reality:** Confirmed — `files.ts:254`: `setError(\`File limit reached: ${fileLimit} files\`)`. The `displayToast` path then tries `localize(error)` on this raw string, which fails gracefully and falls back to the raw string itself. The displayed toast is therefore exactly `"File limit reached: 5 files"` ✓

**For FR-2 (empty):** `setError('com_error_files_empty')` → localized to "Empty files are not allowed." The spec error table correctly lists the translated text.

**Note:** The spec note is correct that count/MIME/size/total use raw strings while disabled/empty/dupe use i18n keys. Only minor wording inconsistency: the spec table shows translated text for all rows, which could confuse testers who look at toast text vs. code key.

**Evidence:** `client/src/utils/files.ts:247-298`

**Suggested correction:** Add a footnote to the error table clarifying which rows show i18n-resolved text and which are verbatim raw strings.

---

### [NEEDS-FIX] Upload States — FR-2: Progress step 0.2 is skipped for HEIC/processed files

**Spec says (FR-2):** "For images, progress advances to 0.2 (ready for upload), then 0.6 (image dimensions loaded)…"

**Reality:** The `0.2` step only occurs for files that are **not** HEIC-processed (the `else` branch in `useFileHandling.ts:410-426`). For HEIC-processed or resized files, progress goes from `0.1` → intermediate HEIC conversion values (0.1–0.5 range) → `0.5` (processing complete) → `0.6` (loadImage) → `0.9` → `1.0`. The `0.2` step is absent for those files.

**Evidence:**
- `client/src/hooks/Files/useFileHandling.ts:344-405` (HEIC/processed path, no 0.2 step)
- `client/src/hooks/Files/useFileHandling.ts:410-426` (non-processed path: 0.2 set)

**Suggested correction:** Add a note that the 0.2 step applies only to non-HEIC files; HEIC/processed files follow a different intermediate progress track (0.1 → HEIC-conversion range 0.1–0.5 → 0.5 → 0.6 → 0.9 → 1.0).

---

### [VERIFY-RESOLVED] File Preview & Removal — delete failure silently swallowed

**Spec (verify marker):** "the server may return an error that is silently swallowed client-side."

**Resolution: CONFIRMED.** `FileRow.tsx:53-55`: `onError: (error) => { console.log('Error deleting files:', error); }` — the error is only logged to the console. No toast or user-visible error is surfaced on delete failure.

**Evidence:** `client/src/components/Chat/Input/Files/FileRow.tsx:53-55`

---

### [VERIFY-RESOLVED] Images vs Documents — GIF animated behavior

**Spec (FR-5, verify marker):** "animated GIF behavior depends on the provider API — the model may not animate them."

**Resolution: RUNTIME-ONLY.** The client sends GIF files as-is via the upload API; whether the provider preserves animation is entirely server/API-side behavior. No client-side conversion or stripping of GIF frames occurs. Cannot be confirmed from code alone — requires runtime test against the target provider.

---

### [VERIFY-RESOLVED] clientImageResize enabled on Nufi production

**Spec (verify marker):** "whether this is enabled on NuFi production deployment."

**Resolution: CONFIRMED DISABLED (by default).** `nufi-chat/librechat.yaml` does not configure `fileConfig.clientImageResize`. The LibreChat default is `clientImageResize.enabled: false` (`packages/data-provider/src/file-config.ts:436-441`). Therefore, the resize toast ("Image resized: X MB → Y MB") will **not** appear on the current Nufi deployment. The resize code path in `useFileHandling.ts:362-382` is present but inactive.

**Evidence:**
- `packages/data-provider/src/file-config.ts:436-441`
- `nufi-chat/librechat.yaml` (no `clientImageResize` entry)

---

## Confirmed Items (selected, non-exhaustive)

| Item | Verdict |
|---|---|
| fileLimit=5, fileSizeLimit=20MB, totalSizeLimit=50MB in librechat.yaml | CONFIRMED (`nufi-chat/librechat.yaml`) |
| supportedMimeTypes list (PNG, JPEG, WebP, GIF, PDF, text/plain, text/markdown, text/csv, docx, JSON) | CONFIRMED (exact strings in librechat.yaml) |
| fileSizeLimit converted via `mbToBytes()` — yaml value 20 → 20971520 bytes | CONFIRMED (`file-config.ts:758-759`) |
| `>=` boundary: exactly 20 MB rejected | CONFIRMED (`files.ts:289`) |
| total size check is `>` (not `>=`): exactly 50 MB allowed | CONFIRMED (`files.ts:295`) |
| Disabled check uses i18n key `com_ui_attach_error_disabled` | CONFIRMED (`files.ts:243`) |
| Empty check: combined incoming size === 0; key `com_error_files_empty` | CONFIRMED (`files.ts:247-249`) |
| MIME check calls `inferMimeType` then `checkType` against endpoint's regex list | CONFIRMED (`files.ts:260-287`) |
| Duplicate detection: `name-size-typeCategory` composite key | CONFIRMED (`files.ts:300-316`) |
| Validation exception: `com_error_files_validation` raw key → "An error occurred while validating the file." | CONFIRMED (`useFileHandling.ts:297`, `translation.json:366`) |
| Upload delay timer: base 5 s + 2 s per MB (using 1,000,000 bytes/MB) | CONFIRMED (`useDelayedUploadToast.ts:10-13`) |
| Upload delay toast: status 'warning' (yellow), i18n key `com_ui_upload_delay` | CONFIRMED (`useDelayedUploadToast.ts:24-28`) |
| Upload success: 300 ms delay before progress reaches 1.0 | CONFIRMED (`useFileHandling.ts:135-156`) |
| Upload error: uses `response.data.message` if present, else `com_error_files_upload` | CONFIRMED (`useFileHandling.ts:173-179`) |
| Upload canceled: `com_error_files_upload_canceled` key | CONFIRMED (`useFileHandling.ts:176`) |
| HEIC conversion toast: `com_info_heic_converting` → "Converting HEIC image to JPEG..." (status 'info') | CONFIRMED (`useFileHandling.ts:337-342`, `translation.json:401`) |
| HEIC conversion failure: `com_error_heic_conversion` key | CONFIRMED (`useFileHandling.ts:431`, `translation.json:368`) |
| General processing error: `com_error_files_process` | CONFIRMED (`useFileHandling.ts:433`, `translation.json:362`) |
| Paste rename: `clipboard_<timestamp>_<originalName>` | CONFIRMED (`useTextarea.ts:224`) |
| Paste with files prevents text insertion (files branch taken when `clipboardData.files.length > 0`) | CONFIRMED (`useTextarea.ts:220-230`) |
| Remove button: `aria-label` = `localize('com_ui_attach_remove')` = "Remove file" | CONFIRMED (`RemoveFile.tsx:6`) |
| Image chip: 56×56 px (`size-14`), lightbox uses `max-h-[85vh] max-w-[90vw]` | CONFIRMED (`ImagePreview.tsx:117`, `ImagePreview.tsx:192`) |
| Lightbox backdrop: `bg-black/90` | CONFIRMED (`ImagePreview.tsx:161`) |
| Escape key closes lightbox (manual listener + Radix Dialog) | CONFIRMED (`ImagePreview.tsx:74-83`) |
| FileContainer width: `w-56` = 224 px | CONFIRMED (`FileContainer.tsx:56`) |
| Chip deduplication by `file_id` | CONFIRMED (`FileRow.tsx:103-108`) |
| "Deleting file..." toast on remove of fully uploaded file: `com_ui_deleting_file`, status 'info' | CONFIRMED (`FileRow.tsx:118-122`) |
| Image chips show ProgressCircle (`progress < 1`), Maximize2 overlay (`progress >= 1`) | CONFIRMED (`ImagePreview.tsx:132-154`) |
| FilePreview shows Spinner overlaid on file icon when `progress < 1` | CONFIRMED (`FilePreview.tsx:24-30`) |
| isImage determined by `file.type?.startsWith('image')` | CONFIRMED (`FileRow.tsx:126`) |
| DragDropOverlay heading: `com_ui_upload_files` = "Upload files" | CONFIRMED (`DragDropOverlay.tsx:92`) |
| DragDropOverlay sub-heading: `com_ui_drag_drop` = "Drop any file here to add it to the conversation" | CONFIRMED (`DragDropOverlay.tsx:93`, `translation.json:974`) |
| DragDropModal title: `com_ui_upload_type` = "Select Upload Type" | CONFIRMED (`DragDropModal.tsx:161`) |
| Endpoint disabled check in drag-drop runs before modal, shows toast | CONFIRMED (`useDragHelpers.ts:94-100`) |
| "Upload for File Search" shown when `fileSearchEnabled && fileSearchAllowedByAgent` | CONFIRMED (`AttachFileMenu.tsx:208-221`) |
| Agent Knowledge via "Upload for File Search" routes to `EToolResources.file_search` | CONFIRMED (`AttachFileMenu.tsx:212-219`) |
| Attach menu `id="attach-file-menu"` (via `menuId` prop) | CONFIRMED (`AttachFileMenu.tsx:314`) |
| Attach menu button `aria-label="Attach File Options"` | CONFIRMED (`AttachFileMenu.tsx:279`) |
| Button `aria-label` uses `com_sidepanel_attach_files` for tooltip | CONFIRMED (`AttachFileMenu.tsx:291`) |
| PDF → title "Document" (via `application/pdf` direct key in fileTypes) | CONFIRMED (`files.ts:75`) |
