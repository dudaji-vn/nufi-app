const mockGetUserById = jest.fn();
const mockDeleteMessages = jest.fn();
const mockDeleteAllUserSessions = jest.fn();
const mockDeleteUserById = jest.fn();
const mockDeleteAllSharedLinks = jest.fn();
const mockDeletePresets = jest.fn();
const mockDeleteUserKey = jest.fn();
const mockDeleteConvos = jest.fn();
const mockDeleteFiles = jest.fn();
const mockGetFiles = jest.fn();
const mockUpdateUserPlugins = jest.fn();
const mockUpdateUser = jest.fn();
const mockFindToken = jest.fn();
const mockVerifyOTPOrBackupCode = jest.fn();
const mockDeleteUserPluginAuth = jest.fn();
const mockProcessDeleteRequest = jest.fn();
const mockDeleteToolCalls = jest.fn();
const mockDeleteUserAgents = jest.fn();
const mockDeleteUserPrompts = jest.fn();
const mockDeleteUserSkills = jest.fn();
const mockGetUserTeams = jest.fn();
const mockRemoveTeamMember = jest.fn();
const mockTransferOwnership = jest.fn();
const mockDeleteInvitesByGroup = jest.fn();
const mockDeleteGroup = jest.fn();
const mockDeleteAclEntries = jest.fn();
const mockRemoveUserFromAllGroups = jest.fn();

jest.mock('@librechat/data-schemas', () => ({
  logger: { error: jest.fn(), info: jest.fn() },
  webSearchKeys: [],
}));

jest.mock('librechat-data-provider', () => ({
  Tools: {},
  CacheKeys: {},
  Constants: { mcp_delimiter: '::', mcp_prefix: 'mcp_' },
  FileSources: {},
}));

jest.mock('@librechat/api', () => ({
  MCPOAuthHandler: {},
  MCPTokenStorage: {},
  normalizeHttpError: jest.fn(),
  extractWebSearchEnvVars: jest.fn(),
  needsRefresh: jest.fn(),
  getNewS3URL: jest.fn(),
}));

jest.mock('~/models', () => ({
  deleteAllUserSessions: (...args) => mockDeleteAllUserSessions(...args),
  deleteAllSharedLinks: (...args) => mockDeleteAllSharedLinks(...args),
  updateUserPlugins: (...args) => mockUpdateUserPlugins(...args),
  deleteUserById: (...args) => mockDeleteUserById(...args),
  deleteMessages: (...args) => mockDeleteMessages(...args),
  deletePresets: (...args) => mockDeletePresets(...args),
  deleteUserKey: (...args) => mockDeleteUserKey(...args),
  getUserById: (...args) => mockGetUserById(...args),
  deleteConvos: (...args) => mockDeleteConvos(...args),
  deleteFiles: (...args) => mockDeleteFiles(...args),
  updateUser: (...args) => mockUpdateUser(...args),
  findToken: (...args) => mockFindToken(...args),
  getFiles: (...args) => mockGetFiles(...args),
  deleteToolCalls: (...args) => mockDeleteToolCalls(...args),
  deleteUserAgents: (...args) => mockDeleteUserAgents(...args),
  deleteUserPrompts: (...args) => mockDeleteUserPrompts(...args),
  deleteUserSkills: (...args) => mockDeleteUserSkills(...args),
  getUserTeams: (...args) => mockGetUserTeams(...args),
  removeTeamMember: (...args) => mockRemoveTeamMember(...args),
  transferOwnership: (...args) => mockTransferOwnership(...args),
  deleteInvitesByGroup: (...args) => mockDeleteInvitesByGroup(...args),
  deleteGroup: (...args) => mockDeleteGroup(...args),
  deleteTransactions: jest.fn(),
  deleteBalances: jest.fn(),
  deleteAllAgentApiKeys: jest.fn(),
  deleteAssistants: jest.fn(),
  deleteConversationTags: jest.fn(),
  deleteAllUserMemories: jest.fn(),
  deleteActions: jest.fn(),
  deleteTokens: jest.fn(),
  removeUserFromAllGroups: (...args) => mockRemoveUserFromAllGroups(...args),
  deleteAclEntries: (...args) => mockDeleteAclEntries(...args),
  getSoleOwnedResourceIds: jest.fn().mockResolvedValue([]),
}));

