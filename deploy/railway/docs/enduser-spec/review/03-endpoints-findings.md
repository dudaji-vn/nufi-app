# Verification findings — 03 Endpoints/Models/Presets

## Summary

- Claims checked: 52 | CONFIRMED: 37 | WRONG: 8 | NEEDS-FIX: 4 | RUNTIME-ONLY: 2 | VERIFY-RESOLVED: 1

---

## Findings

### [WRONG] Parameters Panel — Access mechanism & trigger button (§ Conversation Parameters Panel, Preconditions / Access; FR-1; AC-1; AC-7)

**Spec says:** The parameters gear button (`Settings2`, `id="parameters-button"`) is shown in the conversation header for the Nufi (`custom`) endpoint; "gear button is shown for `custom` (Nufi)"; AC-7 says the gear button is NOT shown for the Agents endpoint.

**Reality (inverted condition):** `HeaderOptions.tsx:50` renders the gear button ONLY when `paramEndpoint === false`:

```tsx
{interfaceConfig?.parameters === true && paramEndpoint === false && (
  <TooltipAnchor id="parameters-button" …>
```

`isParamEndpoint` (`schemas.ts:149-162`) checks `paramEndpoints` (`schemas.ts:86-94`), which includes BOTH `EModelEndpoint.custom` AND `EModelEndpoint.agents`. Therefore `paramEndpoint` is `true` for both Nufi and Agents — the gear button is **never shown** for either in the NuFi deployment. For the Nufi (`custom`) endpoint, parameters are accessed through the **SidePanel right rail** (`Parameters` component, `Panel.tsx`), added to the nav links when `isParamEndpoint === true && !isAgentsEndpoint` (`useSideNavLinks.ts:181-194`). The OptionsPopover/gear path is dead code for this deployment.

- Evidence: `client/src/components/Chat/Input/HeaderOptions.tsx:50,65`; `packages/data-provider/src/schemas.ts:86-94,149-162`; `client/src/hooks/Nav/useSideNavLinks.ts:181-194`
- Suggested correction: Remove all references to `id="parameters-button"` and the OptionsPopover as the access path for Nufi parameters. Replace with: parameters are accessed via the SidePanel icon (SlidersHorizontal) in the right rail. The OptionsPopover / gear button path is shown only when the endpoint is NOT in `paramEndpoints` (none of the two NuFi endpoints qualify). AC-7 should be inverted: it is the Agents endpoint for which the SidePanel Parameters link is suppressed (`!isAgentsEndpoint` guard in `useSideNavLinks.ts:184`).

---

### [WRONG] Parameters Panel — Layout for in-conversation use (§ Conversation Parameters Panel, UI Elements; FR-2)

**Spec says:** The EndpointSettings panel for the Nufi endpoint uses `custom` → `OpenAISettings` → two-column layout (col1 3/5, col2 2/5) with parameters from `presetSettings[EModelEndpoint.custom]` = `openAIColumns`.

**Reality:** The SidePanel `Parameters` component (`Panel.tsx`) uses `paramSettings[EModelEndpoint.custom]` (the flat `openAI` array, `parameterSettings.ts:1052-1070`), not `presetSettings`. It renders a plain 2-column CSS grid (`grid-cols-2`, `Panel.tsx:146`), not a 3/5 + 2/5 split. The `presetSettings` / `OpenAISettings` / `openAIColumns` two-column layout described in the spec applies only to the **Edit Preset Dialog** (`EndpointSettings` component, `EndpointSettings.tsx`; `OpenAI.tsx:6,19`). FR-2's mention of "dynamic slider component (in the `Panel.tsx` SidePanel view)" is correct, but the column layout framing refers to a path only active in the preset editor.

- Evidence: `client/src/components/SidePanel/Parameters/Panel.tsx:41-51,145-171`; `packages/data-provider/src/parameterSettings.ts:1052-1070`; `client/src/components/Endpoints/Settings/OpenAI.tsx:6,19`
- Suggested correction: Describe two separate surfaces: (a) in-conversation SidePanel Parameters panel — flat `paramSettings`, 2-column grid, `Panel.tsx`; (b) Edit Preset dialog — `presetSettings` col1/col2, `OpenAISettings`, 3/5+2/5 layout.

---

### [WRONG] Parameters Panel — Column 1 parameter key `chatGptLabel` (§ Parameters — Column 1 table)

**Spec says:** Parameter key for the custom name override is `chatGptLabel`.

**Reality:** In `openAICol1` (`parameterSettings.ts:797-801`), the field is `librechat.modelLabel` which has `key: 'modelLabel'`. `openAIParams.chatGptLabel` (key `chatGptLabel`) is defined in the `openAIParams` object (`parameterSettings.ts:161-164`) but is **not referenced** in `openAICol1` or `openAICol2`. Saving this field writes to the `modelLabel` property of the conversation/preset object, not `chatGptLabel`. (Both share label `com_endpoint_custom_name`, so the UI label is correct.)

