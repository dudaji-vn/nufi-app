const express = require('express');
const request = require('supertest');
const mongoose = require('mongoose');
const { MongoMemoryServer } = require('mongodb-memory-server');
const { createModels, createMethods } = require('@librechat/data-schemas');

/**
 * Integration test for the self-service teams routes.
 *
 * Auth middleware is bypassed so we can inject req.user directly.
 * All DB operations run against a real in-memory MongoDB instance.
 */

jest.mock('~/server/middleware', () => ({
  requireJwtAuth: (_req, _res, next) => next(),
  checkBan: (_req, _res, next) => next(),
}));

jest.mock('~/server/utils', () => ({
  ...jest.requireActual('~/server/utils'),
  sendEmail: jest.fn().mockResolvedValue({}),
}));

let mongoServer;
let db;

beforeAll(async () => {
  mongoServer = await MongoMemoryServer.create();
  await mongoose.connect(mongoServer.getUri());
  createModels(mongoose);
  db = createMethods(mongoose);
});

afterAll(async () => {
  await mongoose.disconnect();
  await mongoServer.stop();
});

afterEach(async () => {
  const Group = mongoose.models.Group;
  const TeamInvite = mongoose.models.TeamInvite;
  const User = mongoose.models.User;
  await Promise.all([Group.deleteMany({}), TeamInvite.deleteMany({}), User.deleteMany({})]);
});

function makeUserId() {
  return new mongoose.Types.ObjectId();
}

async function seedUser(overrides = {}) {
  const User = mongoose.models.User;
  const id = makeUserId();
  const email = overrides.email ?? `user-${id}@test.com`;
  await User.create({
    _id: id,
    name: 'Test User ' + id,
    provider: 'local',
    ...overrides,
    email,
  });
  return { _id: id, id: id.toString(), email };
}

function createApp(user) {
  const { createTeamsHandlers, createTeamInviteHandlers } = require('@librechat/api');

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

  const mockSendInviteEmail = jest.fn().mockResolvedValue(undefined);

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
    sendInviteEmail: mockSendInviteEmail,
  });

  const app = express();
  app.use(express.json());
  app.use((req, _res, next) => {
    req.user = user;
    next();
  });

  const router = express.Router();

  // Invite routes with no /:id prefix — MUST come before /:id routes
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

  app.use('/api/teams', router);

  return app;
}

