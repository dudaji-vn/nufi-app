const express = require('express');
const { logger, SystemCapabilities } = require('@librechat/data-schemas');
const { requireCapability } = require('~/server/middleware/roles/capabilities');
const { requireJwtAuth } = require('~/server/middleware');
const litellmGateway = require('~/server/services/LiteLLM');

const router = express.Router();

router.use(requireJwtAuth, requireCapability(SystemCapabilities.ACCESS_ADMIN));

/**
 * POST /api/admin/litellm/resync
 * Re-run the LiteLLM reconcile from the current base-config custom endpoints.
 * Recovery path for endpoints left in a failed/pending sync state.
 */
router.post('/resync', async (req, res) => {
  try {
    const tenantId = req.user?.tenantId;
    await litellmGateway.resyncAll({ tenantId });
    return res.status(200).json({ success: true });
  } catch (error) {
    logger.error('[adminLiteLLM] resync failed:', error);
    return res.status(500).json({ error: 'Failed to resync LiteLLM' });
  }
});

module.exports = router;