- Evidence: `packages/data-provider/src/parameterSettings.ts:97-108,161-164,797-801`
- Suggested correction: Change the parameter key in the table from `chatGptLabel` to `modelLabel`.

---

### [WRONG] Parameters Panel — Agents endpoint Spinner (§ States & Edge Cases, "Agents endpoint loading assistants")

**Spec says:** "While agents data is fetching, a `Spinner` is rendered inside the Agents sub-panel instead of model rows."

**Reality:** The `Spinner` is rendered only for `isAssistantsEndpoint` (not agents), specifically when `endpoint.models === undefined`:

```tsx
if (isAssistantsEndpoint(endpoint.value) && endpoint.models === undefined) {
  return <Spinner …/>;
}
```

`isAssistantsEndpoint` (`schemas.ts:131-137`) returns true only for endpoints ending in `"assistants"` (i.e., `assistants` / `azureAssistants`). `agents` does NOT trigger this. The Agents endpoint has its own loading path, but in practice no spinner is shown in the Agents sub-panel based on this code.

- Evidence: `client/src/components/Chat/Menus/Endpoints/components/EndpointItem.tsx:109-118`; `packages/data-provider/src/schemas.ts:131-137`
- Suggested correction: Remove or correct the edge-case note. The Spinner shown for a loading sub-panel applies to the legacy Assistants endpoint, not the Agents endpoint.

---

### [WRONG] Parameters Panel — Height claim inverted (§ UI Elements, EndpointSettings panel)

**Spec says:** "max height 500 px desktop / 350 px tablet"

**Reality:** The class string in `EndpointSettings.tsx:33` is `h-[500px] overflow-y-auto md:mb-2 md:h-[350px]`. In Tailwind, `md:` prefix applies at the medium breakpoint and above (≥768 px, i.e., tablet/desktop). Therefore 500 px is the **mobile** height and 350 px is the **tablet/desktop** height — the opposite of what the spec states.

- Evidence: `client/src/components/Endpoints/EndpointSettings.tsx:33`
- Suggested correction: "max height 500 px (mobile) / 350 px (tablet/desktop, `md:` breakpoint and above)".

---

### [WRONG] Model Selector — Global search debounce vs AC-3 timing inconsistency

**Spec says:** FR-2 correctly states "debounced 200 ms". However AC-3 says "within **300 ms**".

**Reality:** The debounce is 200 ms, not 300 ms.

- Evidence: `client/src/components/Chat/Menus/Endpoints/ModelSelectorContext.tsx:167-172`
- Suggested correction: Change AC-3 from "within 300 ms" to "within 200 ms".

---

### [WRONG] Model Selector — Search input placeholder vs comboboxLabel

**Spec says:** "A search combobox (`id="model-search"`, placeholder from `com_endpoint_search_models`)."

**Reality:** The `<input id="model-search" />` element has `placeholder=" "` (a single space). The `comboboxLabel={localize('com_endpoint_search_models')}` is an accessible label prop passed to the Menu wrapper, not the HTML placeholder attribute.

- Evidence: `client/src/components/Chat/Menus/Endpoints/ModelSelector.tsx:97-98`
- Suggested correction: "A search combobox (`id="model-search"`, accessible label from `com_endpoint_search_models`; actual `placeholder` attribute is a space)."

---

### [WRONG] Parameters Panel — `reasoning_summary` default label

**Spec says:** default is `none (unset)`.

**Reality:** `ReasoningSummary.none = ''` (empty string, `schemas.ts:218`). The enum mapping for this default in `parameterSettings.ts:302` maps `ReasoningSummary.none` → `com_ui_unset`, so the displayed label is "Unset", not "None". The value sent to the API when at default is `''` (empty string), not the string `"none"`.

- Evidence: `packages/data-provider/src/schemas.ts:217-222`; `packages/data-provider/src/parameterSettings.ts:293,302`
- Suggested correction: Change default description to `"" (empty / Unset)` and label to `com_ui_unset`. The UI displays "Unset", not "None".

---

### [NEEDS-FIX] Parameters Panel — FR-3 double-click reset attribution

**Spec says:** "Double-clicking a slider resets that individual parameter to its default value (behavior confirmed in `Advanced.tsx` via `onDoubleClick`)."

