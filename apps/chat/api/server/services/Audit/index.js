/**
 * Audit log helpers — map persisted IAuditLog documents to the admin API shape
 * (AdminAuditLogEntry) and render a CSV export for compliance reporting.
 */

/**
 * @param {import('@librechat/data-schemas').IAuditLog} doc
 * @returns {import('@librechat/data-schemas').AdminAuditLogEntry}
 */
function toAuditLogEntry(doc) {
  const createdAt = doc.createdAt instanceof Date ? doc.createdAt.toISOString() : doc.createdAt;
  return {
    id: String(doc._id),
    action: doc.action,
    actorId: doc.actorId ? String(doc.actorId) : '',
    actorName: doc.actorName || 'unknown',
    targetType: doc.targetType,
    targetId: doc.targetId,
    targetName: doc.targetName,
    capability: doc.capability,
    details: doc.details,
    ipAddress: doc.ipAddress,
    status: doc.status,
    metadata: doc.metadata,
    timestamp: createdAt || '',
  };
}

/** Columns emitted by the CSV export, in order. */
const CSV_COLUMNS = [
  'timestamp',
  'action',
  'actorName',
  'targetType',
  'targetName',
  'capability',
  'details',
  'ipAddress',
  'status',
];

function csvCell(value) {
  const str = value == null ? '' : String(value);
  return /[",\n\r]/.test(str) ? `"${str.replace(/"/g, '""')}"` : str;
}

/**
 * Render audit entries as a CSV string (header + rows).
 * @param {import('@librechat/data-schemas').AdminAuditLogEntry[]} entries
 * @returns {string}
 */
function toAuditCsv(entries) {
  const header = CSV_COLUMNS.join(',');
  const rows = entries.map((entry) => CSV_COLUMNS.map((col) => csvCell(entry[col])).join(','));
  return [header, ...rows].join('\r\n');
}

module.exports = { toAuditLogEntry, toAuditCsv, CSV_COLUMNS };
