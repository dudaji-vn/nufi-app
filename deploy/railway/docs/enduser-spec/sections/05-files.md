## File Upload & Attachments

> **Scope note — per-message attachments only.** This section covers files attached directly to a chat message (conversation-scoped). These files are uploaded as context for a single interaction: images are sent as vision input; documents are sent as text context for that message exchange. This is distinct from **Agent Knowledge** (persistent RAG via file search / vector store), which is covered in the Agents section. When in doubt about which mechanism to use, see [Relationship to Agent Knowledge](#relationship-to-agent-knowledge) below.

---

### Attach Button

#### Purpose
Provides the primary entry point for selecting local files to attach to the current message before sending.

#### Preconditions / access
- A conversation must be open (or "New Chat" must be selected with the Nufi endpoint active).
- The Nufi endpoint must be selected; file upload is disabled for endpoints that explicitly set `disabled: true`.
- The input area must not be in a disabled state (e.g., while a response is being generated).

#### UI elements
- **Attach Files** button (paperclip icon, `aria-label="Attach Files"`, tooltip label `com_sidepanel_attach_files` → "Attach Files") located in the chat input toolbar.
- On the Nufi endpoint (a custom, non-Assistants endpoint that supports files), clicking the button opens a **dropdown menu** (`id="attach-file-menu"`, `aria-label="Attach File Options"`) rather than a direct file picker.
- The dropdown lists upload destination options depending on endpoint capabilities (see Supported Types section). For the Nufi endpoint the menu shows at minimum: **"Upload to Provider"** (`com_ui_upload_provider`). The "Upload as Text" option (`com_ui_upload_ocr_text`) is **absent** for the Nufi endpoint because `context` capability is not enabled in the server configuration (`agents.capabilities` does not include `context`).
- The hidden `<input type="file">` is opened programmatically when a menu item is chosen.
- Keyboard: the attach button responds to `Enter` or `Space` to open the file picker.

#### Functional behavior
1. FR-1: When the user clicks the Attach Files button, a dropdown menu appears listing at least the upload type options applicable to the Nufi endpoint.
2. FR-2: Clicking a menu item sets the `accept` filter on the hidden file input (`image/*,.heif,.heic,.pdf,application/pdf` for "Upload to Provider"; unrestricted for other types) and opens the OS file picker.
3. FR-3: After the OS file picker is dismissed, the selected files pass through client-side validation (see Validation section). Files that pass are immediately shown as in-progress chips in the input area.
4. FR-4: The Attach Files button is visually disabled (rendered with `disabled` attribute) while `disableInputs` is true (e.g., during message generation).
5. FR-5: Selecting a menu item and cancelling the OS file picker without choosing a file has no effect; no error is shown.

#### Validation & errors
- If uploads are disabled by server config: toast error "File uploads are disabled for this endpoint" (`com_ui_attach_error_disabled`).
- All further validation is described in [Validation & Error Handling](#validation--error-handling).

#### Edge cases
- If no conversation is active (e.g., no endpoint selected), the button may be absent or disabled; the user sees the toast "Cannot attach file. Create or select a conversation, or try refreshing the page." (`com_ui_attach_error`).
- If the user opens the menu but clicks outside to dismiss, the picker does not open.

#### Acceptance criteria
1. AC-1: Given the Nufi endpoint is active and inputs are enabled, when the user clicks the Attach Files button, then a dropdown menu appears with at least the "Upload to Provider" option (and "Upload for File Search" when file search is enabled). "Upload as Text" is not shown for the Nufi endpoint in its current configuration.
2. AC-2: Given the dropdown is open, when the user selects "Upload to Provider", then the OS file picker opens filtered to `image/*,.heif,.heic,.pdf,application/pdf`.
3. AC-3: Given the input area is disabled (message generating), when the button is rendered, then it has the `disabled` attribute and clicking it has no effect.
4. AC-4: Given a file upload is disabled by endpoint config, when the user attempts to open the file picker, then a red toast "File uploads are disabled for this endpoint" appears.

---

### Drag-and-Drop

#### Purpose
Allows users to drop files from the desktop or file manager anywhere on the chat area without using the attach button.

#### Preconditions / access
- A conversation must be open with the Nufi endpoint active.
- File uploads must not be disabled for the endpoint.

#### UI elements
- The entire chat area (wrapped in `DragDropWrapper`) acts as a drop target.
- While a file is being dragged over the window, a **full-screen semi-transparent overlay** (`DragDropOverlay`) appears with:
  - An upload illustration (SVG graphic).
  - Heading: **"Upload files"** (`com_ui_upload_files`).
  - Sub-heading: **"Drop any file here to add it to the conversation"** (`com_ui_drag_drop`).
- If the dropped file(s) trigger multiple possible destinations (e.g., images that could go to different tool resources), a **"Select Upload Type"** modal (`com_ui_upload_type`) appears offering buttons for each destination.

#### Functional behavior
1. FR-1: When the user drags a file over the application window, the overlay becomes visible with the upload illustration and instructional text.
2. FR-2: When the user releases (drops) the file(s), if the endpoint's upload is disabled a toast error is shown immediately without showing the modal.
3. FR-3: For the Nufi endpoint, the "Select Upload Type" modal appears for **any** dropped file type whenever at least one upload capability applies — not only for images. Because `file_search` is enabled in the Nufi configuration (`fileSearchEnabled = true`, `fileSearchAllowedByAgent = true` by default), the modal is shown for images, documents, and all other supported file types. The modal's primary option for the Nufi endpoint is **"Upload to Provider"** (`com_ui_upload_provider`). The user must click an option to proceed.
4. FR-4: Files are processed directly (without the modal) only when no capability condition is met. Under the current Nufi configuration (`file_search` enabled), the modal always appears for dropped files, so this bypass path is not active.
5. FR-5: After the user selects an option in the modal (or files are processed directly), the same validation and upload flow used for button-selected files applies.
6. FR-6: The overlay disappears when the user moves the dragged item outside the drop area or drops it.

#### Validation & errors
- The endpoint disabled check runs before the modal is displayed; if the endpoint is disabled, a toast error appears instead of the modal.
- All further validation (type, size, count) runs after the modal option is selected, through the same `validateFiles` pipeline.

#### Edge cases
- Dropping a folder (no files) results in no action (the browser does not expose directory contents through the `FileList` API in this flow).
- Dropping an unsupported file type: with `file_search` enabled, the modal still appears; the unsupported type is caught in validation after option selection, showing the error toast.
- Dropping more files than the per-message file limit: caught in validation after option selection.

#### Acceptance criteria
1. AC-1: Given the chat area is displayed and uploads are enabled, when the user drags a file over the window, then the drag-drop overlay with the upload illustration appears.
2. AC-2: Given the overlay is shown, when the user drops any file (image or document), then the "Select Upload Type" modal appears (because `file_search` is enabled for the Nufi endpoint).
3. AC-3: Given the modal is shown, when the user clicks "Upload to Provider", then the file begins uploading and a progress chip appears in the input area.
4. AC-4: Given uploads are disabled by endpoint config, when the user drops a file, then a red toast "File uploads are disabled for this endpoint" appears and no modal is shown.
5. AC-5: Given the user drags a file to the window then drags it back out without dropping, then the overlay disappears and no file is attached.

---

### Paste Image

#### Purpose
Allows users to paste image data directly from the clipboard (e.g., a screenshot or copied image) into the message text area.

#### Preconditions / access
- The message text area (`data-testid="text-input"`) must be focused.
- The Nufi endpoint must support image uploads.
- The clipboard must contain file data (not just text).

#### UI elements
- No dedicated UI element: paste is triggered by the native clipboard shortcut (Cmd+V / Ctrl+V) while the text area is focused.
- After paste, the attached image appears as a preview chip (same as button-uploaded images).

#### Functional behavior
1. FR-1: When the user pastes while the text area is focused and the clipboard contains one or more files, the app reads `clipboardData.files` and initiates file handling for each file.
2. FR-2: Each pasted file is renamed to `clipboard_<timestamp>_<originalName>` before processing; this ensures pasted images have a stable, unique name for deduplication.
3. FR-3: Pasted files pass through the same `validateFiles` pipeline (MIME check, size check, count check, total size check).
4. FR-4: If the clipboard contains only text, the normal text paste behavior occurs; no file upload is triggered.
5. FR-5: HEIC/HEIF images pasted from clipboard are converted to JPEG before upload (see HEIC handling in Image vs Document section).

#### Validation & errors
- All validation is identical to the button upload path; see [Validation & Error Handling](#validation--error-handling).
- An unsupported pasted file type shows the toast "Unsupported file type: `<mime>`".

#### Edge cases
- Pasting multiple images at once: each image is processed individually; count and total size limits apply to the combined set.
- Pasting a screenshot: browsers typically expose it as `image/png` — passes MIME validation on the Nufi endpoint.
- Pasting a file whose type the browser cannot determine: MIME inference from extension is attempted; if inference fails the file is rejected with "Unable to determine file type for: `<filename>`".

#### Acceptance criteria
1. AC-1: Given the text area is focused, when the user pastes an image from the clipboard, then an image preview chip appears in the input area and the file begins uploading.
2. AC-2: Given the text area is focused, when the user pastes plain text, then normal text insertion occurs and no upload is triggered.
3. AC-3: Given the text area is focused, when the user pastes an image that exceeds 20 MB, then a red toast "File size limit exceeded: 20 MB" appears and no chip is added.
4. AC-4: Given 5 files are already attached, when the user pastes a 6th image, then a red toast "File limit reached: 5 files" appears and the paste is rejected.

---

### Supported Types & Limits

#### Purpose
Defines which files the Nufi endpoint accepts and the hard limits enforced at the time of selection.

#### Preconditions / access
- Limits apply every time a file selection, drag-drop, or paste occurs on the Nufi endpoint.

#### UI elements
- No dedicated UI element displaying limits to the user before attachment is attempted; limits are surfaced via toast error messages at validation time.

#### Functional behavior
The following limits are active on the **Nufi** endpoint (sourced from deployed server configuration):

| Limit | Value |
|---|---|
| Maximum files per message | **5** |
| Maximum size per file | **20 MB** (exclusive boundary: file must be strictly less than 20 MB) |
| Maximum total size per request | **50 MB** |

Supported MIME types (the MIME is checked against the `supportedMimeTypes` regex list configured for the Nufi endpoint):

| Type | MIME |
|---|---|
| PNG image | `image/png` |
| JPEG image | `image/jpeg` |
| WebP image | `image/webp` |
| GIF image | `image/gif` |
| PDF document | `application/pdf` |
| Plain text | `text/plain` |
| Markdown | `text/markdown` |
| CSV | `text/csv` |
| Word document (.docx) | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` |
| JSON | `application/json` |

> **Note on HEIC/HEIF:** When uploaded via the "Upload to Provider" option, HEIC/HEIF files are converted client-side to JPEG before validation and upload, so the resulting MIME is `image/jpeg`. HEIC is accepted as an image source format even though `image/heic` is not in the Nufi supported list because conversion happens pre-validation.

> **Note on size boundary:** The `fileSizeLimit` check uses `>=` (strict), so a file of exactly 20 MB is rejected. Only files strictly below 20 MB are accepted.

#### Validation & errors
See [Validation & Error Handling](#validation--error-handling) for the full error message table.

#### Edge cases
- A file whose extension is recognized but whose browser-reported MIME type is empty: `inferMimeType` resolves the MIME from the extension before the type check.
- A file with an unrecognized extension and an empty MIME: rejected with "Unable to determine file type for: `<filename>`".

#### Acceptance criteria
1. AC-1: Given the Nufi endpoint is active, when the user attaches an `image/png` file of 5 MB, then the file is accepted and begins uploading.
2. AC-2: Given the Nufi endpoint is active, when the user attaches a file of exactly 20 MB, then validation rejects it with "File size limit exceeded: 20 MB".
3. AC-3: Given the Nufi endpoint is active, when the user attaches a file of 19.9 MB, then the file is accepted and begins uploading.
4. AC-4: Given the Nufi endpoint is active, when the user attaches a `.docx` file, then the file is accepted.
5. AC-5: Given the Nufi endpoint is active, when the user attaches an `.mp4` video file, then validation rejects it with "Unsupported file type: video/mp4".
6. AC-6: Given the Nufi endpoint is active, when the combined size of already-attached files plus a new file exceeds 50 MB, then the new file is rejected with "Total file size limit exceeded: 50 MB".

---

### Upload States (Progress, Success, Error)

#### Purpose
Provides real-time visual feedback during the file upload lifecycle from selection to server confirmation.

#### Preconditions / access
- A file has passed client-side validation and a chip has been added to the input area.

#### UI elements
- **In-progress image chip:** A 56×56 px thumbnail with a circular progress indicator (`ProgressCircle`) overlaid. Progress is shown as a stroke-dashoffset arc that animates as `progress` goes from `0` to `1`. For non-HEIC images the steps are: `0.1` initial → `0.2` ready for upload → `0.6` image dimensions loaded → `0.9` server acknowledged → `1.0` complete. For HEIC/processed images the `0.2` step is skipped; progress follows: `0.1` → HEIC-conversion range (0.1–0.5) → `0.5` processing complete → `0.6` image loaded → `0.9` server acknowledged → `1.0` complete.
- **In-progress document chip:** A `FileContainer` chip (224 px wide) with a `Spinner` overlaid on the file-type icon (visible when `file.progress < 1`).
- **Upload delay warning:** After an upload takes longer than a threshold (base 5 seconds + 2 seconds per MB of file size), a yellow toast appears: `"Uploading \"<filename>\" is taking more time than anticipated. Please wait while the file finishes indexing for retrieval."` (`com_ui_upload_delay`).
- **Success state:** Progress reaches `1.0`; the spinner/progress arc disappears; the chip renders the file thumbnail or document icon normally. No explicit "success" toast is shown for per-message attachments.
- **Error state:** The chip is removed from the list; a red toast appears with the relevant error message (see below).

#### Functional behavior
1. FR-1: Immediately after validation passes, a chip is added to the input area with `progress = 0.1` (processing state), giving instant visual feedback before the upload request is made.
2. FR-2: For non-HEIC images, progress advances to `0.2` (ready for upload), then `0.6` (image dimensions loaded), then `0.9` (server responded), then `1.0` after a 300 ms delay. For HEIC/processed images, the `0.2` step is absent; progress goes from `0.1` through the HEIC-conversion range (0.1–0.5), to `0.5` (processing complete), `0.6` (image loaded), `0.9` (server responded), then `1.0` after 300 ms.
3. FR-3: For documents, progress advances from `0.1` to server-acknowledged `0.9` then `1.0` after 300 ms.
4. FR-4: If the upload takes longer than the threshold, a yellow warning toast appears (see UI elements); the upload continues.
5. FR-5: On server error, the chip is removed and a red toast "An error occurred while uploading the file." (`com_error_files_upload`) appears, or the server's `response.data.message` if present.
6. FR-6: The `setFilesLoading` state is `true` while any file has `progress < 1`, blocking message submission.

#### Validation & errors
- Upload network error: toast "An error occurred while uploading the file."
- Upload canceled (abort): toast "The file upload request was canceled. Note: the file upload may still be processing and will need to be manually deleted." (`com_error_files_upload_canceled`).
- HEIC conversion failure: toast "Failed to convert HEIC image to JPEG. Please try converting the image manually or use a different format." (`com_error_heic_conversion`).
- General processing error: toast "An error occurred while processing the file." (`com_error_files_process`).

#### Edge cases
- If the user removes the chip while the upload is in progress, `abortUpload()` is called which cancels the HTTP request via `AbortController`; a cancel toast appears.
- If multiple files are uploading simultaneously and one fails, only that file's chip is removed; other uploads continue.
- If the upload success returns a different `file_id` than the `temp_file_id`, the preview cache entry is migrated to the new ID so the image thumbnail persists.

#### Acceptance criteria
1. AC-1: Given a valid file is selected, when it is added to the input area, then a progress chip appears immediately with a spinner/arc overlay.
2. AC-2: Given a file is uploading, when the server returns a success response, then the spinner/arc disappears and the chip shows the fully rendered thumbnail or document icon.
3. AC-3: Given a file upload takes more than 5 seconds, then a yellow warning toast containing the filename appears.
4. AC-4: Given a file upload fails due to a network error, then the chip is removed and a red toast "An error occurred while uploading the file." appears.
5. AC-5: Given a file is uploading, when the user clicks the remove button on the chip, then the upload is canceled and a cancel toast appears.

---

### File Preview & Removal

#### Purpose
Allows users to inspect attached files before sending and remove unwanted attachments.

#### Preconditions / access
- At least one file has been added (even while uploading) to the current message.

#### UI elements
- **Image chip:** A rounded square (56×56 px, class `rounded-2xl`) showing the image as a background. On hover, a semi-transparent dark overlay with a `Maximize2` (expand) icon appears. Clicking opens a full-screen lightbox (`DialogPrimitive.Root`) over a `bg-black/90` backdrop, with the image at `max-h-[85vh] max-w-[90vw]`. A close button (`aria-label="Close"`) is in the top-right of the lightbox; pressing Escape also closes it.
- **Document chip (`FileContainer`):** A 224 px wide chip with a rounded-rectangle border. Left side: file-type icon (e.g., document, spreadsheet, code). Right side: filename (truncated with `title` tooltip for long names) and file-type label (e.g., "Document", "Spreadsheet", "Code").
- **Remove button:** A small circular `×` button (`aria-label="Remove file"`, translation key `com_ui_attach_remove`) positioned at the top-right corner of each chip (visible at all times, not just on hover). Clicking it deletes the file.
- **Source badge:** A small icon in the bottom-right corner of the file icon area indicating the file source (e.g., OpenAI logo for OpenAI-sourced files, "T" for text-extracted files, database icon for vector-store files). For local uploads on the Nufi endpoint this badge is typically absent.
- **Deleting state:** When the remove button is clicked on a fully uploaded file, a blue info toast "Deleting file..." (`com_ui_deleting_file`) appears briefly while the server deletion request runs.

#### Functional behavior
1. FR-1: Image chips render the image as a CSS `background-image`. Clicking the chip (when fully uploaded, `progress === 1`) opens the full-screen lightbox.
2. FR-2: Document chips display the filename and a human-readable type label derived from the MIME type (e.g., `application/pdf` → "Document", `text/csv` → "Document", code types → "Code"). Note: CSV files resolve to the "Document" label via the `text` category fallback in `getFileType()`; the "Spreadsheet" label applies only to Excel MIME types matching the `excelMimeTypes` regex.
3. FR-3: The remove button is present on every chip regardless of upload state. If the file is still uploading (`progress < 1`), clicking remove aborts the upload. If upload is complete, a server delete request is sent.
4. FR-4: Duplicate file IDs within the chip list are deduplicated; each unique `file_id` is rendered once.
5. FR-5: Chips are laid out in a wrapping flex row (`gap-4px`, `flexBasis: 70px` per chip slot); images and documents can appear together in the same row.

#### Validation & errors
- If the delete API call fails, the error is silently swallowed client-side: `FileRow.tsx` logs it to the console only (`console.log('Error deleting files:', error)`) and no toast or other user-visible feedback is shown on delete failure.

#### Edge cases
- Removing the last file: the chip area collapses; `setFilesLoading(false)` is called.
- Very long filenames: truncated with CSS `overflow: hidden; text-overflow: ellipsis`; full name available via `title` tooltip.
- Clicking the chip thumbnail for a file still uploading: the lightbox does not open (the expand overlay is only shown when `progress >= 1`); instead, the progress arc is shown.

#### Acceptance criteria
1. AC-1: Given an image file is fully uploaded, when the user clicks the image chip, then a full-screen lightbox opens displaying the image.
2. AC-2: Given the lightbox is open, when the user presses Escape or clicks the close button, then the lightbox closes.
3. AC-3: Given any chip is present, when the user clicks the remove button (aria-label "Remove file"), then the chip is removed from the input area.
4. AC-4: Given a file is still uploading, when the user clicks the remove button, then the upload is aborted and the chip disappears without a delete API call.
5. AC-5: Given a fully uploaded file, when the user clicks the remove button, then a blue info toast "Deleting file..." appears and the chip is removed.
6. AC-6: Given a document file is attached, the chip displays the filename and a type label (e.g., "Document" for PDF, "Document" for CSV, "Code" for script files). The "Spreadsheet" label does not appear for CSV files.

---

### Images (Vision) vs Documents (Text Context)

#### Purpose
Clarifies how different attachment types are used by the model and which upload menu option to choose.

#### Preconditions / access
- Nufi endpoint must be selected. Vision behavior depends on the selected model supporting multimodal input (verify: not all models on the Nufi endpoint are necessarily vision-capable — check model documentation).

#### UI elements
- **"Upload to Provider"** option (`com_ui_upload_provider`) in the attach menu: routes the file as a direct provider image/document input. File input filter is set to `image/*,.heif,.heic,.pdf,application/pdf`.
- **"Upload as Text"** option (`com_ui_upload_ocr_text`): **not available on the Nufi endpoint** in its current configuration. This option only appears when `AgentCapabilities.context` is present in `agents.capabilities`; the Nufi `librechat.yaml` sets `agents.capabilities: ["file_search"]` — `context` is absent.

#### Functional behavior
1. FR-1: Files added via "Upload to Provider" are sent to the model as image/document content blocks. The model can "see" images if it supports vision; PDFs are passed as document content.
2. FR-2: The "Upload as Text" path (OCR/document parsing to `context` tool resource) is not available on the Nufi endpoint in its current configuration. To enable it, `context` must be added to `agents.capabilities` in `librechat.yaml`.
3. FR-3: In `FileRow`, any file whose `type` starts with `image/` is rendered as an `Image` chip (thumbnail preview); all others are rendered as `FileContainer` (document chip).
4. FR-4: The source badge on the chip reflects how the file was processed (e.g., "T" badge for text-source files).
5. FR-5: GIF images attached via "Upload to Provider" are sent as static image frames. (requires manual verification on the running product: animated GIF behavior depends on the provider API — the model may not animate them.)

#### Validation & errors
- Attaching a non-image/non-PDF file via the "Upload to Provider" path: the OS file picker filter (`image/*,.heif,.heic,.pdf,application/pdf`) restricts selection; if the filter is bypassed, the MIME check in `validateFiles` will reject the unsupported type.
- "Upload as Text" is not available on the Nufi endpoint in the current configuration; the scenario of bypassing it does not apply.

#### Edge cases
- A `.gif` file uploaded via "Upload to Provider": accepted (MIME `image/gif` is supported). Treated as a static image by most vision APIs.
- An `.webp` file: accepted via "Upload to Provider" (MIME `image/webp` supported).
- A HEIC/HEIF image: converted to JPEG client-side (toast "Converting HEIC image to JPEG..."); the converted JPEG is then uploaded.
- A large image that exceeds 20 MB before HEIC conversion: if the converted JPEG is also ≥ 20 MB, it is rejected post-conversion.
- Client-side image resizing: `clientImageResize` is **disabled** on the Nufi deployment (no `clientImageResize` entry in `nufi-chat/librechat.yaml`; the LibreChat default is `clientImageResize.enabled: false`). The resize code path and the "Image resized: X MB → Y MB (Z% smaller)" toast are therefore inactive on the current Nufi production deployment.

#### Acceptance criteria
1. AC-1: Given a vision-capable model is selected on the Nufi endpoint, when the user attaches a PNG image via "Upload to Provider" and sends the message, then the model responds with awareness of the image content.
2. AC-2: "Upload as Text" is not available on the Nufi endpoint in its current configuration; this scenario requires adding `context` to `agents.capabilities` in `librechat.yaml`. (requires manual verification on the running product: if `context` capability is later enabled, attaching a PDF via "Upload as Text" and sending should result in the model's response referencing the document content.)
3. AC-3: Given a HEIC file is selected via "Upload to Provider", then a blue info toast "Converting HEIC image to JPEG..." appears, and the file chip shows a JPEG preview after conversion.
4. AC-4: Given a non-image/non-PDF file (e.g., CSV) is attached via "Upload to Provider" (if the OS picker filter is bypassed), then validation rejects it with "Unsupported file type: text/csv".

---

### Validation & Error Handling

#### Purpose
Describes the complete client-side validation pipeline and the exact error behavior for each failure condition.

#### Preconditions / access
- Triggered on every file selection (button, drag-drop, paste) before upload begins.

#### UI elements
- All validation errors are shown as red toast notifications (status `'error'`, duration 5000 ms).
- Multiple errors are deduplicated and, if more than one, displayed as a bullet list in a single toast.
- Error messages are rendered via the localization system.

#### Functional behavior
Validation is performed by `validateFiles()` in the order listed below. The pipeline returns `false` on the first failing check (except for MIME and size checks which iterate the file list):

1. FR-1 (Endpoint disabled): If `endpointFileConfig.disabled === true`, reject with `com_ui_attach_error_disabled`.
2. FR-2 (Empty files): If the combined byte size of all incoming files is `0`, reject with `com_error_files_empty`.
3. FR-3 (File count): If `(existing files count) + (incoming files count) > fileLimit (5)`, reject with the literal string `"File limit reached: 5 files"`.
4. FR-4 (MIME type, per file): For each incoming file, if the MIME type (after inference from extension) does not match any pattern in `supportedMimeTypes`, reject with `"Unsupported file type: <mime>"`. If the MIME cannot be determined, reject with `"Unable to determine file type for: <filename>"`.
5. FR-5 (Per-file size): For each incoming file, if `file.size >= fileSizeLimit (20 MB)`, reject with `"File size limit exceeded: 20 MB"`. (Boundary is inclusive — exactly 20 MB is rejected.)
6. FR-6 (Total size): After per-file checks, if `(existing total size) + (incoming total size) > totalSizeLimit (50 MB)`, reject with `"Total file size limit exceeded: 50 MB"`.
7. FR-7 (Duplicate detection): If any combination of `name + size + type_category` matches an already-attached file, reject with `com_error_files_dupe` → "Duplicate file detected."

> Note on error message sources: The `validateFiles` function generates the file-count, MIME, size, and total-size messages as raw strings (not via i18n keys). The `com_ui_attach_error_limit`, `com_ui_attach_error_type`, `com_ui_attach_error_size`, and `com_ui_attach_error_total_size` keys exist in the translation file but are currently used in separate code paths (e.g., older server-side error relays). For the Nufi endpoint client-side validation, the messages shown are the raw strings listed in FR-3 through FR-6 above. (verify: confirm exact toast text in the deployed UI for each error case.)

#### Validation & errors (exact messages)

| Condition | Toast message |
|---|---|
| Endpoint disabled | "File uploads are disabled for this endpoint" |
| Empty file (0 bytes) | "Empty files are not allowed." |
| Count exceeds 5 | "File limit reached: 5 files" |
| Unsupported MIME type | "Unsupported file type: `<mime>`" |
| MIME cannot be inferred | "Unable to determine file type for: `<filename>`" |
| File ≥ 20 MB | "File size limit exceeded: 20 MB" |
| Total > 50 MB | "Total file size limit exceeded: 50 MB" |
| Duplicate file | "Duplicate file detected." |
| Upload network error | "An error occurred while uploading the file." |
| Upload canceled | "The file upload request was canceled. Note: the file upload may still be processing and will need to be manually deleted." |
| HEIC conversion failure | "Failed to convert HEIC image to JPEG. Please try converting the image manually or use a different format." |
| General processing error | "An error occurred while processing the file." |
| Validation exception | "An error occurred while validating the file." |

#### Edge cases
- Attaching 4 files and then attaching 2 more at once: count check computes `4 (existing) + 2 (incoming) = 6 > 5`; the entire batch is rejected before any upload begins.
- Adding files one at a time to reach the limit: adding the 5th file is allowed; adding the 6th triggers the count error.
- Two files with the same name, size, and type in the same selection batch: the duplicate check covers both existing and incoming files; the second copy triggers "Duplicate file detected."
- Server returns a custom error message in `response.data.message`: that message is used directly in the error toast instead of the generic upload error.

#### Acceptance criteria
1. AC-1: Given 5 files are attached, when the user tries to attach a 6th, then a red toast "File limit reached: 5 files" appears and the 6th file is not added.
2. AC-2: Given the user attaches a 20 MB PDF, then a red toast "File size limit exceeded: 20 MB" appears and no chip is added.
3. AC-3: Given the user attaches a 19.99 MB PDF, then the file is accepted and upload begins.
4. AC-4: Given the total attached size is 45 MB, when the user attaches a 6 MB file, then a red toast "Total file size limit exceeded: 50 MB" appears.
5. AC-5: Given the user attaches a `.mp3` audio file, then a red toast "Unsupported file type: audio/mpeg" appears.
6. AC-6: Given the user attaches the same file twice (identical name, size, and type), then a red toast "Duplicate file detected." appears on the second attempt.
7. AC-7: Given multiple validation errors occur (e.g., two unsupported files in one drop), then a single toast with a bullet list of errors appears.

---

### Relationship to Agent Knowledge

#### Purpose
Clarifies the distinction between per-message file attachments (this section) and persistent Agent Knowledge (RAG via file search / vector store), so testers and end users choose the correct mechanism.

#### Preconditions / access
- Both features may be available simultaneously when the Nufi endpoint is used with an Agent that has File Search enabled.

#### UI elements
- **Per-message attachment** (this section): files are attached via the Attach Files button in the chat input bar. They are visible as chips between the text area and the send button. They are conversation-scoped.
- **Agent Knowledge / File Search**: files are uploaded through the Agent configuration panel (Side Panel → Agents → File Search section). They are stored in a vector store and persist across all conversations using that agent. This is RAG — the agent retrieves relevant chunks from these files on demand.

#### Functional behavior
1. FR-1: A per-message attachment is sent to the model once, as part of the specific message it is attached to. It is not stored for future conversations or retrievable by the model in later messages.
2. FR-2: Agent Knowledge files are indexed into a vector store. The agent retrieves relevant excerpts automatically across all conversations.
3. FR-3: When the Attach menu is open, the "Upload for File Search" option (`com_ui_upload_file_search`) — if shown — routes the file to the Agent's file search vector store (persistent, RAG). This is not a per-message attachment.
4. FR-4: "Upload to Provider" in the attach menu is a per-message attachment (conversation-scoped). "Upload as Text" is not available on the Nufi endpoint in its current configuration.
5. FR-5: A message can include both per-message attachments and benefit from Agent Knowledge simultaneously; the two mechanisms do not conflict.

#### When to use which
| Goal | Use |
|---|---|
| Share a one-off document or image for a single question | Per-message attachment (this section) |
| Give the agent persistent reference material to draw from across all conversations | Agent Knowledge (File Search in Agent config panel) |
| Vision: let the model describe or analyze an image | Per-message attachment via "Upload to Provider" |
| Extract text from a PDF or image for one message | Per-message attachment via "Upload as Text" (requires `context` capability — not enabled on Nufi by default) |

#### Validation & errors
- Files uploaded via "Upload for File Search" from the message attach menu are subject to the same per-file MIME and size validation, but their destination is the vector store rather than the message. Validation errors appear as red toasts.

#### Edge cases
- If an Agent has File Search disabled, the "Upload for File Search" option does not appear in the attach dropdown or drag-drop modal.
- Deleting a per-message attachment removes it only from the current draft message; it has no effect on Agent Knowledge files.

#### Acceptance criteria
1. AC-1: Given a file is attached to a message via "Upload to Provider", when the message is sent, then the file is visible in the conversation history for that message only and is not available in subsequent messages.
2. AC-2: Given a file is uploaded to the Agent's File Search knowledge base, then it is available as context in all future conversations with that agent, independent of per-message attachments.
3. AC-3: Given an Agent without File Search enabled, when the user opens the attach dropdown, then "Upload for File Search" is not visible in the menu.
