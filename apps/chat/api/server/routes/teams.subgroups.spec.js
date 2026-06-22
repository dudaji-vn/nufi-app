const express = require('express');
const request = require('supertest');
const mongoose = require('mongoose');
const { MongoMemoryServer } = require('mongodb-memory-server');
const { createModels, createMethods } = require('@librechat/data-schemas');

/**
 * Integration test for the sub-group routes wired onto the teams router.
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

jest.mock('~/server/services/GraphApiService', () => ({
  entraIdPrincipalFeatureEnabled: jest.fn().mockReturnValue(false),
  getUserOwnedEntraGroups: jest.fn().mockResolvedValue([]),
  getUserEntraGroups: jest.fn().mockResolvedValue([]),
  getEntraGroupDetailsBatch: jest.fn().mockResolvedValue([]),
  getGroupMembers: jest.fn().mockResolvedValue([]),
  getGroupOwners: jest.fn().mockResolvedValue([]),
}));

jest.mock('@librechat/data-schemas', () => ({
  ...jest.requireActual('@librechat/data-schemas'),
  getTransactionSupport: jest.fn().mockResolvedValue(false),
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
  const User = mongoose.models.User;
  const AclEntry = mongoose.models.AclEntry;
  await Promise.all([
    Group.deleteMany({}),
    User.deleteMany({}),
    AclEntry && AclEntry.deleteMany({}),
  ]);
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

/**
 * Build a minimal express app wiring both the teams handlers and the
 * subgroup handlers onto the same router, mirroring what teams.js does.
 */
