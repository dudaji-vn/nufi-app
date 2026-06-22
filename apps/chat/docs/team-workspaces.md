# Team Workspaces

Team Workspaces lets any authenticated user create a self-service team, invite members by email, and share resources across the team — a shared knowledge base (files) for RAG retrieval, agents, and prompt groups — without admin involvement for day-to-day management.

## Overview

A **team** is a named group with an owner, optional admins, and members. Resources shared with a team are immediately accessible to all current members:

- **Shared knowledge base** — uploaded files attached to the team's knowledge base are included in every member's RAG (`file_search`) queries automatically.
- **Shared agents and prompt groups** — any agent or prompt group the team owner/admin holds SHARE rights on can be shared with the team so members can use it.

Teams are distinct from admin-managed groups (`kind: 'team'` vs `kind: 'group'`). Admin-managed groups are unaffected.

---

## Roles

Every team member holds exactly one role. Roles are ordered: **owner > admin > member**.

| Role | Who | Capabilities |
|---|---|---|
| **owner** | Exactly one member (invariant) | All admin actions + delete team + transfer ownership. Cannot leave or be demoted while sole owner. |
| **admin** | Zero or more members | Invite/revoke members, change member roles (admin/member), manage knowledge, share/unshare agents and prompt groups. |
| **member** | Zero or more members | Access all shared resources (knowledge, agents, prompts). Can leave the team. Cannot manage membership or resources. |

Ownership transfer: the owner promotes a member and atomically the previous owner becomes a member. There is always exactly one owner per team.

---

## API Reference

All routes require authentication (`requireJwtAuth + checkBan`). All paths are under `/api/teams`. Bodies and responses are JSON.

### Teams — CRUD

| Method | Path | Min role | Body | Behavior |
|---|---|---|---|---|
| `POST` | `/api/teams` | any auth + TEAMS.CREATE permission | `{name, description?, avatar?}` | Create a team; caller becomes owner. 201 returns team. |
| `GET` | `/api/teams` | any auth | — | List all teams the caller belongs to. 200 team array. |
| `GET` | `/api/teams/:id` | member | — | Team detail with member list enriched with name/email/avatar. Non-members receive 404. |
| `PATCH` | `/api/teams/:id` | admin | `{name?, description?, avatar?}` | Update team metadata. At least one field required. 200 updated team. |
| `DELETE` | `/api/teams/:id` | owner | — | Delete team; cascades to all pending invites and ACL grants made to the team. 200 `{success:true}`. |

### Members

| Method | Path | Min role | Body | Behavior |
|---|---|---|---|---|
| `GET` | `/api/teams/:id/members` | member | — | List members with role, joinedAt, and profile info. |
| `DELETE` | `/api/teams/:id/members/:userId` | admin (or self) | — | Remove a member. Any member may remove themselves (self-leave). Owner cannot be removed; transfer ownership first. 200 `{success:true}`. |
| `PATCH` | `/api/teams/:id/members/:userId` | admin | `{role: 'admin'\|'member'}` | Change a member's role. Cannot demote the owner. 200 updated team. |
| `POST` | `/api/teams/:id/transfer` | owner | `{newOwnerId}` | Transfer ownership to an existing member. The caller becomes a member. 200 updated team. |

### Invitations

Members join only via invitation — there is no direct member-add endpoint.

| Method | Path | Min role | Body | Behavior |
|---|---|---|---|---|
| `POST` | `/api/teams/:id/invites` | admin | `{email, role: 'admin'\|'member'}` | Create an invite for the given email address. Sends an email with a deep-link accept URL when email is configured (best-effort; never fails the request). Response includes the invite token. |
| `GET` | `/api/teams/:id/invites` | admin | — | List pending invites for the team. Token is excluded from this response. |
| `DELETE` | `/api/teams/:id/invites/:inviteId` | admin | — | Revoke a pending invite. 200 `{success:true}`. |
| `GET` | `/api/teams/invites` | any auth | — | List the caller's own pending invites (matched by user id or email). Includes the token for use in accept/decline. |
| `POST` | `/api/teams/invites/:token/accept` | any auth (caller-bound) | — | Accept the invite. Validates that the invite belongs to the caller's email or user id. Adds caller as a member with the role on the invite. 200 `{team}`. |
| `POST` | `/api/teams/invites/:token/decline` | any auth (caller-bound) | — | Decline the invite. Caller-bound validation same as accept. 200 `{success:true}`. |

**Invite expiry:** invites expire after 7 days by default. Expired or already-accepted/declined invites return 410 Gone. A token stolen from another user cannot be redeemed (caller-binding enforced).

### Knowledge (Shared RAG)