**Reality:** Double-click reset is confirmed, but it is implemented in `DynamicSlider.tsx:217` (the SidePanel component), not in `Advanced.tsx`. `Advanced.tsx` does exist and has `onDoubleClick` handlers (line 149, 190, 232, 274, 333 of `Advanced.tsx`), but `Advanced.tsx` is NOT used in the `custom` endpoint parameters path — neither through the OptionsPopover (which is not shown for custom) nor via Panel.tsx (which uses `DynamicSlider`). The claim that the behavior is "confirmed in `Advanced.tsx`" is misleading for the NuFi context.

- Evidence: `client/src/components/SidePanel/Parameters/DynamicSlider.tsx:217`; `client/src/components/Endpoints/Settings/Advanced.tsx:149`
- Suggested correction: Attribute the double-click reset to `DynamicSlider.tsx` (the SidePanel path). Remove the `Advanced.tsx` reference for the custom endpoint.

---

### [NEEDS-FIX] Presets — FR-11/FR-12 toast wording

**Spec says:** FR-11 toast: "`<title>` set as default" (`com_endpoint_preset_default`). FR-12 toast: "`<title>` removed as default" (`com_endpoint_preset_default_removed`).

**Reality:** `com_endpoint_preset_default` = `"is now the default preset."` and `com_endpoint_preset_default_removed` = `"is no longer the default preset."` (`en/translation.json:317,320`). The toast is composed as `${toastTitle} ${localize('com_endpoint_preset_default')}` (`usePresets.ts:115`), so the full message is e.g. `"Low Temp" is now the default preset.` and `"Low Temp" is no longer the default preset.` — not the paraphrase given in the spec.

- Evidence: `client/src/hooks/Conversations/usePresets.ts:113-121`; `client/src/locales/en/translation.json:317,320`
- Suggested correction: Update toast descriptions to exact composed strings: `"<title>" is now the default preset.` and `"<title>" is no longer the default preset.`

---

### [NEEDS-FIX] Presets — FR-5 toast wording

**Spec says:** FR-5 toast: "`<title>` selected" (duration 750 ms, `com_endpoint_preset_selected_title`).

**Reality:** `com_endpoint_preset_selected_title` = `"Active!"` (`en/translation.json:329`). Toast is composed as `${toastTitle} ${localize('com_endpoint_preset_selected_title')}` (`usePresets.ts:177-180`), so the message is e.g. `"Low Temp" Active!` — not `"Low Temp" selected`.

- Evidence: `client/src/hooks/Conversations/usePresets.ts:173-180`; `client/src/locales/en/translation.json:329`
- Suggested correction: Toast reads `"<title>" Active!`, not `"<title> selected"`.

---

### [NEEDS-FIX] Presets — Header row "Default preset:" label key

**Spec says:** Header row shows "Default preset: `<title>`" or `com_endpoint_preset_default_none`.

**Reality:** The label key used when a default exists is `com_endpoint_preset_default_item` = `"Default:"` (`en/translation.json:318`), not the phrase "Default preset:" as written. Full display is e.g. `Default: Low Temp`. When no default is set, `com_endpoint_preset_default_none` = `"No default preset active."` — not a short "Default: none".

- Evidence: `client/src/components/Chat/Menus/Presets/PresetItems.tsx:58-60`; `client/src/locales/en/translation.json:318-319`
- Suggested correction: Change spec to use `com_endpoint_preset_default_item` ("Default:") and show the full "No default preset active." text for the empty state.

---

### [RUNTIME-ONLY] VERIFY-RESOLVED: Nufi model fetch fallback (§ States & Edge Cases, "Backend unreachable")

**Spec says (verify marker):** "verify: whether a loading spinner or error state is surfaced beyond the single placeholder model"

