const inputGuard = require('./inputGuard');
const applyOutputGuard = require('./outputGuard');
const { agentUsesFileSearch, shouldBufferOutput } = require('./outputGuard');
const { detectInjection, detectPII } = require('./detect');
const { redactOutput } = require('./redact');

module.exports = {
  inputGuard,
  applyOutputGuard,
  agentUsesFileSearch,
  shouldBufferOutput,
  detectInjection,
  detectPII,
  redactOutput,
};