| Method | Path | Min role | Body | Behavior |
|---|---|---|---|---|
| `POST` | `/api/teams/:id/knowledge` | admin | `{fileId}` | Attach a file to the team knowledge base. The file must be permanent (already saved — no TTL) and owned by the caller. Grants FILE_VIEWER to the team group. |
| `GET` | `/api/teams/:id/knowledge` | member | — | List files shared with this team. |
| `DELETE` | `/api/teams/:id/knowledge/:fileId` | admin | — | Remove a file from the team knowledge base. Revokes the team group's grant. 200 `{success:true}`. |

### Agent and Prompt Sharing

| Method | Path | Min role | Body | Behavior |
|---|---|---|---|---|
| `POST` | `/api/teams/:id/agents/:agentId` | admin | — | Share an agent with the team. Caller must hold SHARE rights on the agent. Grants AGENT_VIEWER to the team group. |
| `DELETE` | `/api/teams/:id/agents/:agentId` | admin | — | Revoke the team's access to an agent. |
| `GET` | `/api/teams/:id/agents` | member | — | List agents shared with this team. |
| `POST` | `/api/teams/:id/prompts/:promptGroupId` | admin | — | Share a prompt group with the team. Caller must hold SHARE rights on the prompt group. Grants PROMPTGROUP_VIEWER to the team group. |
| `DELETE` | `/api/teams/:id/prompts/:promptGroupId` | admin | — | Revoke the team's access to a prompt group. |
| `GET` | `/api/teams/:id/prompts` | member | — | List prompt groups shared with this team. |

---

## Shared RAG

When a member starts a conversation with `file_search` enabled, the set of files searched includes:

- Files the member **owns**
- Files accessible through an **agent's tool resources**
- Files **shared with any team the member belongs to**

Only files that have been embedded (status `embedded: true`) are included in RAG queries — non-embedded files are excluded automatically.

**Preconditions for sharing a file:**
1. The file must be **permanent** — it must have been saved by the user (the 1-hour TTL must have been removed). Uploading a file does not automatically make it permanent.
2. The caller sharing the file must be the **file's owner**.

**Access revocation** is immediate: removing a file from the team knowledge base (`DELETE /:id/knowledge/:fileId`) removes it from all members' RAG scope on the next query.

---

## Permissions and Configuration

### Interface permission: `TEAMS`

The `TEAMS` interface permission controls who may use and create teams.

| Permission | Default (USER role) | Effect when disabled |
|---|---|---|
| `TEAMS.USE` | `true` | Member cannot access the teams feature at all. |
| `TEAMS.CREATE` | `true` | Member cannot create new teams (but can still be a member of existing ones). |

Admins can restrict team creation by setting the USER role's `TEAMS.CREATE` to `false` in the admin panel (Roles & Permissions). This is the recommended way to gate the feature before a full rollout.

### `librechat.yaml` limits

Add a `teams` block to `librechat.yaml` to cap resource usage. Omitting the block entirely means no limits are enforced.

```yaml
teams:
  maxTeamsPerUser: 5        # Maximum teams a single user may own or create. Unlimited if unset.
  maxMembersPerTeam: 50     # Maximum members per team. Unlimited if unset.
  maxKnowledgeFilesPerTeam: 100  # Maximum files in a team's knowledge base. Unlimited if unset.
```

When a limit is reached, the relevant request returns **403 Forbidden**.

---

## Sub-groups (RBAC)

Sub-groups let you scope shared resources to a named subset of team members — for example, giving an Engineering group access to engineering docs while Legal sees only legal docs. Resources can still be shared with the whole team (the existing behavior) or with one or more specific sub-groups. Access is always additive: more group memberships mean more access, never less.

### Data model

A sub-group is a `Group` document with:

- `kind: 'team_subgroup'` — distinguishes it from the parent team (`kind: 'team'`) and admin-managed groups (`kind: 'group'`).
- `parentTeamId` — references the parent team Group.

Sub-groups are **flat** (one level; no nesting). Membership is **binary** (in or out; no per-sub-group roles). A user may belong to multiple sub-groups within the same team, and their accessible resource set is the union of all matching grants. Sub-group membership must be a **subset** of the parent team's membership — adding a user who is not a team member is rejected.

### API

#### Sub-group management

All sub-group management routes require at least `admin` role within the team.

