/**
 * Heuristic rule definitions for the application-layer LLM guardrails.
 *
 * Detection only — these patterns are NEVER used to mutate a user's prompt.
 * Prompt-injection rules block the request; PII rules drive warn/log (input)
 * and grounded-aware redaction (output). Extend the lists here as policy hardens.
 */

// Prompt-injection / jailbreak rules (English + Vietnamese), case-insensitive.
// Kept non-global so `.test()` is stateless across calls.
const INJECTION_PATTERNS = [
  {
    id: 'ignore_previous',
    re: /ignore\s+(?:all\s+|the\s+|any\s+|your\s+)*(?:previous|prior|above|preceding|earlier)\s+(?:instructions?|prompts?|rules?|directions?|messages?)/i,
  },
  {
    id: 'disregard_previous',
    re: /disregard\s+(?:all\s+|the\s+|any\s+)*(?:previous|prior|above|preceding|earlier)\s+(?:instructions?|prompts?|rules?|directions?)/i,
  },
  {
    id: 'reveal_system_prompt',
    re: /(?:reveal|show|print|repeat|expose|display|tell\s+me)\s+(?:me\s+)?(?:your\s+|the\s+)?(?:system\s+|initial\s+|original\s+)?(?:prompt|instructions?|rules?)/i,
  },
  { id: 'dan_jailbreak', re: /you\s+are\s+now\s+(?:dan\b|developer\s+mode|do\s+anything)/i },
  { id: 'do_anything_now', re: /\bdo\s+anything\s+now\b/i },
  { id: 'developer_mode', re: /\bdeveloper\s+mode\s+(?:enabled|on)\b/i },
  { id: 'jailbreak_word', re: /\bjailbreak\b/i },
  {
    id: 'pretend_no_rules',
    re: /pretend\s+(?:you\s+have\s+no|there\s+are\s+no)\s+(?:rules?|restrictions?|guidelines?)/i,
  },
  // Vietnamese
  {
    id: 'vi_bo_qua',
    re: /bỏ\s+qua\s+(?:mọi|tất\s*cả|các|những)?\s*(?:hướng\s*dẫn|chỉ\s*dẫn|chỉ\s*thị|quy\s*tắc|quy\s*định|yêu\s*cầu|lệnh)/i,
  },
  {
    id: 'vi_tiet_lo',
    re: /(?:tiết\s*lộ|cho\s+(?:tôi\s+)?xem|in\s+ra|hiển\s*thị)\s+.*(?:system\s*prompt|prompt\s+hệ\s+thống|chỉ\s*thị\s+hệ\s+thống|câu\s*lệnh\s+hệ\s+thống)/i,
  },
  // Other languages — common "ignore previous instructions" / "reveal the
  // system prompt" phrasings so the instant heuristic catches multilingual
  // injection without paying for an AI call (see GUARDRAIL_INJECTION_MODE).
  { id: 'ko_ignore', re: /(?:이전|모든)\s*(?:지시|명령|지침)[^\n]{0,10}?무시/ },
  { id: 'ko_reveal', re: /시스템\s*프롬프트[^\n]{0,12}?(?:보여|공개|출력|알려)/ },
  { id: 'ja_ignore', re: /(?:前|以前|これまで)[^\n]{0,8}?(?:指示|命令)[^\n]{0,8}?無視/ },
  { id: 'ja_reveal', re: /システムプロンプト[^\n]{0,10}?(?:見せ|表示|教え|出力)/ },
  {
    id: 'zh_ignore',
    re: /忽[略视][^\n]{0,12}?(?:之前|先前|上面|所有)?[^\n]{0,6}?(?:指令|指示|命令|提示)/,
  },
  { id: 'zh_reveal', re: /(?:显示|展示|输出|告诉我)[^\n]{0,8}?(?:系统提示|系统提示词|系统指令)/ },
  {
    id: 'fr_ignore',
    re: /ignore[zr]?\s+(?:les\s+|toutes\s+les\s+)?instructions\s+(?:précédentes|antérieures)/i,
  },
  {
    id: 'es_ignore',
    re: /ignora\s+(?:las\s+|todas\s+las\s+)?instrucciones\s+(?:anteriores|previas)/i,
  },
  {
    id: 'de_ignore',
    re: /ignoriere\s+(?:die\s+|alle\s+)?(?:vorherigen|vorigen|obigen)\s+anweisungen/i,
  },
  { id: 'ru_ignore', re: /игнорируй[^\n]{0,12}?(?:предыдущие|все)\s+инструкции/i },
];

// PII rules. Ordered by priority — earlier entries win when spans overlap, so
// structured types (SSN, credit card, IP) are claimed before the looser phone
// rule. All global so detectPII can find every occurrence.
const PII_PATTERNS = [
  { type: 'EMAIL', re: /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi },
  { type: 'SSN', re: /\b\d{3}-\d{2}-\d{4}\b/g },
  { type: 'CREDIT_CARD', re: /\b(?:\d{4}[ -]){3}\d{4}\b/g },
  { type: 'CREDIT_CARD', re: /\b\d{13,16}\b/g },
  { type: 'IP', re: /\b(?:\d{1,3}\.){3}\d{1,3}\b/g },
  { type: 'PHONE', re: /(?:\+\d{1,3}[\s.-]?)?\(?\d{2,4}\)?[\s.-]?\d{3,4}[\s.-]?\d{3,4}/g },
];

// Default user-facing replacement when ungrounded PII is redacted from output.
// Overridable via GUARDRAIL_REDACT_MESSAGE.
const DEFAULT_REDACT_MESSAGE =
  'Tôi không thể hiển thị trực tiếp thông tin nhạy cảm này do hạn chế về quyền truy cập bảo mật hệ thống.';

module.exports = { INJECTION_PATTERNS, PII_PATTERNS, DEFAULT_REDACT_MESSAGE };
