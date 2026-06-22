import mongoose from 'mongoose';
import { v4 as uuidv4 } from 'uuid';
import { MongoMemoryServer } from 'mongodb-memory-server';
import {
  ResourceType,
  AccessRoleIds,
  PrincipalType,
  PermissionBits,
} from 'librechat-data-provider';
import type { AccessRole as TAccessRole, AclEntry as TAclEntry } from '..';
import type { Types } from 'mongoose';
import { createAclEntryMethods } from './aclEntry';
import { createModels } from '../models';
import { createMethods } from './index';

/** Lean access role object from .lean() */
type LeanAccessRole = TAccessRole & { _id: mongoose.Types.ObjectId };

/** Lean ACL entry from .lean() */
type LeanAclEntry = TAclEntry & { _id: mongoose.Types.ObjectId };

/** Tool resources shape for agent file access */
type AgentToolResources = {
  file_search?: { file_ids?: string[] };
  code_interpreter?: { file_ids?: string[] };
};

let File: mongoose.Model<unknown>;
let Agent: mongoose.Model<unknown>;
let AclEntry: mongoose.Model<unknown>;
let AccessRole: mongoose.Model<unknown>;
let User: mongoose.Model<unknown>;
let Group: mongoose.Model<unknown>;
let methods: ReturnType<typeof createMethods>;
let aclMethods: ReturnType<typeof createAclEntryMethods>;