| Method | Path | Body | Behavior |
|---|---|---|---|
| `POST` | `/api/teams/:id/subgroups` | `{name, description?}` | Create a sub-group. 201 returns `{subgroup}` with `_id`, `name`, `description`, `parentTeamId`, `memberCount`. Enforces `maxSubgroupsPerTeam` if configured (403 when limit reached). |
| `GET` | `/api/teams/:id/subgroups` | — | List all sub-groups with member counts. Admin/owner only. |
| `GET` | `/api/teams/:id/subgroups/:sgId` | — | Sub-group detail: metadata + enriched member list (name, email, avatar). |
| `PATCH` | `/api/teams/:id/subgroups/:sgId` | `{name?, description?}` | Rename or update description. At least one field required. |
| `DELETE` | `/api/teams/:id/subgroups/:sgId` | — | Delete sub-group; revokes all ACL grants made to it. 200 `{success:true}`. |
| `POST` | `/api/teams/:id/subgroups/:sgId/members` | `{userId}` | Add a team member to the sub-group. Rejects if the user is not already a team member. |
| `DELETE` | `/api/teams/:id/subgroups/:sgId/members/:userId` | — | Remove a member from the sub-group. 200 `{success:true}`. |

#### Targeted sharing

The existing share endpoints accept an optional `targetSubgroupId` to scope a grant to a sub-group instead of the whole team:

| Method | Path | Target param | Behavior |
|---|---|---|---|
| `POST` | `/:id/knowledge` | `targetSubgroupId` in request body | Share a file with the whole team (omitted) or a specific sub-group. |
| `DELETE` | `/:id/knowledge/:fileId` | `targetSubgroupId` as query param | Revoke the grant for the specified target (team or sub-group). |
| `POST` | `/:id/agents/:agentId` | `targetSubgroupId` in request body | Share an agent with the whole team or a specific sub-group. |
| `DELETE` | `/:id/agents/:agentId` | `targetSubgroupId` as query param | Revoke for the specified target. |
| `POST` | `/:id/prompts/:promptGroupId` | `targetSubgroupId` in request body | Share a prompt group with the whole team or a specific sub-group. |
| `DELETE` | `/:id/prompts/:promptGroupId` | `targetSubgroupId` as query param | Revoke for the specified target. |

When `targetSubgroupId` is omitted, behavior is unchanged from today (grant or revoke against the team principal). When provided, it must be a valid ObjectId that belongs to the given team, else 400/404.

#### List responses — `target` annotation

Every item in `GET /:id/knowledge`, `GET /:id/agents`, and `GET /:id/prompts` includes a `target` field indicating which principal holds the grant:

```json
{ "type": "team" }
{ "type": "subgroup", "id": "<sgId>", "name": "Engineering" }
```

**Members** see only resources granted to the team or to a sub-group they belong to (caller-scoped). **Owner/admin** see all grants across the team and every sub-group, each annotated with its target — for management purposes.

### Access semantics

- **Union, no deny.** A member's visible resource set is the union of team-wide grants and the grants of every sub-group they belong to. There are no negative/deny rules.
- **Members** cannot see sub-group structure (that is owner/admin-only). They simply see the resources they have access to.
- **RAG (file-search) path:** `findAccessibleResources` already resolves the caller's full principal set (user + every group they belong to), so a file granted to a sub-group is automatically included in that member's RAG scope. No special handling is required in the file-search hot path.

### Configuration limit

Add `maxSubgroupsPerTeam` to the `teams` block in `librechat.yaml` to cap how many sub-groups a team may have. Omitting it means no limit.

```yaml
teams:
  maxTeamsPerUser: 5
  maxMembersPerTeam: 50
  maxKnowledgeFilesPerTeam: 100
  maxSubgroupsPerTeam: 20   # Optional. Unlimited if unset.
```

When the limit is reached, `POST /:id/subgroups` returns **403 Forbidden**.

### Cascade behavior

| Trigger | Effect on sub-groups |
|---|---|
| Delete a sub-group | All ACL grants made to that sub-group are revoked immediately. |
| Remove a member from the team | The member is also removed from every sub-group of that team. |
| Delete the team | All sub-groups are deleted and their grants revoked (extends the existing team-delete cascade). |
| Delete a user | The user's sub-group memberships are cleaned up across all teams; for teams where the user is the sole owner with no other admins, the team and its sub-groups are deleted. |

Existing teams with no sub-groups behave exactly as before — all existing ACL grants remain on the team principal and are visible to every member.

---

## Lifecycle Notes

- **Invite expiry** — invites expire after 7 days by default. Expired invites are excluded at query time; no periodic cleanup job is required.
- **User deletion cascade** — when a user account is deleted:
  - Teams where the user is **not the owner**: the user is removed from `members`.
  - Teams where the user **is the owner and another admin exists**: ownership is automatically transferred to the first available admin before the user is removed.
  - Teams where the user **is the sole owner with no other admins**: the team, its pending invites, and all ACL grants made to the team are deleted.
- **Tenant isolation** — `tenantId` is set on all Group, TeamInvite, and ACL records. Team endpoints only operate on records belonging to the caller's tenant.
- **Admin-managed groups** — admin groups (`kind: 'group'`) are unaffected by the team endpoints. Team endpoints only act on records with `kind: 'team'`.
