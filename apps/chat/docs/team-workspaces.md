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

## Lifecycle Notes

- **Invite expiry** — invites expire after 7 days by default. Expired invites are excluded at query time; no periodic cleanup job is required.
- **User deletion cascade** — when a user account is deleted:
  - Teams where the user is **not the owner**: the user is removed from `members`.
  - Teams where the user **is the owner and another admin exists**: ownership is automatically transferred to the first available admin before the user is removed.
  - Teams where the user **is the sole owner with no other admins**: the team, its pending invites, and all ACL grants made to the team are deleted.
- **Tenant isolation** — `tenantId` is set on all Group, TeamInvite, and ACL records. Team endpoints only operate on records belonging to the caller's tenant.
- **Admin-managed groups** — admin groups (`kind: 'group'`) are unaffected by the team endpoints. Team endpoints only act on records with `kind: 'team'`.
