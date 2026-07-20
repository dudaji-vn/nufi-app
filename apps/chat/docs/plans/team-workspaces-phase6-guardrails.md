# Team Workspaces — Phase 6: Guardrails / Config / TEAMS permission (Spec)

Phase 6 of the master plan. Three independent pieces, each its own task. Touch points from
exploration. Builds on Phases 0–4 (all merged).

## D20 — TEAMS interface permission (gate team creation), FILES-pattern (no YAML interface field)
`generateCheckAccess({ permissionType: PermissionTypes.TEAMS, permissions:[USE,CREATE], getRoleByName })`
applied on `POST /api/teams`. Default `USE+CREATE = true` for USER and ADMIN (admins can lower the
USER role to gate creation). Follows the FILES precedent (no `interface.teams` YAML key;
`hasExplicitConfig`→false; defaults-only bootstrap) to minimize the change set.
**Touch points (TS compile-gates enforce consistency — `permissionsSchema`/`PERMISSION_TYPE_INTERFACE_FIELDS` are `Record<PermissionTypes,_>`):**
1. `packages/data-provider/src/permissions.ts`: `TEAMS='TEAMS'` enum; `teamsPermissionsSchema`
   (`USE`/`CREATE` default true); `permissionsSchema[TEAMS]`; `PERMISSION_TYPE_INTERFACE_FIELDS[TEAMS]='teams'`.
2. `packages/data-provider/src/roles.ts`: ADMIN + USER defaults `[TEAMS]:{USE:true,CREATE:true}`.
3. `packages/api/src/app/permissions.ts`: `hasExplicitConfig` case TEAMS → `false` (like FILES);
   `allPermissions[TEAMS]` block (mirror SKILLS/FILES).
4. `api/server/routes/teams.js`: build `checkTeamsCreate` and apply on `POST /`.
5. Build data-provider + packages/api.

## D21 — Config limits
Add to `configSchema` (`packages/data-provider/src/config.ts`):
```ts
teams: z.object({
  maxTeamsPerUser: z.number().int().positive().optional(),
  maxMembersPerTeam: z.number().int().positive().optional(),
  maxKnowledgeFilesPerTeam: z.number().int().positive().optional(),
}).optional(),
```
The teams router lacks `configMiddleware` → `req.config` undefined. Add `configMiddleware` to the teams
router (`router.use(requireJwtAuth, checkBan, configMiddleware)`) and read `req.config?.config?.teams?.*`
in handlers (extend the `ServerRequest` type with `config?` if needed). Enforce (each → **403** when over
limit, only when the limit is configured — `undefined` means unlimited):
- `maxTeamsPerUser`: in `create` handler — `getUserTeams(caller).length >= max` → 403.
- `maxMembersPerTeam`: in the invite `accept` handler — the team's current member count `>= max` → 403 (before addTeamMember).
- `maxKnowledgeFilesPerTeam`: in knowledge `add` — current team file-grant count `>= max` → 403.

## D22 — User-deletion cascade
In `api/server/controllers/UserController.js` `deleteUserController`, add a teams-cleanup block before the
existing `db.removeUserFromAllGroups(user.id)` (line ~340). The existing `removeUserFromAllGroups` only
`$pullAll`s `memberIds` (NOT the typed `members[]` subdoc, and NOT owner handling) — so handle teams via the
typed methods:
```js
const teams = await db.getUserTeams({ userId: user.id });
for (const team of teams) {
  const isOwner = team.ownerId?.toString() === user.id;
  if (isOwner) {
    const admins = (team.members ?? []).filter(m => m.role === 'admin' && m.userId.toString() !== user.id);
    if (admins.length) {
      await db.transferOwnership({ groupId: team._id, fromUserId: user.id, toUserId: admins[0].userId });
      await db.removeTeamMember({ groupId: team._id, userId: user.id });   // now non-owner
    } else {
      await db.deleteInvitesByGroup({ groupId: team._id });
      await db.deleteAclEntries({ principalId: team._id });                 // grants made TO the team (by-principal)
      await db.deleteGroup(team._id);
    }
  } else {
    await db.removeTeamMember({ groupId: team._id, userId: user.id });      // pulls members[] + memberIds
  }
}
```
All methods already injected in `db`. This also closes the deferred by-principal ACL cleanup (D5) for the
delete-team path (the Phase-1 team-DELETE endpoint could adopt `deleteAclEntries({principalId})` similarly —
follow-up, noted). Integration test: a user who owns a team with another admin → ownership transfers on
delete; a user who owns a sole-member team → team+invites+grants deleted; a non-owner member → removed from
`members`+`memberIds`.

## Tasks
- **T1** (D20): TEAMS interface permission across data-provider + packages/api + the route gate; build. Test: USER role has TEAMS.USE/CREATE; `POST /api/teams` passes for USER, and (unit) `generateCheckAccess` denies a role without it.
- **T2** (D21): config `teams` limits + `configMiddleware` on the router + the 3 limit checks + tests (limit hit → 403; unset → unlimited).
- **T3** (D22): user-delete cascade + integration test.

## Out of scope
Frontend (Phase 5), migration/docs (Phase 7). Admin user-deletion route is currently commented out — only
self-deletion (`deleteUserController`) exists, so the cascade lives there.
