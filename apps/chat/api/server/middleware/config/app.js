const { logger } = require('@librechat/data-schemas');
const { getAppConfig } = require('~/server/services/Config');

const configMiddleware = async (req, res, next) => {
  try {
    const userRole = req.user?.role;
    const userId = req.user?.id;
    const tenantId = req.user?.tenantId;
    // `req.config` feeds the chat/agent routes, which open provider connections
    // from these endpoint credentials, so admin-managed endpoints must resolve
    // to their gateway routing here. Read-only callers must NOT ask for this.
    req.config = await getAppConfig({
      role: userRole,
      userId,
      tenantId,
      resolveManagedEndpoints: true,
    });

    next();
  } catch (error) {
    logger.error('Config middleware error:', {
      error: error.message,
      userRole: req.user?.role,
      path: req.path,
    });

    try {
      req.config = await getAppConfig({
        tenantId: req.user?.tenantId,
        resolveManagedEndpoints: true,
      });
      next();
    } catch (fallbackError) {
      logger.error('Fallback config middleware error:', fallbackError);
      next(fallbackError);
    }
  }
};

module.exports = configMiddleware;
