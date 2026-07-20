# Team Workspaces — Phase 2: Invitations + Email (Spec)

Phase 2 of the master plan. Owner/admin invites people by email; invitees accept/decline; a team
member joins via accepted invite (the team API has no direct member-add by design). Decisions
[D7–D13](./team-workspaces-decisions.md). Builds on the Phase-0 invite data methods + Phase-1 route.

## 1. Architecture
```
packages/data-schemas .../teamInvite.ts   revokeInvite gains optional groupId guard (T1)
packages/api/src/teams/invites.ts          createTeamInviteHandlers(deps) — 6 handlers (T2)
packages/api/src/teams/invites.spec.ts     unit tests (mocked deps) (T2)
packages/api/src/teams/index.ts            + re-export invites (T3)
api/server/routes/teams.js                 + invite routes (ordered) + sendInviteEmail injection (T4)
api/server/routes/__tests__/teams.spec.js  + invite integration tests (T4)
```
Auth/guards unchanged (`requireJwtAuth, checkBan`). `caller = req.user.id`, `req.user.email` (lowercased).

## 2. Endpoints (added to the teams router; ORDER per D11)
Register the no-`:id` invite routes BEFORE the `/:id` routes:
| Method/Path | Min role | Behavior |
|---|---|---|
| `GET /api/teams/invites` | any auth | `listPendingInvitesForUser({userId:caller, email:req.user.email})`; enrich each with its team name; **include token** |
| `POST /api/teams/invites/:token/accept` | any auth (caller-bound) | validate (D12) → `addTeamMember` → `acceptInvite`; 200 `{team}` |
| `POST /api/teams/invites/:token/decline` | any auth (caller-bound) | validate caller-bound + pending → `declineInvite({token})`; 200 `{success:true}` |
Then the `/:id/invites` routes (distinct prefix, order-independent):
| `POST /api/teams/:id/invites` | admin | body `{email, role:'admin'\|'member'}`; resolve `invitedUserId=findUser({email})?._id`; `createInvite({groupId:id, email, role, invitedBy:caller, invitedUserId, tenantId:req.user.tenantId})`; then `sendInviteEmail?(...)`; 201 invite (**with token**) |
| `GET /api/teams/:id/invites` | admin | `listInvitesForTeam({groupId:id, status:'pending'})`; **strip token** |
| `DELETE /api/teams/:id/invites/:inviteId` | admin | `revokeInvite({inviteId, groupId:id})`; null→404; 200 `{success:true}` |

`resolveTeamAccess` (from Phase 1, exported/shared) gates the `/:id/invites` routes (admin min; 404
non-member, 403 member-below-admin). Reuse it — import from the teams handlers module.

## 3. Validation & errors (mirror Phase 1 style)
- `email` required + basic shape on create-invite → 400. `role ∈ {admin,member}` → 400.
- `:token` non-empty; `:inviteId` valid ObjectId → 400.
- Accept/decline caller-binding fail → **403**. Invite not found → 404. Found but not pending/ expired
  → **410 Gone** (`{error:'Invite is no longer valid'}`).
- Data-layer throws (e.g. addTeamMember rejecting bad role) → 409. Else `logger.error`+500.

## 4. `sendInviteEmail` (JS wrapper in teams.js, D8)
```js
const { checkEmailConfig } = require('@librechat/api');
const { sendEmail } = require('~/server/utils');
async function sendInviteEmail({ email, token, teamName, inviterName }) {
  if (!checkEmailConfig()) return;            // no-op when unconfigured
  await sendEmail({
    email, subject: `You're invited to ${teamName}`,
    payload: { appName: process.env.APP_TITLE || 'LibreChat', name: email,
      teamName, inviterName, inviteLink: `${process.env.DOMAIN_CLIENT}/teams/invite/${token}`,
      year: new Date().getFullYear() },
    template: 'inviteUser.handlebars', throwError: false,
  });
}
```
Inject into `createTeamInviteHandlers({ ..., sendInviteEmail })`. Handler calls it after `createInvite`
(best-effort; never fails the request). Unit tests inject a `jest.fn()` and assert it's called with
the right payload; also a test with `sendInviteEmail` omitted (undefined) still 201s.

## 5. Deps for `createTeamInviteHandlers`
`createInvite, findInviteByToken, listPendingInvitesForUser, listInvitesForTeam, acceptInvite,
declineInvite, revokeInvite, addTeamMember, findUser, findGroupById, getTeamRole` (+ reuse
`resolveTeamAccess`), and optional `sendInviteEmail`. No `any`; types from `@librechat/data-schemas`.

## 6. Tests
**Unit (`invites.spec.ts`):** each handler happy path + authz (admin gate on `/:id/invites`;
caller-binding 403 on accept/decline; 410 on expired/non-pending; token included/stripped correctly),
validation failures, `sendInviteEmail` called/omitted, accept composition calls addTeamMember then
acceptInvite.
**Integration (append to `teams.spec.js`):** real flow — admin invites email → invite created (token
present) → invitee `GET /invites` sees it → accept → invitee is now a member (role correct) →
re-list shows gone; decline path; revoke path; route-ordering proof (`GET /api/teams/invites` does
NOT hit the `:id` handler); non-admin invite → 403; stolen-token accept by wrong user → 403. Mailer
mocked/spied — NO real send.

## 7. Acceptance
Owner/admin invites by email; invitee sees + accepts → becomes a member with the assigned role;
decline & revoke work; expired/cross-user tokens rejected; email is best-effort + config-gated (no
hard fail, no real send in tests); `@librechat/api` + `@librechat/data-schemas` build clean; unit +
integration green; local FF-merge to `fork/main`.

## 8. Out of scope
FILE-ACL/shared-RAG (Phase 3), agent/prompt sharing (Phase 4), interface-permission/limits (Phase 6),
frontend (Phase 5), scheduled expiry sweep (D13).