function createApp(user) {
  const { createTeamsHandlers, createSubgroupsHandlers } = require('@librechat/api');

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

  const subgroupHandlers = createSubgroupsHandlers({
    getTeamRole: db.getTeamRole,
    findGroupById: db.findGroupById,
    createSubgroup: db.createSubgroup,
    getTeamSubgroups: db.getTeamSubgroups,
    getSubgroupById: db.getSubgroupById,
    updateSubgroup: db.updateSubgroup,
    deleteSubgroup: db.deleteSubgroup,
    addSubgroupMember: db.addSubgroupMember,
    removeSubgroupMember: db.removeSubgroupMember,
    findUsers: db.findUsers,
    deleteAclEntries: db.deleteAclEntries,
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

  // Sub-group routes — must come after member routes
  router.post('/:id/subgroups', subgroupHandlers.create);
  router.get('/:id/subgroups', subgroupHandlers.list);
  router.get('/:id/subgroups/:sgId', subgroupHandlers.get);
  router.patch('/:id/subgroups/:sgId', subgroupHandlers.update);
  router.delete('/:id/subgroups/:sgId', subgroupHandlers.remove);
  router.post('/:id/subgroups/:sgId/members', subgroupHandlers.addMember);
  router.delete('/:id/subgroups/:sgId/members/:userId', subgroupHandlers.removeMember);

  app.use('/api/teams', router);
  return app;
}

describe('Sub-group Routes — Integration', () => {
  it('owner creates a sub-group → 201 with subgroup DTO', async () => {
    const owner = await seedUser();
    const app = createApp(owner);

    const createTeamRes = await request(app)
      .post('/api/teams')
      .send({ name: 'Alpha Team' })
      .expect(201);

    const teamId = createTeamRes.body.team._id;

    const res = await request(app)
      .post(`/api/teams/${teamId}/subgroups`)
      .send({ name: 'Squad A', description: 'First sub-group' })
      .expect(201);

    expect(res.body).toHaveProperty('subgroup');
    expect(res.body.subgroup.name).toBe('Squad A');
    expect(res.body.subgroup.parentTeamId).toBe(teamId);
    expect(res.body.subgroup).toHaveProperty('memberCount', 0);
  });

  it('plain team member (non-admin) cannot create a sub-group → 403', async () => {
    const owner = await seedUser();
    const member = await seedUser();

    const ownerApp = createApp(owner);
    const memberApp = createApp(member);

    const createTeamRes = await request(ownerApp)
      .post('/api/teams')
      .send({ name: 'Beta Team' })
      .expect(201);

    const teamId = createTeamRes.body.team._id;
    await db.addTeamMember({ groupId: teamId, userId: member.id, role: 'member' });

    const res = await request(memberApp)
      .post(`/api/teams/${teamId}/subgroups`)
      .send({ name: 'Unauthorized Sub-group' });

    expect(res.status).toBe(403);
    expect(res.body).toHaveProperty('error');
  });

  it('non-member cannot create a sub-group → 404', async () => {
    const owner = await seedUser();
    const outsider = await seedUser();

    const ownerApp = createApp(owner);
    const outsiderApp = createApp(outsider);

    const createTeamRes = await request(ownerApp)
      .post('/api/teams')
      .send({ name: 'Gamma Team' })
      .expect(201);

    const teamId = createTeamRes.body.team._id;

    const res = await request(outsiderApp)
      .post(`/api/teams/${teamId}/subgroups`)
      .send({ name: 'Outsider Sub-group' });

    expect(res.status).toBe(404);
  });

  it('add a real team member to a sub-group → 200 with updated memberCount', async () => {
    const owner = await seedUser();
    const member = await seedUser();

    const ownerApp = createApp(owner);

    const createTeamRes = await request(ownerApp)
      .post('/api/teams')
      .send({ name: 'Delta Team' })
      .expect(201);

    const teamId = createTeamRes.body.team._id;
    await db.addTeamMember({ groupId: teamId, userId: member.id, role: 'member' });

    const sgRes = await request(ownerApp)
      .post(`/api/teams/${teamId}/subgroups`)
      .send({ name: 'Squad B' })
      .expect(201);

    const sgId = sgRes.body.subgroup._id;

    const addRes = await request(ownerApp)
      .post(`/api/teams/${teamId}/subgroups/${sgId}/members`)
      .send({ userId: member.id })
      .expect(200);

    expect(addRes.body).toHaveProperty('subgroup');
    expect(addRes.body.subgroup.memberCount).toBe(1);
  });

  it('add a non-team-member to a sub-group → 400 (team-subset invariant)', async () => {
    const owner = await seedUser();
    const outsider = await seedUser();

    const ownerApp = createApp(owner);

    const createTeamRes = await request(ownerApp)
      .post('/api/teams')
      .send({ name: 'Epsilon Team' })
      .expect(201);

    const teamId = createTeamRes.body.team._id;

    const sgRes = await request(ownerApp)
      .post(`/api/teams/${teamId}/subgroups`)
      .send({ name: 'Squad C' })
      .expect(201);

    const sgId = sgRes.body.subgroup._id;

    const res = await request(ownerApp)
      .post(`/api/teams/${teamId}/subgroups/${sgId}/members`)
      .send({ userId: outsider.id });

    expect(res.status).toBe(400);
    expect(res.body).toHaveProperty('error');
    expect(res.body.error).toMatch(/not a member of the team/i);
  });

  it('GET /:id/subgroups lists sub-groups for the team', async () => {
    const owner = await seedUser();
    const app = createApp(owner);

    const createTeamRes = await request(app)
      .post('/api/teams')
      .send({ name: 'Zeta Team' })
      .expect(201);

    const teamId = createTeamRes.body.team._id;

    await request(app).post(`/api/teams/${teamId}/subgroups`).send({ name: 'Sub A' }).expect(201);
    await request(app).post(`/api/teams/${teamId}/subgroups`).send({ name: 'Sub B' }).expect(201);

    const listRes = await request(app).get(`/api/teams/${teamId}/subgroups`).expect(200);

    expect(listRes.body).toHaveProperty('subgroups');
    expect(listRes.body.subgroups).toHaveLength(2);
    const names = listRes.body.subgroups.map((sg) => sg.name);
    expect(names).toContain('Sub A');
    expect(names).toContain('Sub B');
  });

  it('GET /:id/subgroups/:sgId returns sub-group with members', async () => {
    const owner = await seedUser();
    const app = createApp(owner);

    const createTeamRes = await request(app)
      .post('/api/teams')
      .send({ name: 'Eta Team' })
      .expect(201);

    const teamId = createTeamRes.body.team._id;

    const sgRes = await request(app)
      .post(`/api/teams/${teamId}/subgroups`)
      .send({ name: 'Solo Sub' })
      .expect(201);

    const sgId = sgRes.body.subgroup._id;

    const getRes = await request(app)
      .get(`/api/teams/${teamId}/subgroups/${sgId}`)
      .expect(200);

    expect(getRes.body).toHaveProperty('subgroup');
    expect(getRes.body).toHaveProperty('members');
    expect(getRes.body.subgroup._id).toBe(sgId);
  });

  it('PATCH /:id/subgroups/:sgId updates sub-group name', async () => {
    const owner = await seedUser();
    const app = createApp(owner);

    const createTeamRes = await request(app)
      .post('/api/teams')
      .send({ name: 'Theta Team' })
      .expect(201);

    const teamId = createTeamRes.body.team._id;

    const sgRes = await request(app)
      .post(`/api/teams/${teamId}/subgroups`)
      .send({ name: 'Old Name' })
      .expect(201);

    const sgId = sgRes.body.subgroup._id;

    const patchRes = await request(app)
      .patch(`/api/teams/${teamId}/subgroups/${sgId}`)
      .send({ name: 'New Name' })
      .expect(200);

    expect(patchRes.body.subgroup.name).toBe('New Name');
  });

  it('DELETE /:id/subgroups/:sgId removes the sub-group', async () => {
    const owner = await seedUser();
    const app = createApp(owner);

    const createTeamRes = await request(app)
      .post('/api/teams')
      .send({ name: 'Iota Team' })
      .expect(201);

    const teamId = createTeamRes.body.team._id;

    const sgRes = await request(app)
      .post(`/api/teams/${teamId}/subgroups`)
      .send({ name: 'To Delete' })
      .expect(201);

    const sgId = sgRes.body.subgroup._id;

    await request(app).delete(`/api/teams/${teamId}/subgroups/${sgId}`).expect(200);

    const listRes = await request(app).get(`/api/teams/${teamId}/subgroups`).expect(200);
    expect(listRes.body.subgroups).toHaveLength(0);
  });

  it('DELETE /:id/subgroups/:sgId/members/:userId removes member from sub-group', async () => {
    const owner = await seedUser();
    const member = await seedUser();

    const ownerApp = createApp(owner);

    const createTeamRes = await request(ownerApp)
      .post('/api/teams')
      .send({ name: 'Kappa Team' })
      .expect(201);

    const teamId = createTeamRes.body.team._id;
    await db.addTeamMember({ groupId: teamId, userId: member.id, role: 'member' });

    const sgRes = await request(ownerApp)
      .post(`/api/teams/${teamId}/subgroups`)
      .send({ name: 'Squad D' })
      .expect(201);

    const sgId = sgRes.body.subgroup._id;

    await request(ownerApp)
      .post(`/api/teams/${teamId}/subgroups/${sgId}/members`)
      .send({ userId: member.id })
      .expect(200);

    const removeRes = await request(ownerApp)
      .delete(`/api/teams/${teamId}/subgroups/${sgId}/members/${member.id}`)
      .expect(200);

    expect(removeRes.body.subgroup.memberCount).toBe(0);
  });

  it('GET /:id/subgroups for invalid team ID → 400', async () => {
    const owner = await seedUser();
    const app = createApp(owner);

    const res = await request(app).get('/api/teams/not-an-objectid/subgroups');
    expect(res.status).toBe(400);
  });

  it('GET /:id/subgroups/:sgId for wrong team returns 404', async () => {
    const owner = await seedUser();
    const app = createApp(owner);

    const createTeamARes = await request(app)
      .post('/api/teams')
      .send({ name: 'Team A' })
      .expect(201);

    const createTeamBRes = await request(app)
      .post('/api/teams')
      .send({ name: 'Team B' })
      .expect(201);

    const teamAId = createTeamARes.body.team._id;
    const teamBId = createTeamBRes.body.team._id;

    const sgRes = await request(app)
      .post(`/api/teams/${teamAId}/subgroups`)
      .send({ name: 'Sub of A' })
      .expect(201);

    const sgId = sgRes.body.subgroup._id;

    // Try to access Team A's sub-group via Team B's route → should 404
    const res = await request(app).get(`/api/teams/${teamBId}/subgroups/${sgId}`);
    expect(res.status).toBe(404);
  });
});
