const { isEnabled } = require('@librechat/api');
const { logger } = require('@librechat/data-schemas');
const denyRequest = require('~/server/middleware/denyRequest');
const { detectPII } = require('./detect');
const { judgeInjection } = require('./judge');

const DEFAULT_INJECTION_MESSAGE =
  '⚠️ Yêu cầu của bạn đã bị chặn bởi bộ lọc bảo mật vì có dấu hiệu can thiệp hệ thống (prompt injection). Vui lòng diễn đạt lại theo cách khác.';
const DEFAULT_PII_BLOCK_MESSAGE =
  '⚠️ Yêu cầu của bạn chứa thông tin nhạy cảm (PII) và đã bị chặn theo chính sách bảo mật.';

/**
 * Application-layer input guardrail for the chat path.
 *
 * Runs after `moderateText` on the unified agents chat route. Two checks, both
 * DETECTION-ONLY — the user's prompt is NEVER mutated (this is the deliberate
 * fix for the old Presidio bug where input masking corrupted the prompt):
 *
 *   ① Prompt-injection / jailbreak → block the request (no model call).
 *   ② PII in input → warn/log only by default; optionally block. The prompt is
 *      always forwarded to the model untouched.
 *
 * Toggled by GUARDRAIL_ENABLED (master), GUARDRAIL_INJECTION_ENABLED,
 * GUARDRAIL_PII_INPUT_MODE = off | warn | block.
 *
 * @type {import('express').RequestHandler}
 */
async function inputGuard(req, res, next) {
  if (!isEnabled(process.env.GUARDRAIL_ENABLED)) {
    return next();
  }

  const text = typeof req.body?.text === 'string' ? req.body.text : '';
  if (!text) {
    return next();
  }

  const userId = req.user?.id;

  // ① Prompt-injection — AI judge (LLM-as-judge, multilingual) with a heuristic
  // fallback when the guard model is unavailable. Block on a positive verdict;
  // the refusal message is the judge's localized one (in the user's language).
  if (process.env.GUARDRAIL_INJECTION_ENABLED !== 'false') {
    const verdict = await judgeInjection(text);
    if (verdict.injection) {
      logger.warn(
        `[guardrail] blocked prompt injection (source: ${verdict.source}, lang: ${verdict.language || '?'}) user=${userId}`,
      );
      return denyRequest(
        req,
        res,
        verdict.message || process.env.GUARDRAIL_INJECTION_MESSAGE || DEFAULT_INJECTION_MESSAGE,
      );
    }
  }

  // ② Input PII — warn/log only by default. NEVER mutates the prompt.
  const piiMode = (process.env.GUARDRAIL_PII_INPUT_MODE || 'warn').toLowerCase();
  if (piiMode !== 'off') {
    const pii = detectPII(text);
    if (pii.length > 0) {
      const types = [...new Set(pii.map((m) => m.type))].join(', ');
      logger.warn(
        `[guardrail] PII detected in input (${types}) user=${userId} — prompt forwarded unchanged`,
      );
      if (piiMode === 'block') {
        return denyRequest(
          req,
          res,
          process.env.GUARDRAIL_PII_BLOCK_MESSAGE || DEFAULT_PII_BLOCK_MESSAGE,
        );
      }
    }
  }

  return next();
}

module.exports = inputGuard;