describe('File Access Control', () => {
  let mongoServer: MongoMemoryServer;

  beforeAll(async () => {
    mongoServer = await MongoMemoryServer.create();
    const mongoUri = mongoServer.getUri();
    await mongoose.connect(mongoUri);

    createModels(mongoose);
    File = mongoose.models.File;
    Agent = mongoose.models.Agent;
    AclEntry = mongoose.models.AclEntry;
    AccessRole = mongoose.models.AccessRole;
    User = mongoose.models.User;
    Group = mongoose.models.Group;

    methods = createMethods(mongoose);
    aclMethods = createAclEntryMethods(mongoose);

    // Seed default access roles
    await methods.seedDefaultRoles();
  });

  afterAll(async () => {
    const collections = mongoose.connection.collections;
    for (const key in collections) {
      await collections[key].deleteMany({});
    }
    await mongoose.disconnect();
    await mongoServer.stop();
  });

  beforeEach(async () => {
    await File.deleteMany({});
    await Agent.deleteMany({});
    await AclEntry.deleteMany({});
    await User.deleteMany({});
    await Group.deleteMany({});
  });

  describe('File ACL entry operations', () => {
    it('should create ACL entries for agent file access', async () => {
      const userId = new mongoose.Types.ObjectId();
      const authorId = new mongoose.Types.ObjectId();
      const agentId = uuidv4();
      const fileIds = [uuidv4(), uuidv4(), uuidv4(), uuidv4()];

      // Create users
      await User.create({
        _id: userId,
        email: 'user@example.com',
        emailVerified: true,
        provider: 'local',
      });

      await User.create({
        _id: authorId,
        email: 'author@example.com',
        emailVerified: true,
        provider: 'local',
      });

      // Create files
      for (const fileId of fileIds) {
        await methods.createFile({
          user: authorId,
          file_id: fileId,
          filename: `file-${fileId}.txt`,
          filepath: `/uploads/${fileId}`,
        });
      }

      // Create agent with only first two files attached
      const agent = await methods.createAgent({
        id: agentId,
        name: 'Test Agent',
        author: authorId,
        model: 'gpt-4',
        provider: 'openai',
        tool_resources: {
          file_search: {
            file_ids: [fileIds[0], fileIds[1]],
          },
        },
      });

      // Grant EDIT permission to user on the agent
      const editorRole = (await AccessRole.findOne({
        accessRoleId: AccessRoleIds.AGENT_EDITOR,
      }).lean()) as LeanAccessRole | null;

      if (editorRole) {
        await aclMethods.grantPermission(
          PrincipalType.USER,
          userId,
          ResourceType.AGENT,
          agent._id as string | Types.ObjectId,
          editorRole.permBits,
          authorId,
          undefined,
          editorRole._id,
        );
      }

      // Verify ACL entry exists for the user
      const aclEntry = (await AclEntry.findOne({
        principalType: PrincipalType.USER,
        principalId: userId,
        resourceType: ResourceType.AGENT,
        resourceId: agent._id,
      }).lean()) as LeanAclEntry | null;

      expect(aclEntry).toBeTruthy();

      // Check that agent has correct file_ids in tool_resources
      const agentRecord = await methods.getAgent({ id: agentId });
      const toolResources = agentRecord?.tool_resources as AgentToolResources | undefined;
      expect(toolResources?.file_search?.file_ids).toContain(fileIds[0]);
      expect(toolResources?.file_search?.file_ids).toContain(fileIds[1]);
      expect(toolResources?.file_search?.file_ids).not.toContain(fileIds[2]);
      expect(toolResources?.file_search?.file_ids).not.toContain(fileIds[3]);
    });

    it('should grant access to agent author via ACL', async () => {
      const authorId = new mongoose.Types.ObjectId();
      const agentId = uuidv4();

      await User.create({
        _id: authorId,
        email: 'author@example.com',
        emailVerified: true,
        provider: 'local',
      });

      const agent = await methods.createAgent({
        id: agentId,
        name: 'Test Agent',
        author: authorId,
        model: 'gpt-4',
        provider: 'openai',
      });

      // Grant owner permissions
      const ownerRole = (await AccessRole.findOne({
        accessRoleId: AccessRoleIds.AGENT_OWNER,
      }).lean()) as LeanAccessRole | null;

      if (ownerRole) {
        await aclMethods.grantPermission(
          PrincipalType.USER,
          authorId,
          ResourceType.AGENT,
          agent._id as string | Types.ObjectId,
          ownerRole.permBits,
          authorId,
          undefined,
          ownerRole._id,
        );
      }

      // Author should have full permission bits on the agent
      const hasView = await aclMethods.hasPermission(
        [{ principalType: PrincipalType.USER, principalId: authorId }],
        ResourceType.AGENT,
        agent._id as string | Types.ObjectId,
        PermissionBits.VIEW,
      );

      const hasEdit = await aclMethods.hasPermission(
        [{ principalType: PrincipalType.USER, principalId: authorId }],
        ResourceType.AGENT,
        agent._id as string | Types.ObjectId,
        PermissionBits.EDIT,
      );

      expect(hasView).toBe(true);
      expect(hasEdit).toBe(true);
    });

    it('should deny access when no ACL entry exists', async () => {
      const userId = new mongoose.Types.ObjectId();
      const agentId = new mongoose.Types.ObjectId();

      const hasAccess = await aclMethods.hasPermission(
        [{ principalType: PrincipalType.USER, principalId: userId }],
        ResourceType.AGENT,
        agentId,
        PermissionBits.VIEW,
      );

      expect(hasAccess).toBe(false);
    });

    it('should deny EDIT when user only has VIEW permission', async () => {
      const userId = new mongoose.Types.ObjectId();
      const authorId = new mongoose.Types.ObjectId();
      const agentId = uuidv4();

      await User.create({
        _id: userId,
        email: 'user@example.com',
        emailVerified: true,
        provider: 'local',
      });

      await User.create({
        _id: authorId,
        email: 'author@example.com',
        emailVerified: true,
        provider: 'local',
      });

      const agent = await methods.createAgent({
        id: agentId,
        name: 'View-Only Agent',
        author: authorId,
        model: 'gpt-4',
        provider: 'openai',
      });

      // Grant only VIEW permission
      const viewerRole = (await AccessRole.findOne({
        accessRoleId: AccessRoleIds.AGENT_VIEWER,
      }).lean()) as LeanAccessRole | null;

      if (viewerRole) {
        await aclMethods.grantPermission(
          PrincipalType.USER,
          userId,
          ResourceType.AGENT,
          agent._id as string | Types.ObjectId,
          viewerRole.permBits,
          authorId,
          undefined,
          viewerRole._id,
        );
      }

      const canView = await aclMethods.hasPermission(
        [{ principalType: PrincipalType.USER, principalId: userId }],
        ResourceType.AGENT,
        agent._id as string | Types.ObjectId,
        PermissionBits.VIEW,
      );

      const canEdit = await aclMethods.hasPermission(
        [{ principalType: PrincipalType.USER, principalId: userId }],
        ResourceType.AGENT,
        agent._id as string | Types.ObjectId,
        PermissionBits.EDIT,
      );

      expect(canView).toBe(true);
      expect(canEdit).toBe(false);
    });

    it('should support role-based permission grants', async () => {
      const userId = new mongoose.Types.ObjectId();
      const authorId = new mongoose.Types.ObjectId();
      const agentId = uuidv4();

      await User.create({
        _id: userId,
        email: 'user@example.com',
        emailVerified: true,
        provider: 'local',
        role: 'ADMIN',
      });

      await User.create({
        _id: authorId,
        email: 'author@example.com',
        emailVerified: true,
        provider: 'local',
      });

      const agent = await methods.createAgent({
        id: agentId,
        name: 'Test Agent',
        author: authorId,
        model: 'gpt-4',
        provider: 'openai',
      });

      // Grant permission to ADMIN role
      const editorRole = (await AccessRole.findOne({
        accessRoleId: AccessRoleIds.AGENT_EDITOR,
      }).lean()) as LeanAccessRole | null;

      if (editorRole) {
        await aclMethods.grantPermission(
          PrincipalType.ROLE,
          'ADMIN',
          ResourceType.AGENT,
          agent._id as string | Types.ObjectId,
          editorRole.permBits,
          authorId,
          undefined,
          editorRole._id,
        );
      }

      // User with ADMIN role should have access through role-based ACL
      const hasAccess = await aclMethods.hasPermission(
        [
          { principalType: PrincipalType.USER, principalId: userId },
          {
            principalType: PrincipalType.ROLE,
            principalId: 'ADMIN' as unknown as mongoose.Types.ObjectId,
          },
        ],
        ResourceType.AGENT,
        agent._id as string | Types.ObjectId,
        PermissionBits.VIEW,
      );

      expect(hasAccess).toBe(true);
    });
  });

  describe('getFiles with file queries', () => {
    it('should return files created by user', async () => {
      const userId = new mongoose.Types.ObjectId();
      const fileId1 = `file_${uuidv4()}`;
      const fileId2 = `file_${uuidv4()}`;

      await methods.createFile({
        file_id: fileId1,
        user: userId,
        filename: 'file1.txt',
        filepath: '/uploads/file1.txt',
        type: 'text/plain',
        bytes: 100,
      });

      await methods.createFile({
        file_id: fileId2,
        user: new mongoose.Types.ObjectId(),
        filename: 'file2.txt',
        filepath: '/uploads/file2.txt',
        type: 'text/plain',
        bytes: 200,
      });

      const files = await methods.getFiles({ file_id: { $in: [fileId1, fileId2] } });
      expect(files).toHaveLength(2);
    });

    it('should return all files matching query', async () => {
      const userId = new mongoose.Types.ObjectId();
      const fileId1 = `file_${uuidv4()}`;
      const fileId2 = `file_${uuidv4()}`;

      await methods.createFile({
        file_id: fileId1,
        user: userId,
        filename: 'file1.txt',
        filepath: '/uploads/file1.txt',
      });

      await methods.createFile({
        file_id: fileId2,
        user: userId,
        filename: 'file2.txt',
        filepath: '/uploads/file2.txt',
      });

      const files = await methods.getFiles({ user: userId });
      expect(files).toHaveLength(2);
    });
  });

  /**
   * RAG sub-group union confirmation (Phase 2, Task 1).
   *
   * Proves that a file granted to a `kind:'team_subgroup'` principal is
   * included in the `findAccessibleResources` result for a user who belongs
   * to that sub-group — and is excluded for a user who does not.
   *
   * This is the lowest-possible-friction, highest-fidelity test: it exercises
   * the real ACL grant + principal-lookup chain that `getTeamSharedFileIds`
   * delegates to, without needing the full api-layer PermissionService stack.
   */
  describe('RAG sub-group union: file granted to sub-group reaches member, not non-member', () => {
    it('includes the file_id for a user in the sub-group and excludes it for a non-member', async () => {
      const owner = await User.create({
        email: 'owner@test.com',
        emailVerified: true,
        provider: 'local',
        name: 'Owner',
      });
      const member = await User.create({
        email: 'member@test.com',
        emailVerified: true,
        provider: 'local',
        name: 'Member',
      });
      const nonMember = await User.create({
        email: 'stranger@test.com',
        emailVerified: true,
        provider: 'local',
        name: 'Stranger',
      });

      // Build team + sub-group via methods so memberIds is always resolved correctly
      const team = await methods.createTeam({ name: 'RagTeam', ownerId: owner._id as Types.ObjectId });
      await methods.addTeamMember({ groupId: team._id as Types.ObjectId, userId: member._id as Types.ObjectId });

      const sg = await methods.createSubgroup({
        parentTeamId: team._id as Types.ObjectId,
        name: 'RagSub',
        ownerId: (owner._id as Types.ObjectId).toString(),
      });
      await methods.addSubgroupMember({
        subgroupId: sg._id as Types.ObjectId,
        userId: (member._id as Types.ObjectId).toString(),
      });

      // Create an embedded file (mirrors what getTeamSharedFileIds filters on)
      const fileId = uuidv4();
      const fileDoc = await methods.createFile(
        {
          file_id: fileId,
          user: owner._id as Types.ObjectId,
          filename: 'rag-test.txt',
          filepath: '/uploads/rag-test.txt',
          embedded: true,
        },
        true, // disableTTL so the document persists
      );

      // Look up the FILE_VIEWER role to get its permBits
      const fileViewerRole = (await AccessRole.findOne({
        accessRoleId: AccessRoleIds.FILE_VIEWER,
      }).lean()) as (TAccessRole & { _id: Types.ObjectId }) | null;
      expect(fileViewerRole).not.toBeNull();

      // Grant FILE VIEW to the sub-group (not the team, not any user directly)
      await aclMethods.grantPermission(
        PrincipalType.GROUP,
        sg._id as Types.ObjectId,
        ResourceType.FILE,
        (fileDoc as { _id: Types.ObjectId })._id,
        fileViewerRole!.permBits,
        owner._id as Types.ObjectId,
        undefined,
        fileViewerRole!._id,
      );

      // Member's principals include the sub-group → file must be visible
      const memberPrincipals = await methods.getUserPrincipals({ userId: member._id as Types.ObjectId });
      const memberSubgroupIds = memberPrincipals
        .filter((p) => p.principalType === PrincipalType.GROUP)
        .map((p) => p.principalId?.toString());
      expect(memberSubgroupIds).toContain((sg._id as Types.ObjectId).toString());

      const memberAccessible = await methods.findAccessibleResources(
        memberPrincipals,
        ResourceType.FILE,
        PermissionBits.VIEW,
      );
      expect(memberAccessible.map((id) => id.toString())).toContain(
        (fileDoc as { _id: Types.ObjectId })._id.toString(),
      );

      // Non-member's principals do NOT include the sub-group → file must NOT be visible
      const nonMemberPrincipals = await methods.getUserPrincipals({ userId: nonMember._id as Types.ObjectId });
      const nonMemberSubgroupIds = nonMemberPrincipals
        .filter((p) => p.principalType === PrincipalType.GROUP)
        .map((p) => p.principalId?.toString());
      expect(nonMemberSubgroupIds).not.toContain((sg._id as Types.ObjectId).toString());

      const nonMemberAccessible = await methods.findAccessibleResources(
        nonMemberPrincipals,
        ResourceType.FILE,
        PermissionBits.VIEW,
      );
      expect(nonMemberAccessible.map((id) => id.toString())).not.toContain(
        (fileDoc as { _id: Types.ObjectId })._id.toString(),
      );
    });
  });
});
