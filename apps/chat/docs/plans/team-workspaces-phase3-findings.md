# Team Workspaces — Phase 3 Exploration Findings (working notes)

Durable capture of the Phase-3 exploration so design survives context summarization. Phase 3 =
shared-RAG: add `FILE` as an ACL resource, team-knowledge endpoints, file access checks, and RAG
retrieval scoping.

## A. FILE-as-ACL-resource touch points (the "3a" foundation)

1. `packages/data-provider/src/accessPermissions.ts`: add `ResourceType.FILE='file'`;
   `AccessRoleIds.FILE_VIEWER/FILE_EDITOR/FILE_OWNER`; 3 cases in `accessRoleToPermBits`
   (viewer=VIEW, editor=VIEW|EDIT, owner=VIEW|EDIT|DELETE|SHARE).
2. `packages/data-schemas/src/methods/accessRole.ts` `seedDefaultRoles()`: add 3 FILE role seed
   entries (mirror agent_viewer/editor/owner; names `com_ui_role_viewer/editor/owner`,
   `RoleBits.VIEWER/EDITOR/OWNER`, `resourceType: ResourceType.FILE`). Seeded at startup via
   `api/models/index.js` `seedDatabase()` → `seedDefaultRoles()`.
3. `packages/data-schemas/src/admin/capabilities.ts`: add `SystemCapabilities.MANAGE_FILES` +
   `ResourceCapabilityMap[ResourceType.FILE] = MANAGE_FILES`. **`ResourceCapabilityMap` is
   `Record<ResourceType, SystemCapability>` → omitting this is a COMPILE ERROR (safety net).**
4. `packages/data-schemas/src/methods/file.ts`: add `getFileByObjectId(_id)` → `File.findById(_id).lean()`
   (existing `findFileById` resolves by the STRING `file_id`, not `_id`).
5. `api/server/routes/accessPermissions.js` `checkResourcePermissionAccess()`: add a
   `ResourceType.FILE` branch → `canAccessResource({ resourceType: FILE, requiredPermission,
   resourceIdParam:'resourceId', idResolver: getFileByObjectId })`.
6. `packages/data-provider/src/permissions.ts`: add `PermissionTypes.FILES='FILES'`.
   `packages/api/src/middleware/share.ts` `resourceToPermissionType`: add `[ResourceType.FILE]:
   PermissionTypes.FILES`. `packages/api/src/app/permissions.ts`: add a `filesPermissionsSchema` +
   role-config block mirroring the SKILLS pattern (else `PUT /api/permissions/file/...` → 400 at the
   share-policy middleware before the controller).

PermissionService API (already generic): `grantPermission({principalType, principalId, resourceType,
resourceId, accessRoleId, grantedBy, session?})`, `checkPermission({userId, role?, resourceType,
resourceId, requiredPermission})`, `findAccessibleResources({userId, role?, resourceType,
requiredPermissions}) → ObjectId[]`, `removeAllPermissions({resourceType, resourceId})`. Grant a file
to a team = `grantPermission({principalType:GROUP, principalId:teamGroupId, resourceType:FILE,
resourceId:file._id, accessRoleId:FILE_VIEWER, grantedBy:caller})`.

## B. Sharp edges (FILE is special)

1. **Dual key:** file has string `file_id` (the vector-store key, used everywhere external) AND Mongo
   `_id` (ObjectId, the ACL `resourceId`). ACL grants on `_id`; RAG searches by `file_id`. The
   team-share → RAG path must resolve granted `_id`s → their `file_id` strings.
2. **`user` owner field is required**; group-share sits ALONGSIDE the `file.user===userId` ownership
   shortcut in `filterFilesByAgentAccess`, never replacing it.
3. **TTL:** `createFile()` sets a 1h `expiresAt`; `updateFile()` removes it for permanent files. Only
   grant FILE ACL on permanent files (TTL removed) or the ACL entry dangles.
4. `aclEntry.resourceType` enum = `Object.values(ResourceType)` → rebuild `data-provider` +
   `data-schemas` after adding FILE.
5. No implicit uploader=owner ACL grant — ownership ACL is only what we explicitly grant.

## C. Current file access checks (extend for 3a)
`api/server/services/Files/permissions.js`:
- `hasAccessToFilesViaAgent({userId, role?, fileIds, agentId, isDelete?, files?}) → Map<file_id, bool>`
  — agent-mediated only; consults AGENT ACL + agent tool_resources + author ownership.
- `filterFilesByAgentAccess({files, userId, role?, agentId}) → MongoFile[]` — owned (file.user) ∪
  agent-accessible.
Neither consults `resourceType:'file'` ACL yet. Add `hasDirectFileAccess`/extend to call
`checkPermission({resourceType:FILE, resourceId:file._id, ...})` for direct+group grants.

## D. Team knowledge endpoints (3a, on the teams route)
- `POST /api/teams/:id/knowledge` (admin): `grantPermission({GROUP, teamGroupId:id, FILE, file._id,
  FILE_VIEWER, grantedBy:caller})`; require the file be permanent (no TTL) + caller owns it.
- `GET /api/teams/:id/knowledge` (member): `findAccessibleResources` by GROUP principal, or query ACL
  entries {principalType:GROUP, principalId:id, resourceType:FILE} → resolve files → list.
- `DELETE /api/teams/:id/knowledge/:fileId` (admin): remove the GROUP→file grant.

## E. RAG retrieval scoping (3b) — RESOLVED
**Integration point:** `primeFiles` in `api/app/clients/tools/util/fileSearch.js` (~line 34). It builds
the searchable set from `tool_resources[file_search].file_ids`, fetches via `getFiles`, filters via
`filterFilesByAgentAccess`, → `createFileSearchTool`. The rag_api is called by STRING `file_id` (one
`POST ${RAG_API_URL}/query` per file) — adding more file_id strings = more queries, NO rag_api change.

**Plan:** after computing the agent's `file_ids`, union `await getTeamSharedFileIds(req.user.id,
req.user.role)` (D16) into the set passed to `getFiles`. Because 3a-2 makes `filterFilesByAgentAccess`
FILE-ACL-aware (D15), the team-shared files PASS the filter (they're VIEW-granted) instead of being
stripped. Filter team files by `embedded:true` (only embedded files exist in rag_api).

**Sharp edges:** (a) team-shared files not in any agent's tool_resources get a cosmetic
'(just attached)' label in the tool-context string — harmless. (b) MUST inject so the ACL-aware filter
validates them (don't bypass authz). (c) `embedded:true` required to avoid rag_api errors.

**3b unit test:** `getTeamSharedFileIds` resolves grants→file_id strings (embedded filter); `primeFiles`
unions team ids and the ACL-aware filter passes them. Full e2e (real rag_api) deferred (D18).
