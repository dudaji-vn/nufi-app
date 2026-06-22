import mongoose from 'mongoose';
import { MongoMemoryServer } from 'mongodb-memory-server';
import groupSchema from './group';

describe('Group Schema', () => {
  let mongoServer: MongoMemoryServer;

  beforeAll(async () => {
    mongoServer = await MongoMemoryServer.create();
    const mongoUri = mongoServer.getUri();
    await mongoose.connect(mongoUri);
  });

  afterAll(async () => {
    await mongoose.disconnect();
    await mongoServer.stop();
  });

  it('persists a sub-group with kind team_subgroup and parentTeamId', async () => {
    const Group = mongoose.model('Group', groupSchema);
    const parentTeamId = new mongoose.Types.ObjectId();
    const sg = await Group.create({
      name: 'Engineering', kind: 'team_subgroup', parentTeamId,
      ownerId: new mongoose.Types.ObjectId(), memberIds: [], members: [],
    });
    const found = await Group.findById(sg._id).lean();
    expect(found?.kind).toBe('team_subgroup');
    expect(found?.parentTeamId?.toString()).toBe(parentTeamId.toString());
  });
});
