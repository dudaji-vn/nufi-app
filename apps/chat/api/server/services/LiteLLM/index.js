const { PrincipalType } = require('librechat-data-provider');
const {
  tenantStorage,
  encryptV3,
  decryptV3,
  BASE_CONFIG_PRINCIPAL_ID,
} = require('@librechat/data-schemas');
const { createLiteLLMGateway } = require('@librechat/api');
const db = require('~/models');

/** Run fn inside the given tenant's ALS context, or as-is when no tenant. */
const runInTenant = (tenantId, fn) => (tenantId ? tenantStorage.run({ tenantId }, fn) : fn());

/**
 * Read the raw (un-rewritten) custom endpoints from the base-config override —
 * used by resync to recover the real provider baseURL/apiKey (getAppConfig would
 * return the already-rewritten values).
 */
async function getRawCustomEndpoints() {
  const config = await db.findConfigByPrincipal(PrincipalType.ROLE, BASE_CONFIG_PRINCIPAL_ID, {
    includeInactive: true,
  });
  return config?.overrides?.endpoints?.custom ?? [];
}

/**
 * The LiteLLM gateway seams consumed by the fork:
 *  - reconcileLiteLLM: admin-config write hook
 *  - applyEndpointRewrite: getAppConfig runtime rewrite
 *  - resyncAll: manual recovery route
 * All no-op unless LITELLM_SYNC_ENABLED=true (+ base URL + master key).
 */
const gateway = createLiteLLMGateway({
  db: {
    findLiteLLMSyncByEndpointName: db.findLiteLLMSyncByEndpointName,
    findLiteLLMSyncByEndpointNames: db.findLiteLLMSyncByEndpointNames,
    listLiteLLMSync: db.listLiteLLMSync,
    upsertLiteLLMSync: db.upsertLiteLLMSync,
    deleteLiteLLMSyncByEndpointName: db.deleteLiteLLMSyncByEndpointName,
  },
  encrypt: encryptV3,
  decrypt: decryptV3,
  runInTenant,
  getRawCustomEndpoints,
});

module.exports = gateway;
