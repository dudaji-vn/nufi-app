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
  await User.create({
    _id: id,
    name: 'Test User ' + id,
    email: `user-${id}@test.com`,
    provider: 'local',
    ...overrides,
  });
  return { _id: id, id: id.toString() };
}

function createApp(user) {
  const { createTeamsHandlers } = require('@librechat/api');

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

  const app = express();
  app.use(express.json());
  app.use((req, _res, next) => {
    req.user = user;
    next();
  });

  const router = express.Router();
  router.post('/', handlers.create);
  router.get('/', handlers.list);
  router.get('/:id', handlers.get);
  router.patch('/:id', handlers.update);
  router.delete('/:id', handlers.remove);
  router.get('/:id/members', handlers.listMembers);
  router.delete('/:id/members/:userId', handlers.removeMember);
  router.patch('/:id/members/:userId', handlers.changeMemberRole);
  router.post('/:id/transfer', handlers.transferOwnership);
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
