## Endpoint, Model Selection & Parameters

This section documents the endpoint selector, model selector, conversation parameter panel, and preset management for the NuFi Chat deployment. The deployed configuration (`librechat.yaml`) enables exactly two endpoints — **Nufi** (a custom OpenAI-compatible endpoint) and **Agents** — and sets `endpointsMenu`, `modelSelect`, `parameters`, and `presets` all to `true`.

---

### Endpoint & Model Selector (Combined Dropdown)

#### Purpose

Provides a single unified control — rendered as a pill-shaped trigger button in the conversation header — through which the user picks both the endpoint (Nufi or Agents) and, for endpoints that have models, the specific model to use. The selected endpoint/model combination is applied to the active conversation immediately.

#### Preconditions / Access

- User is authenticated and at least one conversation is open (including a "new conversation" blank state).
- `interface.endpointsMenu: true` and `interface.modelSelect: true` are set in `librechat.yaml` (both are set in NuFi's config).
- The selector is hidden only when both `modelSelect: false` and no Model Specs are configured — which is not the case here.

#### UI Elements

- **Trigger button** — pill button in the conversation header (`aria-label="Select a model"`). Displays:
  - An endpoint/model icon (the configured icon for the selected endpoint, or a default Bot icon).
  - A **display label**: for the Nufi endpoint, the raw model ID string; for the Agents endpoint, the agent name. Falls back to `"Select a model"` (i18n key `com_ui_select_model`) when nothing is selected.
- **Dropdown panel** — opens below the trigger. Contains:
  - A **search combobox** (`id="model-search"`, accessible label from `com_endpoint_search_models`; actual `placeholder` attribute is a space `" "`).
  - **Endpoint items** — one expandable row per endpoint; for endpoints with models, the row expands to a submenu.
  - Within the Nufi submenu: a **per-endpoint search field** (placeholder `com_endpoint_search_endpoint_models` filled with the endpoint label), then the list of model rows.
  - Within the Agents submenu: a per-endpoint search field (placeholder `com_endpoint_search_var` filled with "Agents"), then the list of agent rows.
- **Checkmark icon** (`CheckCircle2`) — appears beside the currently selected item; a `VisuallyHidden` span announces `com_a11y_selected` to screen readers.
- **Pin / Unpin button** — appears on hover or focus within a model row; toggles the model as a favorite. Aria-label is `com_ui_pin` / `com_ui_unpin`.
- **Settings gear button** (`SettingsIcon`) — appears beside an endpoint label only when the endpoint requires a user-supplied API key. Not applicable to the Nufi or Agents endpoints in the NuFi deployment (keys are configured server-side).

#### Functional Behavior

**FR-1.** Clicking the trigger button opens the dropdown. Clicking it again, or clicking outside the dropdown (excluding dialogs and preset menus), closes it.

**FR-2.** When the dropdown is open, typing in the global search field filters all endpoints and models in real time (debounced 200 ms). Results show a flat list grouped by endpoint heading. If the query matches an endpoint label but not any of its model IDs, all models under that endpoint are shown. If a query matches neither an endpoint label nor any model, no results render and the text `com_files_no_results` is displayed. A live-region (`role="alert" aria-live="polite"`) announces the result count.

**FR-3.** The **Nufi endpoint row** expands to a sub-panel showing models fetched from the backend (fetch: true in `librechat.yaml`). The per-endpoint search field within this sub-panel filters Nufi models by the typed string (case-insensitive substring match).

**FR-4.** Clicking a model row under Nufi selects that endpoint and model and immediately starts or continues the conversation with those settings. The trigger button display updates to reflect the new selection.

**FR-5.** The **Agents endpoint row** expands to a sub-panel listing available agents by name (resolved via the agents map). Selecting an agent sets `endpoint = "agents"` and `agent_id = <selected agent id>` on the conversation.

**FR-6.** Screen reader announcement: after a model is selected, a polite announcement is made using `com_ui_model_selected` with the display name.

**FR-7.** Each model row contains a pin/unpin toggle for favorites. Favorited models remain visually pinned (pin icon always visible); un-favorited models show the icon only on hover/focus.

#### States & Edge Cases

- **Backend unreachable (Nufi models endpoint fails):** The model list for Nufi contains only the placeholder entry `"loading..."` (the sole default configured in `librechat.yaml`). The dropdown renders this single item. No spinner or error message is shown in the dropdown itself; the placeholder string is the only feedback. (requires manual verification on the running product: whether a loading spinner or error state is surfaced beyond the single placeholder model — static analysis is consistent with only `"loading..."` being shown)
- **Empty model list returned:** If the backend returns an empty array, the dropdown for Nufi shows no model rows (the sub-panel is empty). No explicit "no models" message is rendered in this code path.
- **Assistants endpoint loading models:** While assistants data is fetching (`isAssistantsEndpoint` is true and `endpoint.models === undefined`), a `Spinner` is rendered inside the Assistants sub-panel instead of model rows. This applies to the legacy `assistants` / `azureAssistants` endpoints, not the Agents endpoint.
- **No endpoint selected:** The trigger button displays the localized string `"Select a model"`.
- **modelSelect: false + no Model Specs:** The entire selector component is not rendered. Not applicable in the NuFi deployment.

#### Acceptance Criteria

**AC-1.** Given the page is loaded and authenticated, when the user views the conversation header, then the model selector trigger button is visible and shows the currently selected endpoint label or "Select a model".

**AC-2.** Given the selector is closed, when the user clicks the trigger button, then the dropdown opens and lists the "Nufi" and "Agents" endpoint rows.

**AC-3.** Given the dropdown is open, when the user types a partial model name in the global search box, then only matching endpoints and models appear within 200 ms.

**AC-4.** Given the dropdown is open and the user types a string with no matches, when the search completes, then the text "No results" (or the localized equivalent) is displayed.

**AC-5.** Given the user clicks a model under Nufi, when the selection completes, then the trigger button display updates to the chosen model ID and the conversation's endpoint and model are set accordingly.

**AC-6.** Given the Nufi backend models endpoint is unreachable, when the user opens the Nufi sub-panel, then the entry "loading..." is shown as the only model option and no unhandled error occurs.

**AC-7.** Given a model is selected, when the user activates the pin toggle for that model, then the model is marked as a favorite and the pin icon remains persistently visible on that row.

---

### Conversation Parameters Panel

#### Purpose

Exposes model-level inference parameters — temperature, top-p, penalties, token limits, and auxiliary options — so the user can tune the model's behavior per conversation without leaving the chat view. Parameters are applied immediately to the active conversation and persist for its lifetime (or until reset).

#### Preconditions / Access

- `interface.parameters: true` is set in `librechat.yaml` (it is).
- The active conversation's endpoint is a "param endpoint": `custom` (Nufi) and `agents` both qualify via the `paramEndpoints` set defined in `schemas.ts`.
- Parameters for the Nufi (`custom`) endpoint are accessed via the **SidePanel right rail** — a `SlidersHorizontal` icon in the right-hand side panel navigation, which opens the **Parameters** panel (`Panel.tsx`). This link is added to the nav when `isParamEndpoint === true && !isAgentsEndpoint` (`useSideNavLinks.ts:181-194`).
- The header gear button (`Settings2`, `id="parameters-button"`) that opens the OptionsPopover is rendered **only** when `interface.parameters === true` AND `paramEndpoint === false` (i.e., the endpoint is NOT in `paramEndpoints`). Because both `custom` (Nufi) and `agents` are in `paramEndpoints`, the header gear button is **never shown** for either endpoint in the NuFi deployment.

#### UI Elements

There are two distinct surfaces that expose parameters:

**(a) In-conversation SidePanel Parameters panel (`Panel.tsx`)** — the primary path for the Nufi endpoint:
- A `SlidersHorizontal` icon in the right-hand SidePanel nav opens the **Parameters** panel.
- The panel renders parameters from `paramSettings[EModelEndpoint.custom]` (the flat `openAI` array, `parameterSettings.ts`).
- Layout: a plain **2-column CSS grid** (`grid-cols-2`, `Panel.tsx:146`).
- Contains a **"Save as preset"** primary button and a **"Reset Model Parameters"** button (`RotateCcw`).

**(b) Edit Preset dialog (`EndpointSettings` component)** — used when editing a saved preset:
- Uses `presetSettings[EModelEndpoint.custom]` = `openAIColumns` → `OpenAISettings`.
- Renders a **two-column layout** with Column 1 (3/5 width on `md+`) from `openAICol1` and Column 2 (2/5 width on `md+`) from `openAICol2`.
- Scrollable container, max height **500 px (mobile)** / **350 px (tablet/desktop, `md:` breakpoint and above)**.

#### Parameters — Column 1

| Parameter key | UI Label (`labelCode`) | Component | Default | Range / Options | Description code |
|---|---|---|---|---|---|
| `model` | `com_ui_model` | `dropdown` | (current model) | Models fetched from backend | Model selector (when rendered in preset editor context) |
| `modelLabel` | `com_endpoint_custom_name` | `input` | `""` (blank) | Free text | Override display name for this conversation |
| `promptPrefix` | `com_endpoint_prompt_prefix` | `textarea` | `""` (blank) | Free text | System / custom instructions prepended to every request |

#### Parameters — Column 2

| Parameter key | UI Label (`labelCode`) | Component | Default | Range / Options | Description code |
|---|---|---|---|---|---|
| `maxContextTokens` | `com_endpoint_context_tokens` | `input` (number) | system default | Any positive integer | Max tokens passed as context window |
| `max_tokens` | `com_endpoint_max_output_tokens` | `input` (number) | undefined (unset) | Any positive integer | Max tokens the model may generate |
| `temperature` | `com_endpoint_temperature` | `slider` | `1` | 0 – 2, step 0.01 | Randomness of output (`com_endpoint_openai_temp`) |
| `top_p` | `com_endpoint_top_p` | `slider` | `1` | 0 – 1, step 0.01 | Nucleus sampling (`com_endpoint_anthropic_topp`) |
| `frequency_penalty` | `com_endpoint_frequency_penalty` | `slider` | `0` | -2 – 2, step 0.01 | Penalises repeated tokens (`com_endpoint_openai_freq`) |
| `presence_penalty` | `com_endpoint_presence_penalty` | `slider` | `0` | -2 – 2, step 0.01 | Penalises topic repetition (`com_endpoint_openai_pres`) |
| `stop` | `com_endpoint_stop` | `tags` | `[]` | 0 – 4 stop strings | Stop sequences (`com_endpoint_openai_stop`) |
| `resendFiles` | `com_endpoint_plug_resend_files` | `switch` | `true` (on) | boolean | Re-attach uploaded files on each turn (`com_endpoint_openai_resend_files`) |
| `imageDetail` | `com_endpoint_plug_image_detail` | `slider` (enum) | `auto` | low / auto / high | Vision image resolution (`com_endpoint_openai_detail`) |
| `reasoning_effort` | `com_endpoint_reasoning_effort` | `slider` (enum) | `unset` (auto) | unset / none / minimal / low / medium / high / xhigh | Reasoning depth (`com_endpoint_openai_reasoning_effort`) |
| `reasoning_summary` | `com_endpoint_reasoning_summary` | `slider` (enum) | `""` (empty / `com_ui_unset`, displays as "Unset") | none / auto / concise / detailed | Reasoning summary verbosity (`com_endpoint_openai_reasoning_summary`) |
| `verbosity` | `com_endpoint_verbosity` | `slider` (enum) | `none` | none / low / medium / high | Output verbosity (`com_endpoint_openai_verbosity`) |
| `useResponsesApi` | `com_endpoint_use_responses_api` | `switch` | `false` | boolean | Use OpenAI Responses API (`com_endpoint_openai_use_responses_api`) |
| `web_search` | `com_ui_web_search` | `switch` | `false` | boolean | Enable web search tool (`com_endpoint_openai_use_web_search`) |
| `disableStreaming` | `com_endpoint_disable_streaming_label` | `switch` | `false` | boolean | Disable token streaming (`com_endpoint_disable_streaming`) |
| `fileTokenLimit` | `com_ui_file_token_limit` | `input` (number) | undefined | Any positive integer | Per-file token limit for context inclusion (`com_ui_file_token_limit_desc`) |

> Note: `reasoning_effort`, `reasoning_summary`, `verbosity`, `useResponsesApi`, and `web_search` are part of the `openAI` parameter list in code and therefore present in the panel for the `custom` (Nufi) endpoint. Whether the configured Nufi backend model honors all of these depends on the backend implementation; unsupported parameters are silently ignored by most OpenAI-compatible servers.

#### Reset & Save-as-Preset Controls

Located below the parameter grid in the OptionsPopover / Side Panel context:

- **"Reset Model Parameters"** button (`com_ui_reset_var` with `com_ui_model_parameters`) — clears all non-excluded conversation-level overrides, reverting parameters to their defaults. Icon: `RotateCcw`.
- **"Save as preset"** button — opens the `SaveAsPresetDialog` (see Presets section) pre-filled with the current conversation's parameter values.

#### Functional Behavior

**FR-1.** Clicking the `SlidersHorizontal` icon in the right-hand SidePanel nav opens the Parameters panel for the Nufi endpoint. The header gear button (`id="parameters-button"`) is not shown for the Nufi or Agents endpoints (it is only rendered when the active endpoint is not in `paramEndpoints`).

**FR-2.** Each slider parameter renders a horizontal draggable slider plus a numeric input (in the older `Advanced.tsx` view) or a dynamic slider component (in the `Panel.tsx` SidePanel view). Dragging or typing updates the value immediately; the change is debounced before being written to the conversation state.

**FR-3.** Double-clicking a slider resets that individual parameter to its default value. In the SidePanel path (Nufi endpoint), this is implemented in `DynamicSlider.tsx` via `onDoubleClick`.

**FR-4.** Stop sequences accept up to 4 entries entered as tags (chip-style input). Existing tags can be removed individually.

**FR-5.** Boolean switch parameters (`resendFiles`, `useResponsesApi`, `web_search`, `disableStreaming`) toggle on/off; they do not affect the slider group state.

**FR-6.** Enum slider parameters (`imageDetail`, `reasoning_effort`, `reasoning_summary`, `verbosity`) snap to discrete labeled positions; intermediate float values are not valid.

**FR-7.** Clicking "Reset Model Parameters" calls `resetParameters`, which deletes all non-excluded parameter keys from the conversation object, causing the UI to revert to defaults on next render.

**FR-8.** The parameters panel is read-only when `readonly` prop is set — all inputs and sliders are disabled. (requires manual verification on the running product: which surfaces pass `readonly: true` — no call site passes `readonly={true}` in the SidePanel path based on static analysis; may be triggered by shared-conversation read-only mode)

**FR-9.** When the endpoint changes (e.g., switching from Nufi to Agents), the parameters effect runs, removes keys no longer in the new parameter set, and the panel re-renders with the new endpoint's controls.

#### States & Edge Cases

- **No endpoint selected:** The EndpointSettings component returns `null` and no parameter panel is rendered.
- **Header gear button shown vs. hidden:** The header gear button (`id="parameters-button"`) is rendered only when `paramEndpoint === false` (`HeaderOptions.tsx`). Both `custom` (Nufi) and `agents` are in `paramEndpoints`, so `paramEndpoint === true` for both — meaning the **gear button is never shown** for either endpoint in the NuFi deployment. The Nufi endpoint's parameters are accessed via the SidePanel right rail (`SlidersHorizontal` icon); the Agents endpoint accesses its parameters via the SidePanel agent builder.
- **Number input out of range:** The `DynamicInput` component does not enforce min/max at the UI level for number fields; out-of-range values are passed to the backend which may reject them.
- **Missing `maxContextTokens` or `max_tokens`:** If left blank (undefined), the backend uses its own defaults; the placeholder text is the localized `com_nav_theme_system` ("System").

#### Acceptance Criteria

**AC-1.** Given the Nufi endpoint is active, when the user clicks the `SlidersHorizontal` icon in the right-hand SidePanel, then the Parameters panel opens and displays a 2-column grid of parameters.

**AC-2.** Given the SidePanel Parameters panel is open, when the user drags the Temperature slider from 1.0 to 0.5 and sends a message, then the API request includes `temperature: 0.5`.

**AC-3.** Given the user has set Temperature to 0.7, when they double-click the Temperature slider, then the value returns to 1.0.

**AC-4.** Given the user enters the string "END" into the Stop sequences field and presses Enter, then a chip labeled "END" appears and the conversation's `stop` array contains `"END"`.

**AC-5.** Given parameters have been modified, when the user clicks "Reset Model Parameters", then all parameter controls return to their default values.

**AC-6.** Given temperature is set to 1.5 (within range), when the user reopens the SidePanel Parameters panel, then the slider shows 1.5 (state persists for the lifetime of the conversation).

**AC-7.** Given either the Nufi or Agents endpoint is selected, when the user views the conversation header, then no parameters gear button is shown (both endpoints are in `paramEndpoints`, so `paramEndpoint === true` suppresses the header button). Parameters for Nufi are accessed via the SidePanel right rail; parameters for Agents are accessed via the SidePanel agent builder.

---

### Presets

#### Purpose

Presets are named snapshots of a conversation's endpoint, model, and parameter settings. They can be applied to any new or existing conversation to restore a known configuration in one click. The presets menu provides full CRUD operations plus export/import.

#### Preconditions / Access

- `interface.presets: true` is set in `librechat.yaml` (it is).
- User must be authenticated; presets are persisted per user on the server.
- The Presets button (`BookCopy` icon, `id="presets-button"`, `aria-label` from `com_endpoint_examples`, `data-testid="presets-button"`) is visible in the conversation header when presets are enabled.
- Note: Agents-endpoint presets are explicitly excluded from the Edit Preset dialog (the component returns `null` if `isAgentsEndpoint(endpoint)`); Nufi-endpoint presets are fully supported.

#### UI Elements

**Presets Menu (popover):**
- **Header row:** Shows `com_endpoint_preset_default_item` ("Default:") followed by `<title>` (e.g., `Default: Low Temp`) when a default is set, or `com_endpoint_preset_default_none` ("No default preset active.") when none is set, on the left. On the right: a **"Clear All"** button (document-x icon + `com_ui_clear_all`) and a hidden **File Upload** input (for JSON import, triggered by "Clear All" dialog area — see import detail below).
- **Empty state:** If no presets exist, displays `com_endpoint_no_presets`.
- **Preset list:** Each preset row contains:
  - Endpoint icon (resolved by `getIconKey`).
  - Preset title (from `getPresetTitle`, truncated with `max-w` classes).
  - **Pin / Unpin** icon button (`com_ui_pin` / `com_ui_unpin`) — always visible for the default preset; hover/focus-visible otherwise.
  - **Edit** icon button (`com_ui_edit`) — hover/focus-visible.
  - **Delete (Trash)** icon button (`com_ui_delete`) — hover/focus-visible.

**Edit Preset Dialog (`OGDialog`):**
- Title: `com_ui_edit_preset_title` (includes preset name).
- **Preset Name** field — `Label` ("Preset name", `com_endpoint_preset_name`), `Input` with placeholder `com_endpoint_set_custom_name`.
- **Endpoint** dropdown — `SelectDropDown` with label `com_endpoint`, lists available non-agents endpoints. Changing the endpoint triggers model and setting re-initialization.
- **PopoverButtons** row — endpoint-specific auxiliary buttons (e.g., for the Google endpoint; no extra buttons for Nufi's `custom` type).
- **EndpointSettings** panel (same two-column layout as the conversation parameters panel, populated with the preset's stored values).
- **Action buttons:** "Export" (`com_endpoint_export`) and "Save" (`com_ui_save`).

**Save As Preset Dialog (`OGDialog`, title `com_endpoint_save_as_preset`):**
- **Preset Name** input (`id="preset-custom-name"`, label `com_endpoint_preset_name`, placeholder `com_endpoint_preset_custom_name_placeholder`).
- Pre-filled with the current conversation title or "My Preset" / `com_endpoint_my_preset`.
- **Save** button (`com_ui_save`). Pressing Enter also submits.

**Delete Confirmation Dialog:**
- Title: `com_ui_delete_preset`.
- Body: `com_ui_delete_confirm_strong` with the preset title in bold.
- Buttons: "Cancel" (`com_ui_cancel`) and "Delete" (`com_ui_delete`, destructive variant).

#### Functional Behavior — Create / Save Current Settings

**FR-1.** In the OptionsPopover, the "Save as preset" button opens the `SaveAsPresetDialog` pre-populated with the active conversation's settings (all parameters, endpoint, model).

**FR-2.** In the parameters SidePanel (right rail), a "Save as preset" primary button opens the same `SaveAsPresetDialog`.

**FR-3.** The user may edit the preset title in the dialog. Pressing Enter or clicking "Save" calls `useCreatePresetMutation`, which POSTs the cleaned preset to the server. On success a toast reads "`<title>` saved" and the dialog closes. On error a toast reads `com_endpoint_preset_save_error`.

**FR-4.** The preset is immediately visible in the presets menu after a successful save (React Query cache is invalidated).

#### Functional Behavior — Apply / Select Preset

**FR-5.** Clicking a preset row in the presets menu calls `onSelectPreset`, which:
  - Shows a brief toast `"<title>" Active!` (duration 750 ms; composed as `${toastTitle} ${localize('com_endpoint_preset_selected_title')}` where `com_endpoint_preset_selected_title` = `"Active!"`).
  - Evaluates endpoint-switch logic: if the current conversation is an existing "modular" conversation and the preset's endpoint is also modular, it updates in-place; otherwise it starts a new conversation.
  - Applies all preset parameters to the conversation state.

**FR-6.** Tools in the preset that are no longer available to the user are stripped before applying (`removeUnavailableTools`).

**FR-7.** If the preset has `defaultPreset: true`, the conversation is started with `disableParams: true` (parameters panel is not overridden by any further auto-load logic).

#### Functional Behavior — Edit Preset

**FR-8.** Clicking the Edit (pencil) icon on a preset row calls `onChangePreset`, which sets that preset as the active preset in Recoil state and sets `presetModalVisible: true`, opening the Edit Preset Dialog.

**FR-9.** In the Edit Preset Dialog, the user may change:
  - Preset name (text input).
  - Endpoint (dropdown; changing endpoint resets model to the first available if the current model is not in the new endpoint's list).
  - All parameter values in the EndpointSettings panel.

**FR-10.** Clicking "Save" calls `useUpdatePresetMutation`. On success, a toast shows "`<title>` saved". The presets list is refreshed.

#### Functional Behavior — Set / Clear Default Preset

**FR-11.** Clicking the Pin button on a non-default preset calls `onSetDefaultPreset(preset, false)`, which updates the preset with `defaultPreset: true`. On success, the header row shows `Default: <title>` and the next new conversation automatically loads this preset. Toast: `"<title>" is now the default preset.` (composed as `${toastTitle} ${localize('com_endpoint_preset_default')}` where `com_endpoint_preset_default` = `"is now the default preset."`).

**FR-12.** Clicking the Pin (Unpin) button on the current default preset calls `onSetDefaultPreset(preset, true)`, which updates with `defaultPreset: false`. Toast: `"<title>" is no longer the default preset.` (composed as `${toastTitle} ${localize('com_endpoint_preset_default_removed')}` where `com_endpoint_preset_default_removed` = `"is no longer the default preset."`). The default preset state in the header reverts to `com_endpoint_preset_default_none` ("No default preset active.").

#### Functional Behavior — Delete Preset

**FR-13.** Clicking the Trash icon on a preset row calls `onDeletePreset`, setting `presetToDelete` and opening the delete confirmation dialog.

**FR-14.** Clicking "Delete" in the confirmation dialog calls `deletePresetsMutation.mutate(preset)`. The preset is optimistically removed from the list immediately. On success, a toast "Preset deleted" (`com_endpoint_preset_delete_success`, severity SUCCESS) is shown and the server list is refreshed. On error, a toast `com_endpoint_preset_delete_error` (severity ERROR) is shown and the list is re-fetched to restore truth.

**FR-15.** Clicking "Cancel" closes the dialog with no mutation, and focus returns to the presets button.

#### Functional Behavior — Clear All Presets

**FR-16.** Clicking "Clear All" opens a confirmation dialog (title `com_ui_clear_presets`, warning `com_endpoint_presets_clear_warning`). Confirming calls `deletePresetsMutation.mutate(undefined)` (no argument = delete all), emptying the preset list.

#### Functional Behavior — Export Preset

**FR-17.** Clicking "Export" in the Edit Preset Dialog calls `exportPreset`, which uses `export-from-json` to download the current preset as a JSON file. The filename is the preset title sanitized with `filenamify` (e.g., `My Preset.json`). The export includes all cleaned preset fields (endpoint, model, parameters) but excludes server-only fields removed by `cleanupPreset`.

#### Functional Behavior — Import Preset

**FR-18.** A `FileUpload` component is embedded in the presets menu header area (associated with the "Clear All" dialog). The user selects a `.json` file from disk. The file content is parsed as JSON and passed to `onFileSelected`, which calls `importPreset` → `useCreatePresetMutation`. On success, toast `com_endpoint_preset_import` is shown. On error, toast `com_endpoint_preset_import_error` (severity ERROR).

**FR-19.** The imported preset's `presetId` is set to `null` before saving, so it is always created as a new preset (never overwrites an existing one).

#### States & Edge Cases

- **No presets exist:** The menu displays only the header row with "No default preset active." (`com_endpoint_preset_default_none`) and "Clear All", followed by the `com_endpoint_no_presets` message.
- **Preset title blank:** Defaults display to `com_endpoint_preset_title` ("Preset") in toasts; the save dialog pre-fills with "My Preset".
- **Server error on save:** Toast `com_endpoint_preset_save_error` is shown; the dialog remains open.
- **Model in preset no longer available:** When a preset whose model is not in the current model list is edited, `EditPresetDialog` auto-corrects the model to `models[0]` for the preset's endpoint. A `console.log` is emitted.
- **Agents endpoint preset:** The Edit Preset Dialog does not open for presets whose endpoint is the Agents endpoint (`isAgentsEndpoint` check returns early). Such presets can still be applied via the preset list but not edited through the dialog.
- **Import of malformed JSON:** The browser's JSON parser will throw; behavior depends on the `FileUpload` wrapper's error handling. (verify: whether a user-visible error is shown for malformed import files)
- **Preset with unavailable tools:** Tools in the preset that are not in the user's `availableTools` set are silently stripped on apply (FR-6).

#### Acceptance Criteria

**AC-1.** Given the user is on a conversation using the Nufi endpoint with Temperature set to 0.7, when they click "Save as preset", name it "Low Temp", and click "Save", then the preset appears in the presets list and a toast confirms the save.

**AC-2.** Given the preset "Low Temp" exists, when the user opens the presets menu and clicks "Low Temp", then the conversation's temperature is set to 0.7 and a toast reads `"Low Temp" Active!`.

**AC-3.** Given the preset "Low Temp" exists, when the user clicks the Edit icon, changes the name to "Very Low Temp", and clicks "Save", then the preset list shows "Very Low Temp" and the server reflects the update.

**AC-4.** Given the preset "Low Temp" exists, when the user clicks the Pin icon, then the header shows "Default: Low Temp" and a toast reads `"Low Temp" is now the default preset.`, and the next new conversation loads with Temperature 0.7.

**AC-5.** Given "Low Temp" is the default preset, when the user clicks the Unpin (active pin) icon, then the header reverts to "No default preset active." and a toast reads `"Low Temp" is no longer the default preset.`, and new conversations no longer auto-load the preset.

**AC-6.** Given the user clicks the Trash icon on "Low Temp" and confirms deletion, then the preset is removed from the list immediately and a success toast is shown.

**AC-7.** Given the user clicks "Export" in the Edit dialog for "Low Temp", then a file named `Low Temp.json` is downloaded containing the preset's endpoint, model, and parameter values.

**AC-8.** Given the user clicks the import (file upload) control and selects a valid exported `.json` preset file, then the preset appears in the list and a toast confirms the import.

**AC-9.** Given the presets list has multiple entries, when the user opens the presets menu, then all presets are listed with pin, edit, and delete icon buttons visible on hover/focus, and the default preset's pin button is always visible.

**AC-10.** Given "Clear All" is clicked and confirmed, when the dialog closes, then the presets list is empty and the header shows "No default preset active.".
