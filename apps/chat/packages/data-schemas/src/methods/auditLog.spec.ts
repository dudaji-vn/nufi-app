import mongoose from 'mongoose';
import { MongoMemoryServer } from 'mongodb-memory-server';
import type * as t from '~/types';
import { createAuditLogMethods } from './auditLog';
import auditLogSchema from '~/schema/auditLog';

jest.mock('~/config/winston', () => ({
  error: jest.fn(),
  info: jest.fn(),
  debug: jest.fn(),
}));

let mongoServer: MongoMemoryServer;
let AuditLog: mongoose.Model<t.IAuditLog>;
let methods: ReturnType<typeof createAuditLogMethods>;

beforeAll(async () => {
  mongoServer = await MongoMemoryServer.create();
  await mongoose.connect(mongoServer.getUri());
  AuditLog = mongoose.models.AuditLog || mongoose.model<t.IAuditLog>('AuditLog', auditLogSchema);
  methods = createAuditLogMethods(mongoose);
});

afterAll(async () => {
  await mongoose.disconnect();
  await mongoServer.stop();
});

beforeEach(async () => {
  await mongoose.connection.dropDatabase();
});

async function seed() {
  await methods.createAuditLog({ action: 'user_created', actorName: 'admin' });
  await methods.createAuditLog({ action: 'grant_assigned', actorName: 'admin' });
  await methods.createAuditLog({
    action: 'guardrail_injection_blocked',
    actorName: 'system:guardrail',
    targetType: 'user',
    targetId: 'u1',
    metadata: { model: 'gpt-4o', source: 'heuristic' },
  });
  await methods.createAuditLog({
    action: 'guardrail_pii_output_redacted',
    actorName: 'system:guardrail',
    metadata: { piiTypes: { email: 2 } },
  });
}

describe('audit log category filtering + counts', () => {
  it('persists and returns the metadata object', async () => {
    await methods.createAuditLog({
      action: 'guardrail_injection_blocked',
      actorName: 'system:guardrail',
      metadata: { model: 'm', source: 'ai', piiTypes: { email: 1 } },
    });
    const [entry] = await methods.getAuditLogs({ category: 'security' });
    expect(entry.metadata).toEqual({ model: 'm', source: 'ai', piiTypes: { email: 1 } });
  });

  it('category=security returns only guardrail_ actions', async () => {
    await seed();
    const logs = await methods.getAuditLogs({ category: 'security' });
    expect(logs).toHaveLength(2);
    expect(logs.every((l) => l.action.startsWith('guardrail_'))).toBe(true);
  });

  it('category=admin excludes guardrail_ actions', async () => {
    await seed();
    const logs = await methods.getAuditLogs({ category: 'admin' });
    expect(logs).toHaveLength(2);
    expect(logs.some((l) => l.action.startsWith('guardrail_'))).toBe(false);
  });

  it('getAuditLogCounts groups by action within the filter', async () => {
    await seed();
    const counts = await methods.getAuditLogCounts({ category: 'security' });
    expect(counts).toEqual({
      guardrail_injection_blocked: 1,
      guardrail_pii_output_redacted: 1,
    });
  });
});
