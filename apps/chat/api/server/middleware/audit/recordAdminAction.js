const { logger } = require('@librechat/data-schemas');
const { createAuditLog } = require('~/models');

const MUTATING_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

/**
 * Maps a resource domain + HTTP method to a stable audit action key.
 * Grants keep their existing `grant_assigned` / `grant_removed` keys so the
 * legacy grants audit tab and filters stay valid.
 *
 * @param {string} resourceType - e.g. 'user', 'role', 'group', 'grant', 'config'.
 * @param {string} method - HTTP method.
 * @returns {string}
 */
function resolveAction(resourceType, method) {
  if (resourceType === 'grant') {
    return method === 'DELETE' ? 'grant_removed' : 'grant_assigned';
  }
  switch (method) {
    case 'POST':
      return `${resourceType}_created`;
    case 'DELETE':
      return `${resourceType}_deleted`;
    default:
      return `${resourceType}_updated`;
  }
}

/**
 * Pulls target identifiers out of the request URL. The audit middleware runs at
 * the router level where req.params is not yet populated, so we parse the path
 * segments after `/api/admin/<resource>` directly.
 *
 * @param {string} originalUrl
 * @param {string} resourceType
 */
function extractTarget(originalUrl, resourceType) {
  const path = (originalUrl || '').split('?')[0];
  const segments = path.split('/').filter(Boolean); // ['api','admin','<resource>', ...]
  const rest = segments.slice(3).map((segment) => {
    try {
      return decodeURIComponent(segment);
    } catch {
      return segment;
    }
  });

  if (resourceType === 'grant') {
    const [principalType, principalId, capability] = rest;
    return { targetId: principalId, targetName: principalId, capability, principalType };
  }

  const first = rest[0];
  const targetId = first && first !== 'search' ? first : undefined;
  return { targetId, targetName: undefined, capability: undefined };
}

/**
 * Express middleware factory. Attach at the top of an admin sub-router (after
 * the auth guards). Records one audit entry for every successful (status < 400)
 * mutating request on that router. GET/HEAD requests are ignored. Writing is
 * best-effort and runs on the `finish` event, so it never delays or breaks the
 * response.
 *
 * @param {string} resourceType - Domain label for this router, e.g. 'user'.
 * @returns {import('express').RequestHandler}
 */
function recordAdminAction(resourceType) {
  return function auditMiddleware(req, res, next) {
    if (!MUTATING_METHODS.has(req.method)) {
      return next();
    }

    res.on('finish', () => {
      try {
        if (res.statusCode >= 400) {
          return;
        }

        const actor = req.user || {};
        const body = req.body || {};
        const { targetId, targetName, capability } = extractTarget(req.originalUrl, resourceType);

        createAuditLog({
          action: resolveAction(resourceType, req.method),
          actorId: actor.id || actor._id,
          actorName: actor.name || actor.email || actor.username || 'unknown',
          targetType: resourceType,
          targetId: targetId ? String(targetId) : undefined,
          targetName:
            String(targetName || body.name || body.email || body.username || targetId || '') ||
            undefined,
          capability: capability || body.capability,
          method: req.method,
          path: req.originalUrl,
          ipAddress: req.ip,
          userAgent: req.get('user-agent'),
          status: 'success',
          statusCode: res.statusCode,
        });
      } catch (error) {
        logger.error('[recordAdminAction] Failed to record audit entry', error);
      }
    });

    next();
  };
}

module.exports = recordAdminAction;
