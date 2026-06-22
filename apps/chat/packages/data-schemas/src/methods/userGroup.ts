import { Types } from 'mongoose';
import { PrincipalType } from 'librechat-data-provider';
import type { TUser, TPrincipalSearchResult } from 'librechat-data-provider';
import type { Model, ClientSession, FilterQuery } from 'mongoose';
import type { TeamRole, IGroup, IRole, IUser } from '~/types';
import { escapeRegExp } from '~/utils/string';

export function createUserGroupMethods(mongoose: typeof import('mongoose')) {
  /**
   * Find a group by its ID
   * @param groupId - The group ID
   * @param projection - Optional projection of fields to return
   * @param session - Optional MongoDB session for transactions
   * @returns The group document or null if not found
   */
  async function findGroupById(
    groupId: string | Types.ObjectId,
    projection: Record<string, 0 | 1> = {},
    session?: ClientSession,
  ): Promise<IGroup | null> {
    const Group = mongoose.models.Group as Model<IGroup>;
    const query = Group.findOne({ _id: groupId }, projection);
    if (session) {
      query.session(session);
    }
    return await query.lean<IGroup>();
  }

  /**
   * Find a group by its external ID (e.g., Entra ID)
   * @param idOnTheSource - The external ID
   * @param source - The source ('entra' or 'local')
   * @param projection - Optional projection of fields to return
   * @param session - Optional MongoDB session for transactions
   * @returns The group document or null if not found
   */
  async function findGroupByExternalId(
    idOnTheSource: string,
    source: 'entra' | 'local' = 'entra',
    projection: Record<string, 0 | 1> = {},
    session?: ClientSession,
  ): Promise<IGroup | null> {
    const Group = mongoose.models.Group as Model<IGroup>;
    const query = Group.findOne({ idOnTheSource, source }, projection);
    if (session) {
      query.session(session);
    }
    return await query.lean<IGroup>();
  }

  /**
   * Find multiple groups by their external IDs (e.g., Entra IDs) in a single query
   * @param idsOnTheSource - Array of external IDs
   * @param source - The source ('entra' or 'local')
   * @param session - Optional MongoDB session for transactions
   * @returns Array of group documents
   */
  async function findGroupsByExternalIds(
    idsOnTheSource: string[],
    source: 'entra' | 'local' = 'entra',
    session?: ClientSession,
  ): Promise<IGroup[]> {
    const Group = mongoose.models.Group as Model<IGroup>;
    const query = Group.find(
      { idOnTheSource: { $in: idsOnTheSource }, source },
      { idOnTheSource: 1, _id: 0 },
    );
    if (session) {
      query.session(session);
    }
    return await query.lean<IGroup[]>();
  }

  /**
   * Find groups by name pattern (case-insensitive partial match)
   * @param namePattern - The name pattern to search for
   * @param source - Optional source filter ('entra', 'local', or null for all)
   * @param limit - Maximum number of results to return
   * @param session - Optional MongoDB session for transactions
   * @returns Array of matching groups
   */
  async function findGroupsByNamePattern(
    namePattern: string,
    source: 'entra' | 'local' | null = null,
    limit: number = 20,
    session?: ClientSession,
  ): Promise<IGroup[]> {
    const Group = mongoose.models.Group as Model<IGroup>;
    const regex = new RegExp(namePattern, 'i');
    const query: Record<string, unknown> = {
      $or: [{ name: regex }, { email: regex }, { description: regex }],
    };

    if (source) {
      query.source = source;
    }

    const dbQuery = Group.find(query).limit(limit);
    if (session) {
      dbQuery.session(session);
    }
    return await dbQuery.lean<IGroup[]>();
  }

  /**
   * Find all groups a user is a member of by their ID or idOnTheSource
   * @param userId - The user ID
   * @param session - Optional MongoDB session for transactions
   * @returns Array of groups the user is a member of
   */
  async function findGroupsByMemberId(
    userId: string | Types.ObjectId,
    session?: ClientSession,
  ): Promise<IGroup[]> {
    const User = mongoose.models.User as Model<IUser>;
    const Group = mongoose.models.Group as Model<IGroup>;

    const userQuery = User.findById(userId, 'idOnTheSource');
    if (session) {
      userQuery.session(session);
    }
    const user = await userQuery.lean<{ idOnTheSource?: string }>();

    if (!user) {
      return [];
    }

    const userIdOnTheSource = user.idOnTheSource || userId.toString();

    const query = Group.find({ memberIds: userIdOnTheSource });
    if (session) {
      query.session(session);
    }
    return await query.lean<IGroup[]>();
  }

  /**
   * Create a new group
   * @param groupData - Group data including name, source, and optional idOnTheSource
   * @param session - Optional MongoDB session for transactions
   * @returns The created group
   */
  async function createGroup(groupData: Partial<IGroup>, session?: ClientSession): Promise<IGroup> {
    const Group = mongoose.models.Group as Model<IGroup>;
    const options = session ? { session } : {};
    return await Group.create([groupData], options).then((groups) => groups[0]);
  }

  /**
   * Update or create a group by external ID
   * @param idOnTheSource - The external ID
   * @param source - The source ('entra' or 'local')
   * @param updateData - Data to update or set if creating
   * @param session - Optional MongoDB session for transactions
   * @returns The updated or created group
   */
  async function upsertGroupByExternalId(
    idOnTheSource: string,
    source: 'entra' | 'local',
    updateData: Partial<IGroup>,
    session?: ClientSession,
  ): Promise<IGroup | null> {
    const Group = mongoose.models.Group as Model<IGroup>;
    const options = {
      new: true,
      upsert: true,
      ...(session ? { session } : {}),
    };

    return await Group.findOneAndUpdate({ idOnTheSource, source }, { $set: updateData }, options);
  }

  /**
   * Add a user to a group
   * Only updates Group.memberIds (one-way relationship)
   * Note: memberIds stores idOnTheSource values, not ObjectIds
   *
   * @param userId - The user ID
   * @param groupId - The group ID to add
   * @param session - Optional MongoDB session for transactions
   * @returns The user and updated group documents
   */
  async function addUserToGroup(
    userId: string | Types.ObjectId,
    groupId: string | Types.ObjectId,
    session?: ClientSession,
  ): Promise<{ user: IUser; group: IGroup | null }> {
    const User = mongoose.models.User as Model<IUser>;
    const Group = mongoose.models.Group as Model<IGroup>;

    const options = { new: true, ...(session ? { session } : {}) };

    const user = await User.findById(userId, 'idOnTheSource', options).lean<{
      idOnTheSource?: string;
      _id: Types.ObjectId;
    }>();
    if (!user) {
      throw new Error(`User not found: ${userId}`);
    }

    const userIdOnTheSource = user.idOnTheSource || userId.toString();
    const updatedGroup = await Group.findByIdAndUpdate(
      groupId,
      { $addToSet: { memberIds: userIdOnTheSource } },
      options,
    ).lean<IGroup>();

    return { user: user as IUser, group: updatedGroup };
  }

  /**
   * Remove a user from a group
   * Only updates Group.memberIds (one-way relationship)
   * Note: memberIds stores idOnTheSource values, not ObjectIds
   *
   * @param userId - The user ID
   * @param groupId - The group ID to remove
   * @param session - Optional MongoDB session for transactions
   * @returns The user and updated group documents
   */
  async function removeUserFromGroup(
    userId: string | Types.ObjectId,
    groupId: string | Types.ObjectId,
    session?: ClientSession,
  ): Promise<{ user: IUser; group: IGroup | null }> {
    const User = mongoose.models.User as Model<IUser>;
    const Group = mongoose.models.Group as Model<IGroup>;

    const options = { new: true, ...(session ? { session } : {}) };

    const user = await User.findById(userId, 'idOnTheSource', options).lean<{
      idOnTheSource?: string;
      _id: Types.ObjectId;
    }>();
    if (!user) {
      throw new Error(`User not found: ${userId}`);
    }

    const userIdOnTheSource = user.idOnTheSource || userId.toString();
    const updatedGroup = await Group.findByIdAndUpdate(
      groupId,
      { $pullAll: { memberIds: [userIdOnTheSource] } },
      options,
    ).lean<IGroup>();

    return { user: user as IUser, group: updatedGroup };
  }

  /**
   * Get all groups a user is a member of
   * @param userId - The user ID
   * @param session - Optional MongoDB session for transactions
   * @returns Array of group documents
   */
  async function getUserGroups(
    userId: string | Types.ObjectId,
    session?: ClientSession,
  ): Promise<IGroup[]> {
    return await findGroupsByMemberId(userId, session);
  }

  /**
   * Get a list of all principal identifiers for a user (user ID + group IDs + public).
   * For use in permission checks.
   *
   * Tenant filtering for group memberships is handled automatically by the
   * `applyTenantIsolation` Mongoose plugin on the Group schema. The
   * `tenantContextMiddleware` (chained by `requireJwtAuth` after passport auth)
   * sets the ALS context, so `getUserGroups()` → `findGroupsByMemberId()` queries
   * are scoped to the requesting tenant. No explicit tenantId parameter is needed.
   *
   * IMPORTANT: This relies on the ALS tenant context being active. If this
   * function is called outside a request context (e.g. startup, background jobs),
   * group queries will be unscoped. In strict mode, the Mongoose plugin will
   * reject such queries.
   *
   * Ref: #12091 (resolved by tenant context middleware in requireJwtAuth)
   *
   * @param params - Parameters object
   * @param params.userId - The user ID
   * @param params.role - Optional user role (if not provided, will query from DB)
   * @param session - Optional MongoDB session for transactions
   * @returns Array of principal objects with type and id
   */
  async function getUserPrincipals(
    params: {
      userId: string | Types.ObjectId;
      role?: string | null;
    },
    session?: ClientSession,
  ): Promise<Array<{ principalType: PrincipalType; principalId?: string | Types.ObjectId }>> {
    const { userId, role } = params;
    /** `userId` must be an `ObjectId` for USER principal since ACL entries store `ObjectId`s */
    const userObjectId = typeof userId === 'string' ? new Types.ObjectId(userId) : userId;
    const principals: Array<{
      principalType: PrincipalType;
      principalId?: string | Types.ObjectId;
    }> = [{ principalType: PrincipalType.USER, principalId: userObjectId }];

    // If role is not provided, query user to get it
    let userRole = role;
    if (userRole === undefined) {
      const User = mongoose.models.User as Model<IUser>;
      const query = User.findById(userId).select('role');
      if (session) {
        query.session(session);
      }
      const user = await query.lean<IUser>();
      userRole = user?.role;
    }

    // Add role as a principal if user has one
    if (userRole && userRole.trim()) {
      principals.push({ principalType: PrincipalType.ROLE, principalId: userRole });
    }

    const userGroups = await getUserGroups(userId, session);
    if (userGroups && userGroups.length > 0) {
      userGroups.forEach((group) => {
        principals.push({ principalType: PrincipalType.GROUP, principalId: group._id });
      });
    }

    principals.push({ principalType: PrincipalType.PUBLIC });

    return principals;
  }

  /**
   * Sync a user's Entra ID group memberships
   * @param userId - The user ID
   * @param entraGroups - Array of Entra groups with id and name
   * @param session - Optional MongoDB session for transactions
   * @returns The updated user with new group memberships
   */
  async function syncUserEntraGroups(
    userId: string | Types.ObjectId,
    entraGroups: Array<{ id: string; name: string; description?: string; email?: string }>,
    session?: ClientSession,
  ): Promise<{
    user: IUser;
    addedGroups: IGroup[];
    removedGroups: IGroup[];
  }> {
    const User = mongoose.models.User as Model<IUser>;
    const Group = mongoose.models.Group as Model<IGroup>;

    const query = User.findById(userId, { idOnTheSource: 1 });
    if (session) {
      query.session(session);
    }
    const user = await query.lean<{ idOnTheSource?: string; _id: Types.ObjectId }>();

    if (!user) {
      throw new Error(`User not found: ${userId}`);
    }

    /** Get user's idOnTheSource for storing in group.memberIds */
    const userIdOnTheSource = user.idOnTheSource || userId.toString();

    const entraIdMap = new Map<string, boolean>();
    const addedGroups: IGroup[] = [];
    const removedGroups: IGroup[] = [];

    for (const entraGroup of entraGroups) {
      entraIdMap.set(entraGroup.id, true);

      let group = await findGroupByExternalId(entraGroup.id, 'entra', {}, session);

      if (!group) {
        group = await createGroup(
          {
            name: entraGroup.name,
            description: entraGroup.description,
            email: entraGroup.email,
            idOnTheSource: entraGroup.id,
            source: 'entra',
            memberIds: [userIdOnTheSource],
          },
          session,
        );

        addedGroups.push(group);
      } else if (!group.memberIds?.includes(userIdOnTheSource)) {
        const { group: updatedGroup } = await addUserToGroup(userId, group._id, session);
        if (updatedGroup) {
          addedGroups.push(updatedGroup);
        }
      }
    }

    const groupsQuery = Group.find(
      { source: 'entra', memberIds: userIdOnTheSource },
      { _id: 1, idOnTheSource: 1 },
    );
    if (session) {
      groupsQuery.session(session);
    }
    const existingGroups = await groupsQuery.lean<
      Array<{
        _id: Types.ObjectId;
        idOnTheSource?: string;
      }>
    >();

    for (const group of existingGroups) {
      if (group.idOnTheSource && !entraIdMap.has(group.idOnTheSource)) {
        const { group: removedGroup } = await removeUserFromGroup(userId, group._id, session);
        if (removedGroup) {
          removedGroups.push(removedGroup);
        }
      }
    }

    const userQuery = User.findById(userId);
    if (session) {
      userQuery.session(session);
    }
    const updatedUser = await userQuery.lean<IUser>();

    if (!updatedUser) {
      throw new Error(`User not found after update: ${userId}`);
    }

    return {
      user: updatedUser,
      addedGroups,
      removedGroups,
    };
  }

  /**
   * Calculate relevance score for a search result
   * @param item - The search result item
   * @param searchPattern - The search pattern
   * @returns Relevance score (0-100)
   */
  function calculateRelevanceScore(item: TPrincipalSearchResult, searchPattern: string): number {
    const exactRegex = new RegExp(`^${searchPattern}$`, 'i');
    const startsWithPattern = searchPattern.toLowerCase();

    /** Get searchable text based on type */
    const searchableFields =
      item.type === PrincipalType.USER
        ? [item.name, item.email, item.username].filter(Boolean)
        : [item.name, item.email, item.description].filter(Boolean);

    let maxScore = 0;

    for (const field of searchableFields) {
      if (!field) continue;
      const fieldLower = field.toLowerCase();
      let score = 0;

      /** Exact match gets highest score */
      if (exactRegex.test(field)) {
        score = 100;
      } else if (fieldLower.startsWith(startsWithPattern)) {
        /** Starts with query gets high score */
        score = 80;
      } else if (fieldLower.includes(startsWithPattern)) {
        /** Contains query gets medium score */
        score = 50;
      } else {
        /** Default score for regex match */
        score = 10;
      }

      maxScore = Math.max(maxScore, score);
    }

    return maxScore;
  }

  /**
   * Sort principals by relevance score and type priority
   * @param results - Array of results with _searchScore property
   * @returns Sorted array
   */
  function sortPrincipalsByRelevance<
    T extends { _searchScore?: number; type: string; name?: string; email?: string },
  >(results: T[]): T[] {
    return results.sort((a, b) => {
      if (b._searchScore !== a._searchScore) {
        return (b._searchScore || 0) - (a._searchScore || 0);
      }
      if (a.type !== b.type) {
        return a.type === PrincipalType.USER ? -1 : 1;
      }
      const aName = a.name || a.email || '';
      const bName = b.name || b.email || '';
      return aName.localeCompare(bName);
    });
  }

  /**
   * Transform user object to TPrincipalSearchResult format
   * @param user - User object from database
   * @returns Transformed user result
   */
  function transformUserToTPrincipalSearchResult(user: TUser): TPrincipalSearchResult {
    return {
      id: user.id,
      type: PrincipalType.USER,
      name: user.name || user.email,
      email: user.email,
      username: user.username,
      avatar: user.avatar,
      provider: user.provider,
      source: 'local',
      idOnTheSource: (user as TUser & { idOnTheSource?: string }).idOnTheSource || user.id,
    };
  }

  /**
   * Transform group object to TPrincipalSearchResult format
   * @param group - Group object from database
   * @returns Transformed group result
   */
  function transformGroupToTPrincipalSearchResult(group: IGroup): TPrincipalSearchResult {
    return {
      id: group._id?.toString(),
      type: PrincipalType.GROUP,
      name: group.name,
      email: group.email,
      avatar: group.avatar,
      description: group.description,
      source: group.source || 'local',
      memberCount: group.memberIds ? group.memberIds.length : 0,
      idOnTheSource: group.idOnTheSource || group._id?.toString(),
    };
  }

  /**
   * Search for principals (users and groups) by pattern matching on name/email
   * Returns combined results in TPrincipalSearchResult format without sorting
   * @param searchPattern - The pattern to search for
   * @param limitPerType - Maximum number of results to return
   * @param typeFilter - Optional array of types to filter by, or null for all types
   * @param session - Optional MongoDB session for transactions
   * @returns Array of principals in TPrincipalSearchResult format
   */
  async function searchPrincipals(
    searchPattern: string,
    limitPerType: number = 10,
    typeFilter: Array<PrincipalType.USER | PrincipalType.GROUP | PrincipalType.ROLE> | null = null,
    session?: ClientSession,
  ): Promise<TPrincipalSearchResult[]> {
    if (!searchPattern || searchPattern.trim().length === 0) {
      return [];
    }

    const trimmedPattern = searchPattern.trim();
    const promises: Promise<TPrincipalSearchResult[]>[] = [];

    if (!typeFilter || typeFilter.includes(PrincipalType.USER)) {
      /** Note: searchUsers is imported from ~/models and needs to be passed in or implemented */
      const userFields = 'name email username avatar provider idOnTheSource';
      /** For now, we'll use a direct query instead of searchUsers */
      const User = mongoose.models.User as Model<IUser>;
      const regex = new RegExp(trimmedPattern, 'i');
      const userQuery = User.find({
        $or: [{ name: regex }, { email: regex }, { username: regex }],
      })
        .select(userFields)
        .limit(limitPerType);

      if (session) {
        userQuery.session(session);
      }

      promises.push(
        userQuery.lean<IUser[]>().then((users) =>
          users.map((user) => {
            const userWithId = user as IUser & { idOnTheSource?: string };
            return transformUserToTPrincipalSearchResult({
              id: userWithId._id?.toString() || '',
              name: userWithId.name,
              email: userWithId.email,
              username: userWithId.username,
              avatar: userWithId.avatar,
              provider: userWithId.provider,
            } as TUser);
          }),
        ),
      );
    } else {
      promises.push(Promise.resolve([]));
    }

    if (!typeFilter || typeFilter.includes(PrincipalType.GROUP)) {
      promises.push(
        findGroupsByNamePattern(trimmedPattern, null, limitPerType, session).then((groups) =>
          groups.map(transformGroupToTPrincipalSearchResult),
        ),
      );
    } else {
      promises.push(Promise.resolve([]));
    }

    if (!typeFilter || typeFilter.includes(PrincipalType.ROLE)) {
      const Role = mongoose.models.Role as Model<IRole>;
      if (Role) {
        const regex = new RegExp(trimmedPattern, 'i');
        const roleQuery = Role.find({ name: regex }).select('name').limit(limitPerType);

        if (session) {
          roleQuery.session(session);
        }

        promises.push(
          roleQuery.lean<Array<{ name: string }>>().then((roles) =>
            roles.map((role) => ({
              /** Role name as ID */
              id: role.name,
              type: PrincipalType.ROLE,
              name: role.name,
              source: 'local' as const,
              idOnTheSource: role.name,
            })),
          ),
        );
      }
    } else {
      promises.push(Promise.resolve([]));
    }

    const results = await Promise.all(promises);
    const combined = results.flat();
    return combined;
  }

  /**
   * Removes a user from all groups they belong to.
   * @param userId - The user ID (or ObjectId) of the member to remove
   */
  async function removeUserFromAllGroups(userId: string | Types.ObjectId): Promise<void> {
    const Group = mongoose.models.Group as Model<IGroup>;
    await Group.updateMany({ memberIds: userId }, { $pullAll: { memberIds: [userId] } });
  }

  /**
   * Finds a single group matching the given filter.
   * @param filter - MongoDB filter query
   */
  async function findGroupByQuery(
    filter: Record<string, unknown>,
    session?: ClientSession,
  ): Promise<IGroup | null> {
    const Group = mongoose.models.Group as Model<IGroup>;
    const query = Group.findOne(filter);
    if (session) {
      query.session(session);
    }
    return query.lean<IGroup>();
  }

  /**
   * Updates a group by its ID.
   * @param groupId - The group's ObjectId
   * @param data - Fields to set via $set
   */
  async function updateGroupById(
    groupId: string | Types.ObjectId,
    data: Record<string, unknown>,
    session?: ClientSession,
  ): Promise<IGroup | null> {
    const Group = mongoose.models.Group as Model<IGroup>;
    const options = { new: true, ...(session ? { session } : {}) };
    return Group.findByIdAndUpdate(groupId, { $set: data }, options).lean<IGroup>();
  }

  /**
   * Bulk-updates groups matching a filter.
   * @param filter - MongoDB filter query
   * @param update - Update operations
   * @param options - Optional query options (e.g., { session })
   */
  async function bulkUpdateGroups(
    filter: Record<string, unknown>,
    update: Record<string, unknown>,
    options?: { session?: ClientSession },
  ) {
    const Group = mongoose.models.Group as Model<IGroup>;
    return Group.updateMany(filter, update, options || {});
  }

  function buildGroupQuery(filter: {
    source?: 'local' | 'entra';
    search?: string;
  }): FilterQuery<IGroup> {
    const query: FilterQuery<IGroup> = {};
    if (filter.source) {
      query.source = filter.source;
    }
    if (filter.search) {
      const regex = new RegExp(escapeRegExp(filter.search), 'i');
      query.$or = [{ name: regex }, { email: regex }, { description: regex }];
    }
    return query;
  }

  /**
   * List groups with optional source, search, and pagination filters.
   * Results are sorted by name.
   * @param filter - Optional filter with source, search, limit, and offset fields
   * @param session - Optional MongoDB session for transactions
   */
  async function listGroups(
    filter: {
      source?: 'local' | 'entra';
      search?: string;
      limit?: number;
      offset?: number;
    } = {},
    session?: ClientSession,
  ): Promise<IGroup[]> {
    const Group = mongoose.models.Group as Model<IGroup>;
    const query = buildGroupQuery(filter);
    const limit = filter.limit ?? 50;
    const offset = filter.offset ?? 0;
    return await Group.find(query)
      .sort({ name: 1 })
      .skip(offset)
      .limit(limit)
      .session(session ?? null)
      .lean<IGroup[]>();
  }

  /**
   * Count groups matching optional source and search filters.
   * @param filter - Optional filter with source and search fields
   * @param session - Optional MongoDB session for transactions
   */
  async function countGroups(
    filter: { source?: 'local' | 'entra'; search?: string } = {},
    session?: ClientSession,
  ): Promise<number> {
    const Group = mongoose.models.Group as Model<IGroup>;
    const query = buildGroupQuery(filter);
    return await Group.countDocuments(query).session(session ?? null);
  }

  /**
   * Delete a group by its ID.
   * @param groupId - The group's ObjectId
   * @param session - Optional MongoDB session for transactions
   */
  async function deleteGroup(
    groupId: string | Types.ObjectId,
    session?: ClientSession,
  ): Promise<IGroup | null> {
    const Group = mongoose.models.Group as Model<IGroup>;
    const options = session ? { session } : {};
    return await Group.findByIdAndDelete(groupId, options).lean<IGroup>();
  }

  /**
   * Remove a member from a group by raw memberId string ($pull from memberIds).
   * Unlike removeUserFromGroup, this does not look up the user first.
   * @param groupId - The group's ObjectId
   * @param memberId - The raw memberId string to remove (ObjectId or idOnTheSource)
   * @param session - Optional MongoDB session for transactions
   */
  async function removeMemberById(
    groupId: string | Types.ObjectId,
    memberId: string,
    session?: ClientSession,
  ): Promise<IGroup | null> {
    const Group = mongoose.models.Group as Model<IGroup>;
    const options = { new: true, ...(session ? { session } : {}) };
    return await Group.findByIdAndUpdate(
      groupId,
      { $pull: { memberIds: memberId } },
      options,
    ).lean<IGroup>();
  }

  /**
   * Resolve the value stored in Group.memberIds for a user: the user's
   * idOnTheSource if present, else the userId string. Mirrors addUserToGroup
   * so ACL membership resolution stays consistent.
   */
  async function resolveMemberIdValue(
    userId: string | Types.ObjectId,
    session?: ClientSession,
  ): Promise<string> {
    const User = mongoose.models.User as Model<IUser>;
    const query = User.findById(userId, 'idOnTheSource');
    if (session) {
      query.session(session);
    }
    const user = await query.lean<{ idOnTheSource?: string }>();
    return user?.idOnTheSource || userId.toString();
  }

  /**
   * Create a self-service team. The creator becomes the sole owner and the
   * first member; memberIds is seeded so ACL checks work immediately.
   */
  async function createTeam(
    params: {
      name: string;
      description?: string;
      avatar?: string;
      ownerId: string | Types.ObjectId;
      tenantId?: string;
    },
    session?: ClientSession,
  ): Promise<IGroup> {
    const ownerObjectId =
      typeof params.ownerId === 'string' ? new Types.ObjectId(params.ownerId) : params.ownerId;
    const memberIdValue = await resolveMemberIdValue(ownerObjectId, session);
    const Group = mongoose.models.Group as Model<IGroup>;
    const doc: Partial<IGroup> = {
      name: params.name,
      description: params.description,
      avatar: params.avatar,
      source: 'local',
      kind: 'team',
      ownerId: ownerObjectId,
      members: [{ userId: ownerObjectId, role: 'owner', joinedAt: new Date() }],
      memberIds: [memberIdValue],
      joinPolicy: 'invite',
      tenantId: params.tenantId,
    };
    const options = session ? { session } : {};
    return await Group.create([doc], options).then((groups) => groups[0]);
  }

  /**
   * Add a member to a team, updating members and memberIds atomically.
   * Rejects 'owner' (ownership moves only via transferOwnership). No-op if the
   * user is already a member (returns null).
   */
  async function addTeamMember(
    params: {
      groupId: string | Types.ObjectId;
      userId: string | Types.ObjectId;
      role?: 'admin' | 'member';
    },
    session?: ClientSession,
  ): Promise<IGroup | null> {
    const role: TeamRole = params.role ?? 'member';
    if (role !== 'admin' && role !== 'member') {
      throw new Error(`Invalid team member role: ${role}`);
    }
    const userObjectId =
      typeof params.userId === 'string' ? new Types.ObjectId(params.userId) : params.userId;
    const memberIdValue = await resolveMemberIdValue(userObjectId, session);
    const Group = mongoose.models.Group as Model<IGroup>;
    const options = { new: true, ...(session ? { session } : {}) };
    return await Group.findOneAndUpdate(
      { _id: params.groupId, 'members.userId': { $ne: userObjectId } },
      {
        $push: { members: { userId: userObjectId, role, joinedAt: new Date() } },
        $addToSet: { memberIds: memberIdValue },
      },
      options,
    ).lean<IGroup>();
  }

  /**
   * Remove a member from a team, pulling from members and memberIds atomically.
   * Refuses to remove the current owner (transfer ownership first).
   */
  async function removeTeamMember(
    params: { groupId: string | Types.ObjectId; userId: string | Types.ObjectId },
    session?: ClientSession,
  ): Promise<IGroup | null> {
    const userObjectId =
      typeof params.userId === 'string' ? new Types.ObjectId(params.userId) : params.userId;
    const group = await findGroupById(params.groupId, {}, session);
    if (!group) {
      return null;
    }
    if (group.ownerId && group.ownerId.toString() === userObjectId.toString()) {
      throw new Error('Cannot remove the team owner; transfer ownership first');
    }
    const memberIdValue = await resolveMemberIdValue(userObjectId, session);
    const Group = mongoose.models.Group as Model<IGroup>;
    const options = { new: true, ...(session ? { session } : {}) };
    return await Group.findByIdAndUpdate(
      params.groupId,
      { $pull: { members: { userId: userObjectId }, memberIds: memberIdValue } },
      options,
    ).lean<IGroup>();
  }

  /** Get a user's role within a team, or null if not a member. */
  async function getTeamRole(
    params: { groupId: string | Types.ObjectId; userId: string | Types.ObjectId },
    session?: ClientSession,
  ): Promise<TeamRole | null> {
    const userObjectId =
      typeof params.userId === 'string' ? new Types.ObjectId(params.userId) : params.userId;
    const group = await findGroupById(params.groupId, { members: 1 }, session);
    if (!group || !group.members) {
      return null;
    }
    const member = group.members.find((m) => m.userId.toString() === userObjectId.toString());
    return member ? member.role : null;
  }

  /**
   * Change a member's role between 'admin' and 'member'. Refuses to touch the
   * owner (use transferOwnership) and rejects 'owner' as a target role.
   */
  async function setMemberRole(
    params: {
      groupId: string | Types.ObjectId;
      userId: string | Types.ObjectId;
      role: 'admin' | 'member';
    },
    session?: ClientSession,
  ): Promise<IGroup | null> {
    if (params.role !== 'admin' && params.role !== 'member') {
      throw new Error(`Invalid role for setMemberRole: ${params.role}`);
    }
    const userObjectId =
      typeof params.userId === 'string' ? new Types.ObjectId(params.userId) : params.userId;
    const group = await findGroupById(params.groupId, {}, session);
    if (!group) {
      return null;
    }
    if (group.ownerId && group.ownerId.toString() === userObjectId.toString()) {
      throw new Error('Cannot change the owner role; use transferOwnership');
    }
    const Group = mongoose.models.Group as Model<IGroup>;
    const options = {
      new: true,
      arrayFilters: [{ 'elem.userId': userObjectId }],
      ...(session ? { session } : {}),
    };
    return await Group.findByIdAndUpdate(
      params.groupId,
      { $set: { 'members.$[elem].role': params.role } },
      options,
    ).lean<IGroup>();
  }

  /**
   * Transfer team ownership: the current owner is demoted to 'admin' and the
   * target is promoted to 'owner', with ownerId updated — one atomic update.
   */
  async function transferOwnership(
    params: {
      groupId: string | Types.ObjectId;
      fromUserId: string | Types.ObjectId;
      toUserId: string | Types.ObjectId;
    },
    session?: ClientSession,
  ): Promise<IGroup | null> {
    const fromObjectId =
      typeof params.fromUserId === 'string'
        ? new Types.ObjectId(params.fromUserId)
        : params.fromUserId;
    const toObjectId =
      typeof params.toUserId === 'string' ? new Types.ObjectId(params.toUserId) : params.toUserId;
    const group = await findGroupById(params.groupId, {}, session);
    if (!group) {
      return null;
    }
    if (!group.ownerId || group.ownerId.toString() !== fromObjectId.toString()) {
      throw new Error('fromUserId is not the current owner');
    }
    if (fromObjectId.toString() === toObjectId.toString()) {
      return group;
    }
    const isMember = (group.members ?? []).some(
      (m) => m.userId.toString() === toObjectId.toString(),
    );
    if (!isMember) {
      throw new Error('toUserId is not a member of the team');
    }
    const Group = mongoose.models.Group as Model<IGroup>;
    const options = {
      new: true,
      arrayFilters: [{ 'old.userId': fromObjectId }, { 'new.userId': toObjectId }],
      ...(session ? { session } : {}),
    };
    return await Group.findByIdAndUpdate(
      params.groupId,
      {
        $set: {
          ownerId: toObjectId,
          'members.$[old].role': 'admin',
          'members.$[new].role': 'owner',
        },
      },
      options,
    ).lean<IGroup>();
  }

  /** Get all team-kind groups a user is a member of. */
  async function getUserTeams(
    params: { userId: string | Types.ObjectId },
    session?: ClientSession,
  ): Promise<IGroup[]> {
    const userObjectId =
      typeof params.userId === 'string' ? new Types.ObjectId(params.userId) : params.userId;
    const Group = mongoose.models.Group as Model<IGroup>;
    const query = Group.find({ kind: 'team', 'members.userId': userObjectId });
    if (session) {
      query.session(session);
    }
    return await query.lean<IGroup[]>();
  }

  /** Create a sub-group scoped to a parent team. */
  async function createSubgroup(params: {
    parentTeamId: string | Types.ObjectId;
    name: string;
    description?: string;
    ownerId: string | Types.ObjectId;
    tenantId?: string;
    session?: ClientSession;
  }): Promise<IGroup> {
    const { parentTeamId, name, description, ownerId, tenantId, session } = params;
    const ownerObjectId =
      typeof ownerId === 'string' ? new Types.ObjectId(ownerId) : ownerId;
    const parentTeamObjectId =
      typeof parentTeamId === 'string' ? new Types.ObjectId(parentTeamId) : parentTeamId;
    return createGroup(
      {
        name,
        description,
        kind: 'team_subgroup',
        parentTeamId: parentTeamObjectId,
        ownerId: ownerObjectId,
        source: 'local',
        memberIds: [],
        members: [],
        tenantId,
      },
      session,
    );
  }

  /** List all sub-groups belonging to a team. */
  async function getTeamSubgroups(
    parentTeamId: string | Types.ObjectId,
  ): Promise<IGroup[]> {
    const Group = mongoose.models.Group as Model<IGroup>;
    return Group.find({ parentTeamId, kind: 'team_subgroup' }).lean<IGroup[]>();
  }

  /** Find a sub-group by its ID. */
  async function getSubgroupById(
    subgroupId: string | Types.ObjectId,
  ): Promise<IGroup | null> {
    const Group = mongoose.models.Group as Model<IGroup>;
    return Group.findById(subgroupId).lean<IGroup>();
  }

  /** Patch a sub-group's name and/or description. */
  async function updateSubgroup(
    subgroupId: string | Types.ObjectId,
    updates: { name?: string; description?: string },
  ): Promise<IGroup | null> {
    const Group = mongoose.models.Group as Model<IGroup>;
    return Group.findByIdAndUpdate(
      subgroupId,
      { $set: updates },
      { new: true },
    ).lean<IGroup>();
  }

  /** Delete a sub-group document. */
  async function deleteSubgroup(
    subgroupId: string | Types.ObjectId,
    session?: ClientSession,
  ): Promise<void> {
    const Group = mongoose.models.Group as Model<IGroup>;
    const options = session ? { session } : {};
    await Group.deleteOne({ _id: subgroupId }, options);
  }

  /**
   * Add a user to a sub-group.
   * Enforces the team-subset invariant: the user must already be in the parent
   * team's memberIds. Dual-writes memberIds (string ACL) + members (role list).
   */
  async function addSubgroupMember(params: {
    subgroupId: string | Types.ObjectId;
    userId: string;
    session?: ClientSession;
  }): Promise<IGroup> {
    const { subgroupId, userId, session } = params;
    const Group = mongoose.models.Group as Model<IGroup>;
    const sg = await Group.findById(subgroupId);
    if (!sg) {
      throw new Error('Sub-group not found');
    }
    const team = await Group.findById(sg.parentTeamId).lean<IGroup>();
    if (!team || !(team.memberIds ?? []).includes(userId)) {
      throw new Error('User is not a member of the team');
    }
    if (!sg.memberIds?.includes(userId)) {
      const userObjectId = new Types.ObjectId(userId);
      sg.memberIds = [...(sg.memberIds ?? []), userId];
      sg.members = [
        ...(sg.members ?? []),
        { userId: userObjectId, role: 'member', joinedAt: new Date() },
      ];
      await sg.save({ session });
    }
    return sg.toObject() as IGroup;
  }

  /**
   * Remove a user from a sub-group, pulling from both memberIds and members.
   */
  async function removeSubgroupMember(params: {
    subgroupId: string | Types.ObjectId;
    userId: string;
    session?: ClientSession;
  }): Promise<IGroup> {
    const { subgroupId, userId, session } = params;
    const Group = mongoose.models.Group as Model<IGroup>;
    const userObjectId = new Types.ObjectId(userId);
    const options = { new: true, ...(session ? { session } : {}) };
    const updated = await Group.findByIdAndUpdate(
      subgroupId,
      { $pull: { memberIds: userId, members: { userId: userObjectId } } },
      options,
    ).lean<IGroup>();
    if (!updated) {
      throw new Error('Sub-group not found');
    }
    return updated;
  }

  /**
   * Return sub-groups (of a given parent team) that the user belongs to.
   * Queries by parentTeamId + kind + memberIds so only the user's own memberships
   * are returned, excluding sub-groups they are not in.
   */
  async function getUserSubgroups(params: {
    userId: string;
    parentTeamId: string | Types.ObjectId;
  }): Promise<IGroup[]> {
    const Group = mongoose.models.Group as Model<IGroup>;
    return Group.find({
      parentTeamId: params.parentTeamId,
      kind: 'team_subgroup',
      memberIds: params.userId,
    }).lean<IGroup[]>();
  }

  return {
    findGroupById,
    findGroupByExternalId,
    findGroupsByExternalIds,
    findGroupsByNamePattern,
    findGroupsByMemberId,
    createGroup,
    upsertGroupByExternalId,
    addUserToGroup,
    removeUserFromGroup,
    removeUserFromAllGroups,
    findGroupByQuery,
    updateGroupById,
    bulkUpdateGroups,
    getUserGroups,
    getUserPrincipals,
    syncUserEntraGroups,
    searchPrincipals,
    calculateRelevanceScore,
    sortPrincipalsByRelevance,
    listGroups,
    countGroups,
    deleteGroup,
    removeMemberById,
    createTeam,
    addTeamMember,
    removeTeamMember,
    getUserTeams,
    getTeamRole,
    setMemberRole,
    transferOwnership,
    createSubgroup,
    getTeamSubgroups,
    getSubgroupById,
    updateSubgroup,
    deleteSubgroup,
    addSubgroupMember,
    removeSubgroupMember,
    getUserSubgroups,
  };
}

export type UserGroupMethods = ReturnType<typeof createUserGroupMethods>;
