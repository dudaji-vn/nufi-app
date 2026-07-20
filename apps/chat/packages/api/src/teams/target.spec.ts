import { Types } from 'mongoose';
import type { IGroup } from '@librechat/data-schemas';
import { resolveShareTarget } from './target';
import type { ResolveShareTargetDeps } from './target';

describe('resolveShareTarget', () => {
  let getSubgroupById: jest.Mock;
  let deps: ResolveShareTargetDeps;
  let teamId: string;

  beforeEach(() => {
    teamId = new Types.ObjectId().toString();
    getSubgroupById = jest.fn();
    deps = { getSubgroupById };
  });

  describe('no targetSubgroupId', () => {
    it('should return ok: true with principalId = teamId when targetSubgroupId is undefined', async () => {
      const result = await resolveShareTarget(deps, teamId);

      expect(result).toEqual({ ok: true, principalId: teamId });
      expect(getSubgroupById).not.toHaveBeenCalled();
    });

    it('should return ok: true with principalId = teamId when targetSubgroupId is empty string', async () => {
      const result = await resolveShareTarget(deps, teamId, '');

      expect(result).toEqual({ ok: true, principalId: teamId });
      expect(getSubgroupById).not.toHaveBeenCalled();
    });
  });

  describe('malformed targetSubgroupId', () => {
    it('should return status: 400 and not call getSubgroupById for non-ObjectId string', async () => {
      const result = await resolveShareTarget(deps, teamId, 'not-an-id');

      expect(result).toEqual({ ok: false, status: 400 });
      expect(getSubgroupById).not.toHaveBeenCalled();
    });

    it('should return status: 400 and not call getSubgroupById for invalid hex string', async () => {
      const result = await resolveShareTarget(deps, teamId, 'zzzzzzzzzzzzzzzzzzzzzz');

      expect(result).toEqual({ ok: false, status: 400 });
      expect(getSubgroupById).not.toHaveBeenCalled();
    });
  });

  describe('valid targetSubgroupId', () => {
    let subgroupId: string;

    beforeEach(() => {
      subgroupId = new Types.ObjectId().toString();
    });

    it('should return ok: true with principalId = subgroupId when subgroup belongs to team', async () => {
      const subgroup: IGroup = {
        _id: new Types.ObjectId(subgroupId),
        name: 'Test Subgroup',
        kind: 'team_subgroup',
        parentTeamId: new Types.ObjectId(teamId),
        members: [],
        memberIds: [],
      } as unknown as IGroup;

      getSubgroupById.mockResolvedValue(subgroup);

      const result = await resolveShareTarget(deps, teamId, subgroupId);

      expect(result).toEqual({ ok: true, principalId: subgroupId });
      expect(getSubgroupById).toHaveBeenCalledWith(subgroupId);
    });

    it('should return status: 404 when subgroup does not exist', async () => {
      getSubgroupById.mockResolvedValue(null);

      const result = await resolveShareTarget(deps, teamId, subgroupId);

      expect(result).toEqual({ ok: false, status: 404 });
      expect(getSubgroupById).toHaveBeenCalledWith(subgroupId);
    });

    it('should return status: 404 when subgroup belongs to a different team', async () => {
      const otherTeamId = new Types.ObjectId().toString();
      const subgroup: IGroup = {
        _id: new Types.ObjectId(subgroupId),
        name: 'Test Subgroup',
        kind: 'team_subgroup',
        parentTeamId: new Types.ObjectId(otherTeamId),
        members: [],
        memberIds: [],
      } as unknown as IGroup;

      getSubgroupById.mockResolvedValue(subgroup);

      const result = await resolveShareTarget(deps, teamId, subgroupId);

      expect(result).toEqual({ ok: false, status: 404 });
      expect(getSubgroupById).toHaveBeenCalledWith(subgroupId);
    });
  });
});
