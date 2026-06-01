const { logger } = require('@librechat/data-schemas');
const { createAuditLog } = require('~/models');

/**
 * Records an `admin_login` audit entry when an admin authenticates through the
 * admin panel. Insert into the login chain after the auth + admin guards so
 * req.user is populated. Records on the `finish` event and only on success
 * (status < 400), so it never blocks or breaks the login response.
 *
 * @type {import('express').RequestHandler}
 */
function recordAdminLogin(req, res, next) {
  res.on('finish', () => {
    try {
      if (res.statusCode >= 400) {
        return;
      }
      const actor = req.user || {};
      createAuditLog({
        action: 'admin_login',
        actorId: actor.id || actor._id,
        actorName:
          actor.name || actor.email || actor.username || (req.body && req.body.email) || 'unknown',
        targetType: 'session',
        details: 'Admin signed in to the admin panel',
        method: req.method,
        path: req.originalUrl,
        ipAddress: req.ip,
        userAgent: req.get('user-agent'),
        status: 'success',
        statusCode: res.statusCode,
      });
    } catch (error) {
      logger.error('[recordAdminLogin] Failed to record audit entry', error);
    }
  });
  next();
}

module.exports = recordAdminLogin;
