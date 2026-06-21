const express = require('express');
const {
  createTeamsHandlers,
  createTeamInviteHandlers,
  checkEmailConfig,
} = require('@librechat/api');
const { requireJwtAuth, checkBan } = require('~/server/middleware');
const { sendEmail } = require('~/server/utils');
const db = require('~/models');

const router = express.Router();

async function sendInviteEmail({ email, token, teamName, inviterName }) {
  if (!checkEmailConfig()) {
    return;
  }
  await sendEmail({
    email,
    subject: `You're invited to ${teamName || 'a team'}`,
    payload: {
      appName: process.env.APP_TITLE || 'LibreChat',
      name: email,
      teamName,
      inviterName,
      inviteLink: `${process.env.DOMAIN_CLIENT}/teams/invite/${token}`,
      year: new Date().getFullYear(),
    },
    template: 'inviteUser.handlebars',
    throwError: false,
  });
}

const handlers = createTeamsHandlers({
  createTeam: db.createTeam,
  getUserTeams: db.getUserTeams,
  getTeamRole: db.getTeamRole,
  findGroupById: db.findGroupById,
  updateGroupById: db.updateGroupById,
  deleteGroup: db.deleteGroup,
  removeTeamMember: db.removeTeamMember,
  setMemberRole: db.setMemberRole,
  transferOwnership: db.transferOwnership,
  deleteInvitesByGroup: db.deleteInvitesByGroup,
  findUsers: db.findUsers,
});

const inviteHandlers = createTeamInviteHandlers({
  createInvite: db.createInvite,
  findInviteByToken: db.findInviteByToken,
  listPendingInvitesForUser: db.listPendingInvitesForUser,
  listInvitesForTeam: db.listInvitesForTeam,
  acceptInvite: db.acceptInvite,
  declineInvite: db.declineInvite,
  revokeInvite: db.revokeInvite,
  addTeamMember: db.addTeamMember,
  findUser: db.findUser,
  findGroupById: db.findGroupById,
  getTeamRole: db.getTeamRole,
  sendInviteEmail,
});

router.use(requireJwtAuth, checkBan);

// Invite routes with no /:id prefix — MUST come before /:id routes to avoid collision
router.get('/invites', inviteHandlers.listMine);
router.post('/invites/:token/accept', inviteHandlers.accept);
router.post('/invites/:token/decline', inviteHandlers.decline);

router.post('/', handlers.create);
router.get('/', handlers.list);
router.get('/:id', handlers.get);
router.patch('/:id', handlers.update);
router.delete('/:id', handlers.remove);
router.get('/:id/members', handlers.listMembers);
router.delete('/:id/members/:userId', handlers.removeMember);
router.patch('/:id/members/:userId', handlers.changeMemberRole);
router.post('/:id/transfer', handlers.transferOwnership);

router.post('/:id/invites', inviteHandlers.create);
router.get('/:id/invites', inviteHandlers.listForTeam);
router.delete('/:id/invites/:inviteId', inviteHandlers.revoke);

module.exports = router;