jest.mock('~/server/services/PluginService', () => ({
  updateUserPluginAuth: jest.fn(),
  deleteUserPluginAuth: (...args) => mockDeleteUserPluginAuth(...args),
}));

jest.mock('~/server/services/twoFactorService', () => ({
  verifyOTPOrBackupCode: (...args) => mockVerifyOTPOrBackupCode(...args),
}));

jest.mock('~/server/services/AuthService', () => ({
  verifyEmail: jest.fn(),
  resendVerificationEmail: jest.fn(),
}));

jest.mock('~/config', () => ({
  getMCPManager: jest.fn(),
  getFlowStateManager: jest.fn(),
  getMCPServersRegistry: jest.fn(),
}));

jest.mock('~/server/services/Config/getCachedTools', () => ({
  invalidateCachedTools: jest.fn(),
}));

jest.mock('~/server/services/Files/process', () => ({
  processDeleteRequest: (...args) => mockProcessDeleteRequest(...args),
}));

jest.mock('~/server/services/Config', () => ({
  getAppConfig: jest.fn(),
}));

jest.mock('~/cache', () => ({
  getLogStores: jest.fn(),
}));

const { deleteUserController } = require('~/server/controllers/UserController');

function createRes() {
  const res = {};
  res.status = jest.fn().mockReturnValue(res);
  res.json = jest.fn().mockReturnValue(res);
  res.send = jest.fn().mockReturnValue(res);
  return res;
}

function stubDeletionMocks() {
  mockDeleteMessages.mockResolvedValue();
  mockDeleteAllUserSessions.mockResolvedValue();
  mockDeleteUserKey.mockResolvedValue();
  mockDeletePresets.mockResolvedValue();
  mockDeleteConvos.mockResolvedValue();
  mockDeleteUserPluginAuth.mockResolvedValue();
  mockDeleteUserById.mockResolvedValue();
  mockDeleteAllSharedLinks.mockResolvedValue();
  mockGetFiles.mockResolvedValue([]);
  mockProcessDeleteRequest.mockResolvedValue();
  mockDeleteFiles.mockResolvedValue();
  mockDeleteToolCalls.mockResolvedValue();
  mockDeleteUserAgents.mockResolvedValue();
  mockDeleteUserPrompts.mockResolvedValue();
  mockDeleteUserSkills.mockResolvedValue(0);
  mockGetUserTeams.mockResolvedValue([]);
  mockRemoveTeamMember.mockResolvedValue();
  mockTransferOwnership.mockResolvedValue();
  mockDeleteInvitesByGroup.mockResolvedValue();
  mockDeleteGroup.mockResolvedValue();
  mockDeleteAclEntries.mockResolvedValue();
  mockRemoveUserFromAllGroups.mockResolvedValue();
}

beforeEach(() => {
  jest.clearAllMocks();
  stubDeletionMocks();
});