describe('Teams Routes — Integration', () => {
  it('POST / creates a team (201) and GET / lists it for the owner', async () => {
    const owner = await seedUser();
    const app = createApp(owner);

    const createRes = await request(app)
      .post('/api/teams')
      .send({ name: 'Alpha Team', description: 'First team' })
      .expect(201);

    expect(createRes.body).toHaveProperty('team');
    expect(createRes.body.team.name).toBe('Alpha Team');
    expect(createRes.body.team.kind).toBe('team');

    const listRes = await request(app).get('/api/teams').expect(200);
    expect(listRes.body).toHaveProperty('teams');
    expect(listRes.body.teams.length).toBe(1);
    expect(listRes.body.teams[0].name).toBe('Alpha Team');
  });

  it('POST / returns 400 when name is missing', async () => {
    const owner = await seedUser();
    const app = createApp(owner);

    const res = await request(app).post('/api/teams').send({}).expect(400);
    expect(res.body).toHaveProperty('error', 'name is required');
  });

  it('GET /:id returns 404 for a non-member', async () => {
    const owner = await seedUser();
    const outsider = await seedUser();

    const ownerApp = createApp(owner);
    const createRes = await request(ownerApp)
      .post('/api/teams')
      .send({ name: 'Private Team' })
      .expect(201);

    const teamId = createRes.body.team._id;
    const outsiderApp = createApp(outsider);
    const res = await request(outsiderApp).get(`/api/teams/${teamId}`).expect(404);
    expect(res.body).toHaveProperty('error');
  });

  it('GET /:id returns team + members for a member', async () => {
    const owner = await seedUser();
    const app = createApp(owner);

    const createRes = await request(app)
      .post('/api/teams')
      .send({ name: 'Member Team' })
      .expect(201);

    const teamId = createRes.body.team._id;
    const getRes = await request(app).get(`/api/teams/${teamId}`).expect(200);

    expect(getRes.body).toHaveProperty('team');
    expect(getRes.body).toHaveProperty('members');
    expect(getRes.body.members.length).toBeGreaterThan(0);
    expect(getRes.body.members[0].role).toBe('owner');
  });

  it('DELETE /:id by non-owner returns 403/404; owner DELETE returns 200 and team is gone', async () => {
    const owner = await seedUser();
    const nonOwner = await seedUser();

    const ownerApp = createApp(owner);
    const createRes = await request(ownerApp)
      .post('/api/teams')
      .send({ name: 'Delete Test Team' })
      .expect(201);

    const teamId = createRes.body.team._id;

    const nonOwnerApp = createApp(nonOwner);
    const forbiddenRes = await request(nonOwnerApp).delete(`/api/teams/${teamId}`);
    expect([403, 404]).toContain(forbiddenRes.status);

    await request(ownerApp).delete(`/api/teams/${teamId}`).expect(200);

    const afterRes = await request(ownerApp).get('/api/teams').expect(200);
    expect(afterRes.body.teams).toHaveLength(0);
  });

  it('PATCH /:id by non-admin returns 403/404', async () => {
    const owner = await seedUser();
    const outsider = await seedUser();

    const ownerApp = createApp(owner);
    const createRes = await request(ownerApp)
      .post('/api/teams')
      .send({ name: 'Update Test Team' })
      .expect(201);

    const teamId = createRes.body.team._id;

    const outsiderApp = createApp(outsider);
    const res = await request(outsiderApp)
      .patch(`/api/teams/${teamId}`)
      .send({ name: 'Hacked Name' });
    expect([403, 404]).toContain(res.status);
  });

  it('transfer ownership → new owner is owner, old owner role is admin', async () => {
    const owner = await seedUser();
    const newOwner = await seedUser();

    const ownerApp = createApp(owner);
    const createRes = await request(ownerApp)
      .post('/api/teams')
      .send({ name: 'Transfer Team' })
      .expect(201);

    const teamId = createRes.body.team._id;

    await db.addTeamMember({ groupId: teamId, userId: newOwner.id, role: 'member' });

    const transferRes = await request(ownerApp)
      .post(`/api/teams/${teamId}/transfer`)
      .send({ newOwnerId: newOwner.id })
      .expect(200);

    expect(transferRes.body).toHaveProperty('team');

    const oldOwnerRole = await db.getTeamRole({ groupId: teamId, userId: owner.id });
    const newOwnerRole = await db.getTeamRole({ groupId: teamId, userId: newOwner.id });

    expect(newOwnerRole).toBe('owner');
    expect(oldOwnerRole).toBe('admin');
  });

  it('member self-leave via DELETE /:id/members/:userId succeeds', async () => {
    const owner = await seedUser();
    const member = await seedUser();

    const ownerApp = createApp(owner);
    const createRes = await request(ownerApp)
      .post('/api/teams')
      .send({ name: 'Leave Team' })
      .expect(201);

    const teamId = createRes.body.team._id;

    await db.addTeamMember({ groupId: teamId, userId: member.id, role: 'member' });

    const memberApp = createApp(member);
    await request(memberApp).delete(`/api/teams/${teamId}/members/${member.id}`).expect(200);

    const roleAfter = await db.getTeamRole({ groupId: teamId, userId: member.id });
    expect(roleAfter).toBeNull();
  });

  it('non-member cannot remove another member (403/404)', async () => {
    const owner = await seedUser();
    const member = await seedUser();
    const outsider = await seedUser();

    const ownerApp = createApp(owner);
    const createRes = await request(ownerApp)
      .post('/api/teams')
      .send({ name: 'Remove Member Test' })
      .expect(201);

    const teamId = createRes.body.team._id;
    await db.addTeamMember({ groupId: teamId, userId: member.id, role: 'member' });

    const outsiderApp = createApp(outsider);
    const res = await request(outsiderApp).delete(`/api/teams/${teamId}/members/${member.id}`);
    expect([403, 404]).toContain(res.status);
  });

  it('delete cascade: invite for team is deleted when team is deleted', async () => {
    const owner = await seedUser();
    const ownerApp = createApp(owner);

    const createRes = await request(ownerApp)
      .post('/api/teams')
      .send({ name: 'Cascade Team' })
      .expect(201);

    const teamId = createRes.body.team._id;

    await db.createInvite({
      groupId: teamId,
      email: 'invitee@test.com',
      role: 'member',
      invitedBy: owner.id,
    });

    const before = await db.listInvitesForTeam({ groupId: teamId });
    expect(before.length).toBe(1);

    await request(ownerApp).delete(`/api/teams/${teamId}`).expect(200);

    const after = await db.listInvitesForTeam({ groupId: teamId });
    expect(after.length).toBe(0);
  });

  it('PATCH /:id/members/:userId: non-admin cannot change member role (403/404)', async () => {
    const owner = await seedUser();
    const member1 = await seedUser();
    const member2 = await seedUser();

    const ownerApp = createApp(owner);
    const createRes = await request(ownerApp)
      .post('/api/teams')
      .send({ name: 'Role Change Test' })
      .expect(201);

    const teamId = createRes.body.team._id;
    await db.addTeamMember({ groupId: teamId, userId: member1.id, role: 'member' });
    await db.addTeamMember({ groupId: teamId, userId: member2.id, role: 'member' });

    const member1App = createApp(member1);
    const res = await request(member1App)
      .patch(`/api/teams/${teamId}/members/${member2.id}`)
      .send({ role: 'admin' });
    expect([403, 404]).toContain(res.status);
  });

  it('GET /:id/members: non-member gets 404', async () => {
    const owner = await seedUser();
    const outsider = await seedUser();

    const ownerApp = createApp(owner);
    const createRes = await request(ownerApp)
      .post('/api/teams')
      .send({ name: 'Members Test Team' })
      .expect(201);

    const teamId = createRes.body.team._id;

    const outsiderApp = createApp(outsider);
    const res = await request(outsiderApp).get(`/api/teams/${teamId}/members`);
    expect([403, 404]).toContain(res.status);
  });
});

