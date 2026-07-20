# Team RBAC Sub-groups — Phase 3 (Frontend: Groups tab + Share-with selector) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax. NOTE: frontend tasks are not classic TDD — each task is "build + `tsc` clean + correct react-query invalidation"; the CONTROLLER visually verifies each task against the running app (backend :3080 + vite :3081) after its review, mirroring how the Team Workspaces Phase-5 UI was verified.

**Goal:** Make sub-group RBAC usable in the UI: a "Groups" tab in the team detail (owner/admin create/manage sub-groups + their members), and a "Share with" target selector + target badges + per-target unshare in the Knowledge and Shared tabs.

**Architecture:** New react-query hooks (`client/src/data-provider/Teams/`) consume the Phase-2 data-provider surface (`dataService.listSubgroups`/`createSubgroup`/… + the `targetSubgroupId`-threaded share services). New `GroupsTab` + a sub-group management dialog in `client/src/components/Teams/`. The Knowledge/Shared pickers gain a target `<Select>`; shared rows render a `target` badge.

**Tech Stack:** React + TypeScript, `@tanstack/react-query` v4 (3-arg form), `@librechat/client` UI primitives, `useLocalize`. Phases 1-2 (sub-group backend + data-provider surface) are merged on `fork/main`.

## Global Constraints

- All user-facing text via `useLocalize()`; add only English keys to `client/src/locales/en/translation.json` (`com_ui_*`).
- react-query **v4** 3-arg form (`useQuery([key], fn, opts)` / `useMutation(fn, opts)`); every mutation invalidates the affected query keys (the Teams hooks already establish this discipline — match it). Use `QueryKeys.subgroups`/`QueryKeys.subgroup` (added in P2) and `MutationKeys.*Subgroup*`.
- Reuse the Phase-2 data-provider surface — do NOT re-define endpoints/services/types. `dataService.{listSubgroups,getSubgroup,createSubgroup,updateSubgroup,deleteSubgroup,addSubgroupMember,removeSubgroupMember}` and the `targetSubgroupId?`-extended `{addTeamKnowledge,removeTeamKnowledge,shareTeamAgent,unshareTeamAgent,shareTeamPrompt,unshareTeamPrompt}` already exist. Types: `TSubgroup`, `TSubgroupMember = TTeamMember`, `TSubgroupDetail`, `TSubgroupListResponse`, `TSubgroupDetailResponse`, `TCreateSubgroupRequest`.
- Owner/admin-only affordances gate on the existing `callerRole` (`'owner'|'admin'`) already computed in `TeamDetail.tsx`. Members see read-only.
- `@librechat/client` primitives (`Tabs`, `Button`, `OGDialog`/`OGDialogTemplate`, `Input`, `Label`, `Select`, `Spinner`, `useToastContext`). No `any`. Match the existing Teams components' theme tokens + the P2-polish visual style (rounded-lg, `px-3.5 py-2.5` rows).
- The client consumes the BUILT `librechat-data-provider` dist (already rebuilt in P2). If a consumed export is missing at runtime, rebuild via `npm run build:data-provider`.

---

### Task 1: Sub-group react-query hooks + thread `targetSubgroupId` into share mutations

