# Team Workspaces — Migration and Rollout Notes

This document covers what happens when you deploy Team Workspaces onto an existing LibreChat instance. No manual migration scripts are required for a standard deployment.

---

## Package rebuild

`@librechat/data-schemas` was bumped to **0.0.52** in Phase 0 to carry the extended `Group` schema (`ownerId`, `members[]`, `kind`, `joinPolicy`) and the new `TeamInvite` model. After pulling the branch and before starting the server:

```bash
npm run smart-reinstall   # or: npm install && npm run build
```

If you build packages individually, rebuild in dependency order:

```bash
cd packages/data-provider && npm run build
cd packages/data-schemas  && npm run build
cd packages/api           && npm run build
```

---

## Automatic seeding (no manual steps)

### FILE access roles

Three new access roles are added to the ACL system — `file_viewer`, `file_editor`, and `file_owner` — mirroring the existing `agent_viewer/editor/owner` pattern. These are seeded automatically at server startup:

```
api/models/index.js  →  seedDatabase()  →  seedDefaultRoles()
```

`seedDefaultRoles()` is an **idempotent upsert** — re-running it on an existing database is safe. No data is overwritten.

### TEAMS and FILES interface permissions

The `TEAMS` (`USE`, `CREATE`) permission type is added to the system. On first startup after the upgrade, `updateAccessPermissions` detects that the USER and ADMIN roles do not yet have `TEAMS` entries and writes the defaults:

- `USER`: `TEAMS.USE = true`, `TEAMS.CREATE = true`
- `ADMIN`: `TEAMS.USE = true`, `TEAMS.CREATE = true`

This update is persistent (stored in MongoDB via the `rolePermissionsSchema`) and runs only once per role until the schema changes again. The Phase-6 fix ensures `rolePermissionsSchema` persists these dynamically-added permission types correctly — earlier builds did not persist them across restarts.

---

## No group backfill needed

Existing admin-managed groups keep `kind: 'group'` (the default for pre-existing records). Team endpoints only operate on records with `kind: 'team'`. No migration of existing groups is needed or performed.

---

## Dark launch / gating the feature

To make the feature available in the backend while keeping end users from creating teams until you are ready:

1. In the admin panel, open **Roles & Permissions** → **USER** role.
2. Set `TEAMS.CREATE` to `false` (and optionally `TEAMS.USE` to `false` to hide the surface entirely).
3. When ready to enable for all users, set both back to `true`.

You can also enable the feature selectively for a subset of users by creating a custom role with `TEAMS.CREATE = true` and assigning it to early-access users.

---

## Summary checklist

| Step | Required | Notes |
|---|---|---|
| `npm run smart-reinstall` (or equivalent build) | Yes | Picks up `@librechat/data-schemas` 0.0.52 and the rebuilt `packages/api` bundle. |
| Restart the backend server | Yes | Triggers `seedDatabase()` and `updateAccessPermissions` automatically. |
| Manual DB migration | No | Seeding and permission bootstrap are fully automatic and idempotent. |
| Backfill existing groups | No | Existing groups remain `kind:'group'`; teams are a new concept. |
| Gate via admin panel | Recommended | Set `USER.TEAMS.CREATE = false` until you are ready to roll out. |
