const express = require('express');
const request = require('supertest');
const mongoose = require('mongoose');
const { MongoMemoryServer } = require('mongodb-memory-server');
const { createModels, createMethods } = require('@librechat/data-schemas');

/**
 * Wiring guard: mounts the REAL teams.js router and exercises GET /:id/knowledge
 * and GET /:id/agents as a plain team member. If getUserTeamPrincipals is missing
 * from the knowledgeHandlers factory call, the handler throws → 500.
 */

jest.mock('~/server/middleware', () => ({
  requireJwtAuth: (_req, _res, next) => next(),
  checkBan: (_req, _res, next) => next(),
}));

jest.mock('~/server/middleware/config/app', () => (_req, _res, next) => next());

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

jest.mock('~/server/services/PermissionService', () => ({
  grantPermission: jest.fn().mockResolvedValue({}),
  checkPermission: jest.fn().mockResolvedValue(true),
}));

jest.mock('@librechat/data-schemas', () => ({
  ...jest.requireActual('@librechat/data-schemas'),
  getTransactionSupport: jest.fn().mockResolvedValue(false),
}));

// Mock ~/models — teams.js imports it for db methods + getRoleByName.
jest.mock('~/models', () => {
  const { PermissionTypes, Permissions } = require('librechat-data-provider');
  const fullTeamsRole = {
    permissions: {
      [PermissionTypes.TEAMS]: {
        [Permissions.USE]: true,
        [Permissions.CREATE]: true,
      },
    },
  };

  const placeholder = () => {
    throw new Error('db not yet initialised');
  };

  return {
    getRoleByName: jest.fn().mockResolvedValue(fullTeamsRole),
    createTeam: placeholder,
    getUserTeams: placeholder,
    getTeamRole: placeholder,
    findGroupById: placeholder,
    updateGroupById: placeholder,
    deleteGroup: placeholder,
    removeTeamMember: placeholder,
    setMemberRole: placeholder,
    transferOwnership: placeholder,
    deleteInvitesByGroup: placeholder,
    findUsers: placeholder,
    createInvite: placeholder,
    findInviteByToken: placeholder,
    listPendingInvitesForUser: placeholder,
    listInvitesForTeam: placeholder,
    acceptInvite: placeholder,
    declineInvite: placeholder,
    revokeInvite: placeholder,
    addTeamMember: placeholder,
    findUser: placeholder,
    findFileById: placeholder,
    getFiles: placeholder,
    findEntriesByPrincipal: placeholder,
    revokePermission: placeholder,
    getAgent: placeholder,
    getPromptGroup: placeholder,
    getSubgroupById: placeholder,
    getTeamSubgroups: placeholder,
    getUserTeamPrincipals: placeholder,
    createSubgroup: placeholder,
    updateSubgroup: placeholder,
    deleteSubgroup: placeholder,
    addSubgroupMember: placeholder,
    removeSubgroupMember: placeholder,
    deleteAclEntries: placeholder,
  };
});

let mongoServer;
let db;

beforeAll(async () => {
  mongoServer = await MongoMemoryServer.create();
  await mongoose.connect(mongoServer.getUri());
  createModels(mongoose);
  db = createMethods(mongoose);

  const modelsModule = require('~/models');
  const fields = [
    'createTeam',
    'getUserTeams',
    'getTeamRole',
    'findGroupById',
    'updateGroupById',
    'deleteGroup',
    'removeTeamMember',
    'setMemberRole',
    'transferOwnership',
    'deleteInvitesByGroup',
    'findUsers',
    'createInvite',
    'findInviteByToken',
    'listPendingInvitesForUser',
    'listInvitesForTeam',
    'acceptInvite',
    'declineInvite',
    'revokeInvite',
    'addTeamMember',
    'findUser',
    'findFileById',
    'getFiles',
    'findEntriesByPrincipal',
    'revokePermission',
    'getAgent',
    'getPromptGroup',
    'getSubgroupById',
    'getTeamSubgroups',
    'getUserTeamPrincipals',
    'createSubgroup',
    'updateSubgroup',
    'deleteSubgroup',
    'addSubgroupMember',
    'removeSubgroupMember',
    'deleteAclEntries',
  ];
  for (const field of fields) {
    if (db[field]) {
      modelsModule[field] = db[field];
    }
  }
});

afterAll(async () => {
  await mongoose.disconnect();
  await mongoServer.stop();
});

afterEach(async () => {
  const Group = mongoose.models.Group;
  const TeamInvite = mongoose.models.TeamInvite;
  const User = mongoose.models.User;
  const AclEntry = mongoose.models.AclEntry;
  await Promise.all([
    Group.deleteMany({}),
    TeamInvite ? TeamInvite.deleteMany({}) : Promise.resolve(),
    User.deleteMany({}),
    AclEntry ? AclEntry.deleteMany({}) : Promise.resolve(),
  ]);
});

async function seedUser(overrides = {}) {
  const User = mongoose.models.User;
  const id = new mongoose.Types.ObjectId();
  const email = overrides.email ?? `user-${id}@test.com`;
  const role = overrides.role ?? 'USER';
  await User.create({
    _id: id,
    name: 'Test User ' + id,
    provider: 'local',
    ...overrides,
    email,
    role,
  });
  return { _id: id, id: id.toString(), email, role };
}

function createApp(user) {
  const teamsRouter = require('./teams');
  const app = express();
  app.use(express.json());
  app.use((req, _res, next) => {
    req.user = user;
    next();
  });
  app.use('/api/teams', teamsRouter);
  return app;
}

describe('Knowledge + Resource route wiring guard', () => {
  it('GET /:id/knowledge as a team member returns 200 (not 500)', async () => {
    const owner = await seedUser();
    const member = await seedUser();

    const ownerApp = createApp(owner);
    const memberApp = createApp(member);

    const createRes = await request(ownerApp)
      .post('/api/teams')
      .send({ name: 'Wiring Test Team' })
      .expect(201);

    const teamId = createRes.body.team._id;
    await db.addTeamMember({ groupId: teamId, userId: member.id, role: 'member' });

    const res = await request(memberApp).get(`/api/teams/${teamId}/knowledge`);

    expect(res.status).not.toBe(500);
    expect(res.status).toBe(200);
    expect(res.body).toHaveProperty('files');
  });

  it('GET /:id/agents as a team member returns 200 (not 500)', async () => {
    const owner = await seedUser();
    const member = await seedUser();

    const ownerApp = createApp(owner);
    const memberApp = createApp(member);

    const createRes = await request(ownerApp)
      .post('/api/teams')
      .send({ name: 'Agents Wiring Test Team' })
      .expect(201);

    const teamId = createRes.body.team._id;
    await db.addTeamMember({ groupId: teamId, userId: member.id, role: 'member' });

    const res = await request(memberApp).get(`/api/teams/${teamId}/agents`);

    expect(res.status).not.toBe(500);
    expect(res.status).toBe(200);
    expect(res.body).toHaveProperty('resources');
  });
});
