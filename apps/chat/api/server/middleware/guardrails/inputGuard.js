const { isEnabled } = require('@librechat/api');
const { logger } = require('@librechat/data-schemas');
const { detectInjection, detectPII, piiTypeCounts } = require('./detect');
const { judgeInjection, FALLBACK_BLOCK_MESSAGE, localizedBlockMessage, detectLang } = require('./judge');
const { recordGuardrailEvent } = require('./audit');

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

  // ① Prompt-injection. The mode keeps the NORMAL chat experience unchanged:
  //   - 'hybrid' (default): the instant heuristic runs on every message; the AI
  //     judge (multilingual, localized refusal) is consulted ONLY when the
  //     heuristic flags something — so a normal chat never pays the AI latency.
  //   - 'ai': AI judge on every message (broadest multilingual detection, but
  //     adds one model call of latency per message).
  //   - 'heuristic': heuristic only, no AI (bilingual refusal).
  if (process.env.GUARDRAIL_INJECTION_ENABLED !== 'false') {
    const mode = (process.env.GUARDRAIL_INJECTION_MODE || 'hybrid').toLowerCase();
    let verdict = { injection: false, message: '', language: '', source: 'none' };
    let heuristicRule = null;

    if (mode === 'ai') {
      verdict = await judgeInjection(text, { model: req.body?.model });
    } else {
      const det = detectInjection(text);
      if (det.detected) {
        heuristicRule = det.rule;
        if (mode === 'heuristic') {
          verdict = { injection: true, message: FALLBACK_BLOCK_MESSAGE, language: '', source: 'heuristic' };
        } else if (det.hard) {
          // hybrid + unambiguous jailbreak signature: block immediately without
          // an AI-judge veto (a small judge model sometimes under-flags a known
          // jailbreak). Localize the refusal locally — no model call, no latency.
          verdict = {
            injection: true,
            message: localizedBlockMessage(text),
            language: detectLang(text),
            source: 'heuristic',
          };
        } else {
          // hybrid + ambiguous signature: let the AI judge confirm so benign
          // phrasings ("show me the instructions") are not blocked.
          verdict = await judgeInjection(text, { model: req.body?.model });
        }
      }
    }

    if (verdict.injection) {
      logger.warn(
        `[guardrail] blocked prompt injection (mode: ${mode}, source: ${verdict.source}, lang: ${verdict.language || '?'}) user=${userId}`,
      );
      // Flag the request instead of responding here: the resumable agents
      // controller turns this into a normal streamed assistant message (a hard
      // response from middleware would leave the client spinning forever).
      req.guardrailBlock = {
        type: 'injection',
        message:
          verdict.message || process.env.GUARDRAIL_INJECTION_MESSAGE || DEFAULT_INJECTION_MESSAGE,
      };
      recordGuardrailEvent({
        type: 'injection',
        req,
        model: req.body?.model,
        source: verdict.source,
        language: verdict.language,
        mode,
        rule: heuristicRule,
      });
      return next();
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
        req.guardrailBlock = {
          type: 'pii',
          message: process.env.GUARDRAIL_PII_BLOCK_MESSAGE || DEFAULT_PII_BLOCK_MESSAGE,
        };
        recordGuardrailEvent({
          type: 'pii_input',
          req,
          model: req.body?.model,
          piiTypes: piiTypeCounts(pii),
        });
        return next();
      }
    }
  }

  return next();
}

module.exports = inputGuard;
