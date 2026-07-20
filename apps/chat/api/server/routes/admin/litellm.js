const express = require('express');
const { logger, SystemCapabilities } = require('@librechat/data-schemas');
const { requireCapability } = require('~/server/middleware/roles/capabilities');
const { requireJwtAuth } = require('~/server/middleware');
const litellmGateway = require('~/server/services/LiteLLM');

const router = express.Router();

router.use(requireJwtAuth, requireCapability(SystemCapabilities.ACCESS_ADMIN));

/**
 * GET /api/admin/litellm/status
 * Per-endpoint sync status for the admin panel. Never returns secrets.
 * When the feature is off, returns { enabled: false, statuses: {} }.
 */
router.get('/status', async (req, res) => {
  try {
    const tenantId = req.user?.tenantId;
    const result = await litellmGateway.getStatus({ tenantId });
    return res.status(200).json(result);
  } catch (error) {
    logger.error('[adminLiteLLM] status failed:', error);
    return res.status(500).json({ error: 'Failed to read LiteLLM status' });
  }
});

/**
 * POST /api/admin/litellm/resync
 * Recovery path for endpoints left in a failed/pending sync state.
 * Body `{ name }` re-syncs a single endpoint; omit `name` to re-sync all.
 */
router.post('/resync', async (req, res) => {
  try {
    const tenantId = req.user?.tenantId;
    const name = typeof req.body?.name === 'string' ? req.body.name.trim() : '';
    if (name) {
      await litellmGateway.resyncEndpoint({ tenantId, name });
    } else {
      await litellmGateway.resyncAll({ tenantId });
    }
    return res.status(200).json({ success: true });
  } catch (error) {
    logger.error('[adminLiteLLM] resync failed:', error);
    return res.status(500).json({ error: 'Failed to resync LiteLLM' });
  }
});

module.exports = router;