**Resolution:** Based on static code analysis, when `fetch: true` fails and the backend is unreachable, the configured `default: ["loading..."]` entry is the only model in the dropdown (per `librechat.yaml:27-29` and LibreChat's `loadConfigModels.js` behavior as described in the yaml comment). No spinner or error banner is rendered in the dropdown itself for a failed fetch. The placeholder string `"loading..."` is the only feedback visible in the sub-panel.

However, confirming the exact failure behavior (network timeout, fallback timing, whether LibreChat shows a toast elsewhere) requires a runtime test with the upstream models endpoint deliberately blocked.

- Evidence: `nufi-chat/librechat.yaml:20-29` (yaml comment explicitly states this); static code consistent with claim.
- Verdict: RUNTIME-ONLY for the spinner/toast question. The spec's stated behavior ("only `loading...` shown, no spinner") is consistent with the code; fully confirming requires a runtime test.

---

### [RUNTIME-ONLY] VERIFY-RESOLVED: `readonly` prop surfaces (§ FR-8)

**Spec says (verify marker):** "verify: which surfaces pass `readonly: true` — currently not observed in the header popover path"

**Resolution:** No call site passes `readonly={true}` to `EndpointSettings` in the OptionsPopover path (`HeaderOptions.tsx:74-79`). The `readonly` prop is threaded through `OpenAI.tsx:12` → `DynamicSlider.tsx:210` to `disabled={readonly}`. Runtime search confirms no `readonly={true}` is set at the header popover. This behavior may be triggered by conditional logic in other views (e.g., shared conversation read-only mode) that requires runtime testing to confirm.

- Evidence: `client/src/components/Chat/Input/HeaderOptions.tsx:74-79`; `client/src/components/Endpoints/Settings/OpenAI.tsx:12`; no `readonly={true}` found via grep.
- Verdict: RUNTIME-ONLY. The spec's parenthetical "(currently not observed in the header popover path)" is correct based on static analysis.

---

## CONFIRMED items (selected highlights)

- **FR-1 (Model Selector trigger):** `aria-label="Select a model"` confirmed on the trigger button. `ModelSelector.tsx:66,71`.
- **FR-2 (Global search debounce 200 ms):** Confirmed. `ModelSelectorContext.tsx:169-171`.
- **FR-6 (Screen reader announcement):** `com_ui_model_selected` announced via `announcePolite`. `ModelSelectorContext.tsx:237-238`.
- **FR-7 (Pin/Unpin favorites):** Pin/Unpin button in model rows confirmed with `com_ui_pin`/`com_ui_unpin`. `PresetItems.tsx:164-199`.
- **openAICol2 full parameter list (12 items):** All parameters in the spec's Column 2 table are present in `openAICol2` (`parameterSettings.ts:803-820`): `maxContextTokens`, `max_tokens`, `temperature`, `top_p`, `frequency_penalty`, `presence_penalty`, `stop`, `resendFiles`, `imageDetail`, `reasoning_effort`, `reasoning_summary`, `verbosity`, `useResponsesApi`, `web_search`, `disableStreaming`, `fileTokenLimit`. ✓
- **Temperature range 0–2, default 1, step 0.01:** `openAISettings.temperature` (`schemas.ts:328-333`). ✓
- **top_p range 0–1, default 1, step 0.01:** `openAISettings.top_p` (`schemas.ts:334-339`). ✓
- **frequency_penalty / presence_penalty range -2–2, default 0:** `openAISettings.frequency_penalty/presence_penalty` (`schemas.ts:340-352`). ✓
- **stop tags: 0–4:** `baseDefinitions.stop.maxTags: 4` (`parameterSettings.ts:68`). ✓
- **resendFiles default true:** `librechat.resendFiles.default: true` (`parameterSettings.ts:129`). ✓
- **imageDetail options low/auto/high, default auto:** `baseDefinitions.imageDetail` (`parameterSettings.ts:70-87`). ✓
- **reasoning_effort options: unset/none/minimal/low/medium/high/xhigh:** `openAIParams.reasoning_effort` (`parameterSettings.ts:230-258`). ✓
- **reasoning_effort default `unset` (maps to `com_ui_auto`):** `parameterSettings.ts:237,249`. ✓
- **verbosity options none/low/medium/high, default none (empty string):** `parameterSettings.ts:310-328`. ✓
- **EditPresetDialog returns null for agents endpoint:** `EditPresetDialog.tsx:129-131`. ✓
- **Preset CRUD (create/read/update/delete) all confirmed:** `usePresets.ts` mutations confirmed. ✓
- **export uses `filenamify` + `export-from-json`:** `usePresets.ts:265-273`. ✓
- **Import sets `presetId: null`:** `usePresets.ts:161`. ✓
- **deletePresetsMutation.mutate(undefined) = clear all:** `usePresets.ts:236`. ✓
- **modelSelect: false + no Model Specs hides selector:** `ModelSelector.tsx:131-133`. ✓
- **SettingsIcon (API key) gear shown only when endpoint requires user key:** `EndpointItem.tsx:157-161,197`. ✓
- **EndpointSettings height 500px mobile / 350px md+:** values correct once the inversion (finding above) is corrected. `EndpointSettings.tsx:33`. ✓ (spec direction wrong, values right)
- **FR-4 (Agents sets agent_id):** `ModelSelectorContext.tsx:213-221` sets `agent_id` for agents endpoint. ✓
- **PresetItems "No presets" empty state:** `PresetItems.tsx:112-123`. ✓
- **Presets — FR-14 optimistic removal:** `usePresets.ts:82-89`. ✓
- **FR-15 (Cancel closes dialog, no mutation):** `PresetsMenu.tsx:130-134`. ✓
- **paramEndpoints includes agents, openAI, custom, anthropic, google, bedrock, azureOpenAI:** `schemas.ts:86-94`. ✓