describe('deleteUserController - 2FA enforcement', () => {
  it('proceeds with deletion when 2FA is not enabled', async () => {
    const req = { user: { id: 'user1', _id: 'user1', email: 'a@b.com' }, body: {} };
    const res = createRes();
    mockGetUserById.mockResolvedValue({ _id: 'user1', twoFactorEnabled: false });

    await deleteUserController(req, res);

    expect(res.status).toHaveBeenCalledWith(200);
    expect(res.send).toHaveBeenCalledWith({ message: 'User deleted' });
    expect(mockDeleteMessages).toHaveBeenCalled();
    expect(mockDeleteUserAgents).toHaveBeenCalledWith('user1');
    expect(mockDeleteUserPrompts).toHaveBeenCalledWith('user1');
    expect(mockDeleteUserSkills).toHaveBeenCalledWith('user1');
    expect(mockVerifyOTPOrBackupCode).not.toHaveBeenCalled();
  });

  it('proceeds with deletion when user has no 2FA record', async () => {
    const req = { user: { id: 'user1', _id: 'user1', email: 'a@b.com' }, body: {} };
    const res = createRes();
    mockGetUserById.mockResolvedValue(null);

    await deleteUserController(req, res);

    expect(res.status).toHaveBeenCalledWith(200);
    expect(res.send).toHaveBeenCalledWith({ message: 'User deleted' });
  });

  it('returns error when 2FA is enabled and verification fails with 400', async () => {
    const req = { user: { id: 'user1', _id: 'user1' }, body: {} };
    const res = createRes();
    mockGetUserById.mockResolvedValue({
      _id: 'user1',
      twoFactorEnabled: true,
      totpSecret: 'enc-secret',
    });
    mockVerifyOTPOrBackupCode.mockResolvedValue({ verified: false, status: 400 });

    await deleteUserController(req, res);

    expect(res.status).toHaveBeenCalledWith(400);
    expect(mockDeleteMessages).not.toHaveBeenCalled();
  });

  it('returns 401 when 2FA is enabled and invalid TOTP token provided', async () => {
    const existingUser = {
      _id: 'user1',
      twoFactorEnabled: true,
      totpSecret: 'enc-secret',
    };
    const req = { user: { id: 'user1', _id: 'user1' }, body: { token: 'wrong' } };
    const res = createRes();
    mockGetUserById.mockResolvedValue(existingUser);
    mockVerifyOTPOrBackupCode.mockResolvedValue({
      verified: false,
      status: 401,
      message: 'Invalid token or backup code',
    });

    await deleteUserController(req, res);

    expect(mockVerifyOTPOrBackupCode).toHaveBeenCalledWith({
      user: existingUser,
      token: 'wrong',
      backupCode: undefined,
    });
    expect(res.status).toHaveBeenCalledWith(401);
    expect(res.json).toHaveBeenCalledWith({ message: 'Invalid token or backup code' });
    expect(mockDeleteMessages).not.toHaveBeenCalled();
  });

  it('returns 401 when 2FA is enabled and invalid backup code provided', async () => {
    const existingUser = {
      _id: 'user1',
      twoFactorEnabled: true,
      totpSecret: 'enc-secret',
      backupCodes: [],
    };
    const req = { user: { id: 'user1', _id: 'user1' }, body: { backupCode: 'bad-code' } };
    const res = createRes();
    mockGetUserById.mockResolvedValue(existingUser);
    mockVerifyOTPOrBackupCode.mockResolvedValue({
      verified: false,
      status: 401,
      message: 'Invalid token or backup code',
    });

    await deleteUserController(req, res);

    expect(mockVerifyOTPOrBackupCode).toHaveBeenCalledWith({
      user: existingUser,
      token: undefined,
      backupCode: 'bad-code',
    });
    expect(res.status).toHaveBeenCalledWith(401);
    expect(mockDeleteMessages).not.toHaveBeenCalled();
  });

  it('deletes account when valid TOTP token provided with 2FA enabled', async () => {
    const existingUser = {
      _id: 'user1',
      twoFactorEnabled: true,
      totpSecret: 'enc-secret',
    };
    const req = {
      user: { id: 'user1', _id: 'user1', email: 'a@b.com' },
      body: { token: '123456' },
    };
    const res = createRes();
    mockGetUserById.mockResolvedValue(existingUser);
    mockVerifyOTPOrBackupCode.mockResolvedValue({ verified: true });

    await deleteUserController(req, res);

    expect(mockVerifyOTPOrBackupCode).toHaveBeenCalledWith({
      user: existingUser,
      token: '123456',
      backupCode: undefined,
    });
    expect(res.status).toHaveBeenCalledWith(200);
    expect(res.send).toHaveBeenCalledWith({ message: 'User deleted' });
    expect(mockDeleteMessages).toHaveBeenCalled();
  });

  it('deletes account when valid backup code provided with 2FA enabled', async () => {
    const existingUser = {
      _id: 'user1',
      twoFactorEnabled: true,
      totpSecret: 'enc-secret',
      backupCodes: [{ codeHash: 'h1', used: false }],
    };
    const req = {
      user: { id: 'user1', _id: 'user1', email: 'a@b.com' },
      body: { backupCode: 'valid-code' },
    };
    const res = createRes();
    mockGetUserById.mockResolvedValue(existingUser);
    mockVerifyOTPOrBackupCode.mockResolvedValue({ verified: true });

    await deleteUserController(req, res);

    expect(mockVerifyOTPOrBackupCode).toHaveBeenCalledWith({
      user: existingUser,
      token: undefined,
      backupCode: 'valid-code',
    });
    expect(res.status).toHaveBeenCalledWith(200);
    expect(res.send).toHaveBeenCalledWith({ message: 'User deleted' });
    expect(mockDeleteMessages).toHaveBeenCalled();
  });
});

