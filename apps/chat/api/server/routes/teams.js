const express = require('express');
const { createTeamsHandlers } = require('@librechat/api');
const { requireJwtAuth, checkBan } = require('~/server/middleware');
const db = require('~/models');

const router = express.Router();

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

router.use(requireJwtAuth, checkBan);

router.post('/', handlers.create);
router.get('/', handlers.list);
router.get('/:id', handlers.get);
router.patch('/:id', handlers.update);
router.delete('/:id', handlers.remove);
router.get('/:id/members', handlers.listMembers);
router.delete('/:id/members/:userId', handlers.removeMember);
router.patch('/:id/members/:userId', handlers.changeMemberRole);
router.post('/:id/transfer', handlers.transferOwnership);

module.exports = router;