**Files:**
- Modify: `client/src/data-provider/Teams/queries.ts`, `client/src/data-provider/Teams/mutations.ts`, `client/src/data-provider/Teams/index.ts` (export the new hooks)
- Test: none (hooks; verified by `tsc` + the components that consume them in T2/T3 + the controller's visual check)

**Interfaces:**
- Produces (mirror the existing `useTeamQuery`/`useCreateTeamMutation` style in the same files):
```ts
useSubgroupsQuery(teamId: string, config?): // GET → { subgroups: TSubgroup[] }, key [QueryKeys.subgroups, teamId]
useSubgroupQuery(teamId: string, sgId: string, config?): // GET → TSubgroupDetail, key [QueryKeys.subgroup, teamId, sgId]
useCreateSubgroupMutation(teamId, options?):  // dataService.createSubgroup(teamId, body) → invalidate [subgroups, teamId]
useUpdateSubgroupMutation(teamId, options?):  // (sgId, body) → invalidate [subgroups, teamId] + [subgroup, teamId, sgId]
useDeleteSubgroupMutation(teamId, options?):  // (sgId) → invalidate [subgroups, teamId] + the team's knowledge/agents/prompts lists (grants vanish)
useAddSubgroupMemberMutation(teamId, options?):    // (sgId, userId) → invalidate [subgroup, teamId, sgId]
useRemoveSubgroupMemberMutation(teamId, options?): // (sgId, userId) → invalidate [subgroup, teamId, sgId]
```
- Also thread an optional `targetSubgroupId` through the EXISTING share/unshare mutations so callers can pass it: `useAddKnowledgeMutation`, `useRemoveKnowledgeMutation`, `useShareAgentMutation`, `useUnshareAgentMutation`, `useSharePromptMutation`, `useUnsharePromptMutation`. Their mutation variables gain `targetSubgroupId?: string`, passed to the data-service fn. On success they already invalidate the relevant list key — keep that.

- [ ] **Step 1:** Add the 2 queries + 5 mutations (mirror the existing hooks' structure: `useQuery([key], () => dataService.fn(...), {...})` / `useMutation((vars) => dataService.fn(...), { onSuccess: invalidate })`). Thread `targetSubgroupId` into the 6 share/unshare mutations' variables + service calls (optional, back-compat — existing callers pass nothing).
- [ ] **Step 2:** Export all new hooks from `index.ts`. Confirm the `client/src/data-provider/index.ts` re-export picks them up (it re-exports the Teams index).
- [ ] **Step 3:** `cd client && npx tsc --noEmit` — no new errors in `data-provider/Teams`.
- [ ] **Step 4:** Commit: `feat(client): sub-group react-query hooks + targetSubgroupId on share mutations`.

---

### Task 2: Groups tab (sub-group CRUD + member management)

**Files:**
- Create: `client/src/components/Teams/GroupsTab.tsx`, `client/src/components/Teams/SubgroupDialog.tsx` (create/rename), `client/src/components/Teams/SubgroupMembersDialog.tsx` (manage members)
- Modify: `client/src/components/Teams/TeamDetail.tsx` (add a 5th `TabsTrigger`/`TabsContent` value `"groups"` — owner/admin only), `client/src/locales/en/translation.json`
- Test: none (component; controller visually verifies)

**Interfaces:**
- Consumes: `useSubgroupsQuery`, `useSubgroupQuery`, `useCreateSubgroupMutation`, `useUpdateSubgroupMutation`, `useDeleteSubgroupMutation`, `useAddSubgroupMemberMutation`, `useRemoveSubgroupMemberMutation` (Task 1); `useTeamQuery(teamId)` (the team's members, to pick from when adding to a sub-group); `callerRole` passed from `TeamDetail`.

- [ ] **Step 1:** `GroupsTab({ teamId, callerRole })` — `useSubgroupsQuery`; spinner/empty state ("No groups yet"); a list of sub-group cards (name, member count) styled like the existing Teams rows (`rounded-lg border border-border-light px-3.5 py-2.5`). owner/admin: a "New group" button (opens `SubgroupDialog`), and per-row Rename (SubgroupDialog) + Delete (OGDialog confirm, `useDeleteSubgroupMutation`) + "Manage members" (opens `SubgroupMembersDialog`). Members: read-only list.
- [ ] **Step 2:** `SubgroupDialog` (OGDialog) — name + description inputs; create (`useCreateSubgroupMutation`) or rename (`useUpdateSubgroupMutation`); toast + invalidate. `SubgroupMembersDialog` — shows the sub-group's members (`useSubgroupQuery`), a picker of the TEAM's members not yet in the sub-group (from `useTeamQuery`) to add (`useAddSubgroupMemberMutation`), and remove per member (`useRemoveSubgroupMemberMutation`); toasts.
- [ ] **Step 3:** In `TeamDetail.tsx`, add a `"groups"` tab (label `com_ui_team_groups`) shown only when `callerRole !== 'member'` (owner/admin), with `<GroupsTab teamId={teamId} callerRole={callerRole} />`. Keep the existing 4 tabs + the loading-race-safe structure intact.
- [ ] **Step 4:** Add `com_ui_*` keys (e.g. `com_ui_team_groups`, `com_ui_team_group`, `com_ui_team_new_group`, `com_ui_team_group_name`, `com_ui_team_no_groups`, `com_ui_team_manage_members`, `com_ui_team_delete_group`, `com_ui_team_delete_group_confirm`, `com_ui_team_add_to_group`, `com_ui_team_group_created`, `com_ui_team_group_deleted`, `com_ui_team_member_added`, `com_ui_team_member_removed`, `com_ui_members_count` — reuse existing where present).
- [ ] **Step 5:** `cd client && npx tsc --noEmit` clean for these files; `npx eslint --fix` (repo root) on them. Commit: `feat(client): team Groups tab (sub-group CRUD + member management)`.

---

### Task 3: "Share with" target selector + target badges + per-target unshare

**Files:**
- Modify: `client/src/components/Teams/KnowledgeTab.tsx` (the `FilePickerDialog` + the shared-file rows), `client/src/components/Teams/SharedTab.tsx` (the Agent/Prompt picker dialogs + the shared rows), `client/src/locales/en/translation.json`
- Test: none (component; controller visually verifies the access-scoped behavior end-to-end)

**Interfaces:**
- Consumes: `useSubgroupsQuery(teamId)` (the options for the "Share with" select); the `targetSubgroupId`-threaded share/unshare mutations (Task 1); the list items now carry `target: {type:'team'} | {type:'subgroup', id, name}` (Phase-2 backend + the data-provider types).

- [ ] **Step 1:** In each picker dialog (`FilePickerDialog`, the agent picker, the prompt picker), add a **"Share with"** `<Select>` (only when there are sub-groups): default option "Whole team" (value empty → `targetSubgroupId` undefined), plus one option per `useSubgroupsQuery` result. The picker's add action passes the selected `targetSubgroupId` to the share mutation.
- [ ] **Step 2:** On each shared-resource ROW (knowledge files, shared agents, shared prompts), render a small **target badge**: "Whole team" or the sub-group name (from `row.target`). The row's unshare/remove action passes `row.target`'s `targetSubgroupId` (the sub-group id, or undefined for team) to the unshare mutation, so it revokes the correct grant. (A resource may appear once per target — the Phase-2 list returns one row per grant.)
- [ ] **Step 3:** Add any new `com_ui_*` keys (`com_ui_team_share_with`, `com_ui_team_whole_team`, `com_ui_team_shared_with` — reuse existing). Localize.
- [ ] **Step 4:** `cd client && npx tsc --noEmit` clean; `npx eslint --fix` on changed files. Commit: `feat(client): share-with sub-group selector + target badges + per-target unshare`.

---

## Self-Review (run after writing; fix inline)

- **Spec coverage (P3 scope):** hooks → T1; Groups tab + member management → T2; share-with selector + target badges + per-target unshare → T3. ✓
- **Out of P3 scope:** P4 (cascade on team/user delete, `maxSubgroupsPerTeam`, docs). The frontend delete-subgroup mutation invalidates the resource lists so the UI reflects vanished grants, but the BACKEND cascade is P4.
- **Type consistency:** hook names in T1's `Produces` are consumed verbatim in T2/T3; `row.target` shape `{type:'team'} | {type:'subgroup',id,name}` matches the Phase-2 data-provider list item types; `TSubgroup`/`TSubgroupMember`/`TSubgroupDetail` reused (not redefined).
- **react-query invalidation:** delete-subgroup invalidates both the sub-group list AND the team's knowledge/agents/prompts lists (its grants disappear); share/unshare with a target invalidates the relevant list (already wired). A missing invalidation = stale UI (the most common frontend defect here).

## Controller verification (after each task's review)

Against the running app (backend :3080, vite :3081, test login `owner@nufi.test`/`Test1234!`, team "Engineering"): T2 → open a team → Groups tab → create a sub-group, add a member, rename, delete; confirm via the UI + (optionally) mongo. T3 → Knowledge/Shared tab → "Share with" a sub-group → confirm the row shows the sub-group badge; log in as / simulate a member NOT in that sub-group and confirm they don't see it (or assert via the list response). Capture a screenshot per slice.

## Definition of done (Phase 3)

`client` + `data-provider` build/`tsc` clean; the Groups tab manages sub-groups + members; resources can be shared with a sub-group via the selector and show the correct target badge; per-target unshare works; all visually verified against the running app. Then local FF-merge to `fork/main`. After P4 (cascade + limits + docs) the whole feature is usable end-to-end and can be released per `feedback_release_flow`.