describe('Team Invite Routes — Integration', () => {
  async function seedUserWithEmail(email, overrides = {}) {
    const User = mongoose.models.User;
    const id = makeUserId();
    await User.create({
      _id: id,
      name: 'Test User ' + id,
      email,
      provider: 'local',
      ...overrides,
    });
    return { _id: id, id: id.toString(), email };
  }

  it('POST /:id/invites: admin creates invite (201 with token); non-admin gets 403', async () => {
    const owner = await seedUser();
    const member = await seedUser();
    const ownerApp = createApp(owner);

    const createRes = await request(ownerApp)
      .post('/api/teams')
      .send({ name: 'Invite Team' })
      .expect(201);

    const teamId = createRes.body.team._id;
    await db.addTeamMember({ groupId: teamId, userId: member.id, role: 'member' });

    const inviteRes = await request(ownerApp)
      .post(`/api/teams/${teamId}/invites`)
      .send({ email: 'invitee@example.com', role: 'member' })
      .expect(201);

    expect(inviteRes.body).toHaveProperty('invite');
    expect(inviteRes.body.invite).toHaveProperty('token');
    expect(inviteRes.body.invite.email).toBe('invitee@example.com');

    const memberApp = createApp(member);
    const forbiddenRes = await request(memberApp)
      .post(`/api/teams/${teamId}/invites`)
      .send({ email: 'other@example.com', role: 'member' });
    expect(forbiddenRes.status).toBe(403);
  });

  it('GET /invites proves route ordering (hits listMine, not /:id handler)', async () => {
    const inviteeEmail = `invitee-${makeUserId()}@example.com`;
    const invitee = await seedUserWithEmail(inviteeEmail);
    const owner = await seedUser();
    const ownerApp = createApp(owner);

    const createRes = await request(ownerApp)
      .post('/api/teams')
      .send({ name: 'Route Order Team' })
      .expect(201);

    const teamId = createRes.body.team._id;

    await request(ownerApp)
      .post(`/api/teams/${teamId}/invites`)
      .send({ email: inviteeEmail, role: 'member' })
      .expect(201);

    const inviteeApp = createApp(invitee);
    const listRes = await request(inviteeApp).get('/api/teams/invites').expect(200);
    expect(listRes.body).toHaveProperty('invites');
    expect(listRes.body.invites.length).toBeGreaterThanOrEqual(1);
    const found = listRes.body.invites.find((inv) => inv.email === inviteeEmail);
    expect(found).toBeDefined();
    expect(found).toHaveProperty('token');
  });

  it('full flow: invite → listMine → accept → invitee is a member', async () => {
    const inviteeEmail = `acceptee-${makeUserId()}@example.com`;
    const invitee = await seedUserWithEmail(inviteeEmail);
    const owner = await seedUser();
    const ownerApp = createApp(owner);

    const createRes = await request(ownerApp)
      .post('/api/teams')
      .send({ name: 'Accept Flow Team' })
      .expect(201);

    const teamId = createRes.body.team._id;

    const inviteRes = await request(ownerApp)
      .post(`/api/teams/${teamId}/invites`)
      .send({ email: inviteeEmail, role: 'member' })
      .expect(201);

    const token = inviteRes.body.invite.token;

    const inviteeApp = createApp(invitee);
    const listRes = await request(inviteeApp).get('/api/teams/invites').expect(200);
    expect(listRes.body.invites.some((inv) => inv.token === token)).toBe(true);

    const acceptRes = await request(inviteeApp)
      .post(`/api/teams/invites/${token}/accept`)
      .expect(200);
    expect(acceptRes.body).toHaveProperty('team');

    const role = await db.getTeamRole({ groupId: teamId, userId: invitee.id });
    expect(role).toBe('member');
  });

  it('decline path: invitee declines invite → invite no longer pending', async () => {
    const inviteeEmail = `decliner-${makeUserId()}@example.com`;
    const invitee = await seedUserWithEmail(inviteeEmail);
    const owner = await seedUser();
    const ownerApp = createApp(owner);

    const createRes = await request(ownerApp)
      .post('/api/teams')
      .send({ name: 'Decline Flow Team' })
      .expect(201);

    const teamId = createRes.body.team._id;

    const inviteRes = await request(ownerApp)
      .post(`/api/teams/${teamId}/invites`)
      .send({ email: inviteeEmail, role: 'member' })
      .expect(201);

    const token = inviteRes.body.invite.token;

    const inviteeApp = createApp(invitee);
    const declineRes = await request(inviteeApp)
      .post(`/api/teams/invites/${token}/decline`)
      .expect(200);
    expect(declineRes.body).toHaveProperty('success', true);

    const role = await db.getTeamRole({ groupId: teamId, userId: invitee.id });
    expect(role).toBeNull();
  });

  it('revoke path: admin revokes invite → gone from GET /:id/invites', async () => {
    const owner = await seedUser();
    const ownerApp = createApp(owner);

    const createRes = await request(ownerApp)
      .post('/api/teams')
      .send({ name: 'Revoke Flow Team' })
      .expect(201);

    const teamId = createRes.body.team._id;

    const inviteRes = await request(ownerApp)
      .post(`/api/teams/${teamId}/invites`)
      .send({ email: 'revokee@example.com', role: 'member' })
      .expect(201);

    const inviteId = inviteRes.body.invite._id;

    const listBefore = await request(ownerApp).get(`/api/teams/${teamId}/invites`).expect(200);
    expect(listBefore.body.invites.some((inv) => inv._id === inviteId)).toBe(true);

    await request(ownerApp).delete(`/api/teams/${teamId}/invites/${inviteId}`).expect(200);

    const listAfter = await request(ownerApp).get(`/api/teams/${teamId}/invites`).expect(200);
    expect(listAfter.body.invites.some((inv) => inv._id === inviteId)).toBe(false);
  });

  it('stolen token: different user accepting returns 403', async () => {
    const inviteeEmail = `intended-${makeUserId()}@example.com`;
    await seedUserWithEmail(inviteeEmail);
    const thief = await seedUser();
    const owner = await seedUser();
    const ownerApp = createApp(owner);

    const createRes = await request(ownerApp)
      .post('/api/teams')
      .send({ name: 'Stolen Token Team' })
      .expect(201);

    const teamId = createRes.body.team._id;

    const inviteRes = await request(ownerApp)
      .post(`/api/teams/${teamId}/invites`)
      .send({ email: inviteeEmail, role: 'member' })
      .expect(201);

    const token = inviteRes.body.invite.token;

    const thiefApp = createApp(thief);
    const res = await request(thiefApp).post(`/api/teams/invites/${token}/accept`).expect(403);
    expect(res.body).toHaveProperty('error');
  });

  it('GET /:id/invites does NOT include token field', async () => {
    const owner = await seedUser();
    const ownerApp = createApp(owner);

    const createRes = await request(ownerApp)
      .post('/api/teams')
      .send({ name: 'Token Strip Team' })
      .expect(201);

    const teamId = createRes.body.team._id;

    await request(ownerApp)
      .post(`/api/teams/${teamId}/invites`)
      .send({ email: 'striptest@example.com', role: 'member' })
      .expect(201);

    const listRes = await request(ownerApp).get(`/api/teams/${teamId}/invites`).expect(200);
    expect(listRes.body.invites.length).toBeGreaterThan(0);
    for (const inv of listRes.body.invites) {
      expect(inv).not.toHaveProperty('token');
    }
  });
});
