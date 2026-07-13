import type { Document, Types } from 'mongoose';

export type LiteLLMSyncModel = {
  /** Raw model id the admin configured on the endpoint, e.g. "gpt-4o". */
  sourceModel: string;
  /** Public alias registered in LiteLLM, namespaced as "<endpoint>/<model>". */
  litellmModelName: string;
  /** The model_id LiteLLM returned from /model/new (for update/delete). */
  litellmModelId: string;
};

export type LiteLLMSyncStatus = 'pending' | 'active' | 'failed';

export type LiteLLMSync = {
  /** The custom endpoint `name` — the join key back to endpoints.custom. */
  endpointName: string;
  status: LiteLLMSyncStatus;
  /** Encrypted (encryptV3) LiteLLM virtual key. Absent until a key is minted. */
  virtualKey?: string;
  models: LiteLLMSyncModel[];
  /** sha256 of the real upstream baseURL — detect drift without storing the URL. */
  realBaseURLHash?: string;
  lastError?: string | null;
  lastSyncedAt?: Date;
  /** Tenant identifier for multi-tenancy isolation. */
  tenantId?: string;
  createdAt?: Date;
  updatedAt?: Date;
};

export type ILiteLLMSync = LiteLLMSync &
  Document & {
    _id: Types.ObjectId;
  };