describe('deleteUserController - teams cascade', () => {
  const userId = 'user1';
  const req = { user: { id: userId, _id: userId, email: 'a@b.com' }, body: {} };

  beforeEach(() => {
    mockGetUserById.mockResolvedValue({ _id: userId, twoFactorEnabled: false });
  });

  it('transfers ownership to another admin and removes the deleted user when they own a team with another admin', async () => {
    const adminUserId = 'admin2';
    const teamId = 'team1';
    const team = {
      _id: teamId,
      ownerId: { toString: () => userId },
      members: [
        { userId: { toString: () => userId }, role: 'owner' },
        { userId: adminUserId, role: 'admin' },
      ],
    };
    mockGetUserTeams.mockResolvedValue([team]);

    const res = createRes();
    await deleteUserController(req, res);

    expect(mockTransferOwnership).toHaveBeenCalledWith({
      groupId: teamId,
      fromUserId: userId,
      toUserId: adminUserId,
    });
    expect(mockRemoveTeamMember).toHaveBeenCalledWith({ groupId: teamId, userId });
    expect(mockDeleteGroup).not.toHaveBeenCalled();
    expect(mockDeleteInvitesByGroup).not.toHaveBeenCalled();
    expect(res.status).toHaveBeenCalledWith(200);
  });

  it('deletes the team, its invites, and its by-principal ACL entries when the owner is the sole member', async () => {
    const teamId = 'team2';
    const team = {
      _id: teamId,
      ownerId: { toString: () => userId },
      members: [{ userId: { toString: () => userId }, role: 'owner' }],
    };
    mockGetUserTeams.mockResolvedValue([team]);

    const res = createRes();
    await deleteUserController(req, res);

    expect(mockDeleteInvitesByGroup).toHaveBeenCalledWith({ groupId: teamId });
    expect(mockDeleteAclEntries).toHaveBeenCalledWith({ principalId: teamId });
    expect(mockDeleteGroup).toHaveBeenCalledWith(teamId);
    expect(mockTransferOwnership).not.toHaveBeenCalled();
    expect(mockRemoveTeamMember).not.toHaveBeenCalled();
    expect(res.status).toHaveBeenCalledWith(200);
  });

  it('removes the user from members and memberIds when they are a non-owner team member', async () => {
    const ownerUserId = 'owner99';
    const teamId = 'team3';
    const team = {
      _id: teamId,
      ownerId: { toString: () => ownerUserId },
      members: [
        { userId: { toString: () => ownerUserId }, role: 'owner' },
        { userId: { toString: () => userId }, role: 'member' },
      ],
    };
    mockGetUserTeams.mockResolvedValue([team]);

    const res = createRes();
    await deleteUserController(req, res);

    expect(mockRemoveTeamMember).toHaveBeenCalledWith({ groupId: teamId, userId });
    expect(mockTransferOwnership).not.toHaveBeenCalled();
    expect(mockDeleteGroup).not.toHaveBeenCalled();
    expect(mockRemoveUserFromAllGroups).toHaveBeenCalledWith(userId);
    expect(res.status).toHaveBeenCalledWith(200);
  });
});
