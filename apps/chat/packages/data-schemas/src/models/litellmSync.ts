import litellmSyncSchema from '~/schema/litellmSync';
import { applyTenantIsolation } from '~/models/plugins/tenantIsolation';
import type * as t from '~/types';

export function createLiteLLMSyncModel(mongoose: typeof import('mongoose')) {
  applyTenantIsolation(litellmSyncSchema);
  return (
    mongoose.models.LiteLLMSync ||
    mongoose.model<t.ILiteLLMSync>('LiteLLMSync', litellmSyncSchema)
  );
}
