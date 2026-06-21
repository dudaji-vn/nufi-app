const express = require('express');
const {
  createTeamsHandlers,
  createTeamInviteHandlers,
  createTeamKnowledgeHandlers,
  createTeamResourceHandlers,
  checkEmailConfig,
} = require('@librechat/api');
const { requireJwtAuth, checkBan } = require('~/server/middleware');
const { sendEmail } = require('~/server/utils');
const PermissionService = require('~/server/services/PermissionService');
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

const knowledgeHandlers = createTeamKnowledgeHandlers({
  getTeamRole: db.getTeamRole,
  findGroupById: db.findGroupById,
  findFileById: db.findFileById,
  getFiles: db.getFiles,
  findEntriesByPrincipal: db.findEntriesByPrincipal,
  revokePermission: db.revokePermission,
  grantPermission: PermissionService.grantPermission,
});

router.post('/:id/knowledge', knowledgeHandlers.add);
router.get('/:id/knowledge', knowledgeHandlers.list);
router.delete('/:id/knowledge/:fileId', knowledgeHandlers.remove);

const resourceHandlers = createTeamResourceHandlers({
  getTeamRole: db.getTeamRole,
  findGroupById: db.findGroupById,
  getAgent: db.getAgent,
  getPromptGroup: db.getPromptGroup,
  findEntriesByPrincipal: db.findEntriesByPrincipal,
  revokePermission: db.revokePermission,
  grantPermission: PermissionService.grantPermission,
  checkPermission: PermissionService.checkPermission,
});

router.post('/:id/agents/:agentId', resourceHandlers.shareAgent);
router.delete('/:id/agents/:agentId', resourceHandlers.revokeAgent);
router.get('/:id/agents', resourceHandlers.listAgents);

router.post('/:id/prompts/:promptGroupId', resourceHandlers.sharePromptGroup);
router.delete('/:id/prompts/:promptGroupId', resourceHandlers.revokePromptGroup);
router.get('/:id/prompts', resourceHandlers.listPromptGroups);

module.exports = router;
