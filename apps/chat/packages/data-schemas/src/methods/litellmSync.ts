import type { Model, ClientSession } from 'mongoose';
import type { ILiteLLMSync, LiteLLMSync } from '~/types';

/**
 * Methods for the LiteLLMSync collection — the endpoint ↔ LiteLLM mapping that
 * lets the runtime rewrite know each managed endpoint's virtual key and models.
 *
 * Tenant scoping is handled by the tenantIsolation plugin (see models/litellmSync.ts);
 * callers run inside a tenant context, so methods query by `endpointName` only.
 */
export function createLiteLLMSyncMethods(mongoose: typeof import('mongoose')) {
  function model(): Model<ILiteLLMSync> {
    return mongoose.models.LiteLLMSync as Model<ILiteLLMSync>;
  }

  async function findLiteLLMSyncByEndpointName(
    endpointName: string,
    session?: ClientSession,
  ): Promise<ILiteLLMSync | null> {
    return await model()
      .findOne({ endpointName })
      .session(session ?? null)
      .lean<ILiteLLMSync>();
  }

  async function findLiteLLMSyncByEndpointNames(names: string[]): Promise<ILiteLLMSync[]> {
    if (!names || names.length === 0) {
      return [];
    }
    return await model()
      .find({ endpointName: { $in: names } })
      .lean<ILiteLLMSync[]>();
  }

  async function listLiteLLMSync(): Promise<ILiteLLMSync[]> {
    return await model().find({}).lean<ILiteLLMSync[]>();
  }

  async function upsertLiteLLMSync(
    endpointName: string,
    patch: Partial<LiteLLMSync>,
    session?: ClientSession,
  ): Promise<ILiteLLMSync | null> {
    const query = { endpointName };
    const update = { $set: { ...patch, endpointName } };
    const options = {
      upsert: true,
      new: true,
      setDefaultsOnInsert: true,
      ...(session ? { session } : {}),
    };
    try {
      return await model().findOneAndUpdate(query, update, options);
    } catch (err: unknown) {
      if ((err as { code?: number }).code === 11000) {
        return await model().findOneAndUpdate(query, update, {
          new: true,
          ...(session ? { session } : {}),
        });
      }
      throw err;
    }
  }

  async function deleteLiteLLMSyncByEndpointName(
    endpointName: string,
    session?: ClientSession,
  ): Promise<ILiteLLMSync | null> {
    return await model()
      .findOneAndDelete({ endpointName })
      .session(session ?? null);
  }

  return {
    findLiteLLMSyncByEndpointName,
    findLiteLLMSyncByEndpointNames,
    listLiteLLMSync,
    upsertLiteLLMSync,
    deleteLiteLLMSyncByEndpointName,
  };
}

export type LiteLLMSyncMethods = ReturnType<typeof createLiteLLMSyncMethods>;
