import mongoose from 'mongoose';
import { MongoMemoryServer } from 'mongodb-memory-server';
import { SystemRoles, Permissions, PermissionTypes } from 'librechat-data-provider';
import type { IRole } from '..';
import { createRoleMethods } from './role';
import { createModels } from '../models';

jest.mock('~/config/winston', () => ({
  error: jest.fn(),
  warn: jest.fn(),
  info: jest.fn(),
  debug: jest.fn(),
}));

let mongoServer: MongoMemoryServer;
let Role: mongoose.Model<IRole>;
let updateAccessPermissions: ReturnType<typeof createRoleMethods>['updateAccessPermissions'];
let getRoleByName: ReturnType<typeof createRoleMethods>['getRoleByName'];

beforeAll(async () => {
  mongoServer = await MongoMemoryServer.create();
  await mongoose.connect(mongoServer.getUri());
  createModels(mongoose);
  Role = mongoose.models.Role;
  const methods = createRoleMethods(mongoose);
  updateAccessPermissions = methods.updateAccessPermissions;
  getRoleByName = methods.getRoleByName;
});

afterAll(async () => {
  await mongoose.disconnect();
  await mongoServer.stop();
});

beforeEach(async () => {
  await Role.deleteMany({});
});

describe('TEAMS and FILES permission persistence (schema strict-mode regression)', () => {
  it('persists TEAMS.USE and TEAMS.CREATE via updateAccessPermissions', async () => {
    await new Role({ name: SystemRoles.USER, permissions: {} }).save();

    await updateAccessPermissions(SystemRoles.USER, {
      [PermissionTypes.TEAMS]: {
        [Permissions.USE]: true,
        [Permissions.CREATE]: true,
      },
    });

    const role = await getRoleByName(SystemRoles.USER);
    expect(role.permissions[PermissionTypes.TEAMS]?.[Permissions.USE]).toBe(true);
    expect(role.permissions[PermissionTypes.TEAMS]?.[Permissions.CREATE]).toBe(true);
  });

  it('persists FILES.USE, FILES.CREATE, FILES.SHARE, FILES.SHARE_PUBLIC via updateAccessPermissions', async () => {
    await new Role({ name: SystemRoles.USER, permissions: {} }).save();

    await updateAccessPermissions(SystemRoles.USER, {
      [PermissionTypes.FILES]: {
        [Permissions.USE]: true,
        [Permissions.CREATE]: true,
        [Permissions.SHARE]: false,
        [Permissions.SHARE_PUBLIC]: false,
      },
    });

    const role = await getRoleByName(SystemRoles.USER);
    expect(role.permissions[PermissionTypes.FILES]?.[Permissions.USE]).toBe(true);
    expect(role.permissions[PermissionTypes.FILES]?.[Permissions.CREATE]).toBe(true);
    expect(role.permissions[PermissionTypes.FILES]?.[Permissions.SHARE]).toBe(false);
    expect(role.permissions[PermissionTypes.FILES]?.[Permissions.SHARE_PUBLIC]).toBe(false);
  });

  it('persists TEAMS and FILES together in a single updateAccessPermissions call', async () => {
    await new Role({ name: SystemRoles.USER, permissions: {} }).save();

    await updateAccessPermissions(SystemRoles.USER, {
      [PermissionTypes.TEAMS]: {
        [Permissions.USE]: true,
        [Permissions.CREATE]: true,
      },
      [PermissionTypes.FILES]: {
        [Permissions.USE]: true,
        [Permissions.CREATE]: true,
        [Permissions.SHARE]: false,
        [Permissions.SHARE_PUBLIC]: false,
      },
    });

    const role = await getRoleByName(SystemRoles.USER);
    expect(role.permissions[PermissionTypes.TEAMS]?.[Permissions.CREATE]).toBe(true);
    expect(role.permissions[PermissionTypes.FILES]?.[Permissions.USE]).toBe(true);
  });

  it('round-trips TEAMS and FILES through a real Mongo write+read without Mongoose strict-mode dropping them', async () => {
    await new Role({ name: SystemRoles.USER, permissions: {} }).save();

    await updateAccessPermissions(SystemRoles.USER, {
      [PermissionTypes.TEAMS]: {
        [Permissions.USE]: true,
        [Permissions.CREATE]: true,
      },
      [PermissionTypes.FILES]: {
        [Permissions.USE]: true,
        [Permissions.CREATE]: true,
        [Permissions.SHARE]: false,
        [Permissions.SHARE_PUBLIC]: false,
      },
    });

    const raw = await Role.findOne({ name: SystemRoles.USER }).lean().exec();
    const perms = (raw as unknown as { permissions: Record<string, Record<string, boolean>> })
      .permissions;

    expect(perms[PermissionTypes.TEAMS]).toBeDefined();
    expect(perms[PermissionTypes.TEAMS][Permissions.USE]).toBe(true);
    expect(perms[PermissionTypes.TEAMS][Permissions.CREATE]).toBe(true);

    expect(perms[PermissionTypes.FILES]).toBeDefined();
    expect(perms[PermissionTypes.FILES][Permissions.USE]).toBe(true);
    expect(perms[PermissionTypes.FILES][Permissions.CREATE]).toBe(true);
    expect(perms[PermissionTypes.FILES][Permissions.SHARE]).toBe(false);
    expect(perms[PermissionTypes.FILES][Permissions.SHARE_PUBLIC]).toBe(false);
  });
});
