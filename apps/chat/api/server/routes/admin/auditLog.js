const express = require('express');
const { logger, SystemCapabilities } = require('@librechat/data-schemas');
const { requireCapability } = require('~/server/middleware/roles/capabilities');
const { requireJwtAuth } = require('~/server/middleware');
const { toAuditLogEntry, toAuditCsv } = require('~/server/services/Audit');
const db = require('~/models');

const router = express.Router();

const requireAdminAccess = requireCapability(SystemCapabilities.ACCESS_ADMIN);

router.use(requireJwtAuth, requireAdminAccess);

/** Parse list/export filters from the query string. */
function parseFilters(query) {
  const limit = query.limit ? parseInt(query.limit, 10) : undefined;
  const skip = query.skip ? parseInt(query.skip, 10) : undefined;
  return {
    search: query.search || undefined,
    action: query.action || undefined,
    from: query.from || undefined,
    to: query.to || undefined,
    limit: Number.isFinite(limit) ? limit : undefined,
    skip: Number.isFinite(skip) ? skip : undefined,
  };
}

/** GET /api/admin/audit-log — list audit entries with filters + pagination. */
router.get('/', async (req, res) => {
  try {
    const filters = parseFilters(req.query);
    const [logs, total] = await Promise.all([db.getAuditLogs(filters), db.countAuditLogs(filters)]);
    res.json({ entries: logs.map(toAuditLogEntry), total });
  } catch (error) {
    logger.error('[GET /api/admin/audit-log] Failed to load audit log', error);
    res.status(500).json({ error: 'Failed to load audit log' });
  }
});

/** GET /api/admin/audit-log/export — CSV export of the filtered audit entries. */
router.get('/export', async (req, res) => {
  try {
    const filters = parseFilters(req.query);
    const logs = await db.getAuditLogs({ ...filters, limit: 10000, skip: 0 });
    const csv = toAuditCsv(logs.map(toAuditLogEntry));
    res.setHeader('Content-Type', 'text/csv; charset=utf-8');
    res.setHeader('Content-Disposition', 'attachment; filename="audit-log.csv"');
    res.send(csv);
  } catch (error) {
    logger.error('[GET /api/admin/audit-log/export] Failed to export audit log', error);
    res.status(500).json({ error: 'Failed to export audit log' });
  }
});

module.exports = router;
