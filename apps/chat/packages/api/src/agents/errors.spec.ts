import { ErrorTypes } from 'librechat-data-provider';
import { formatRunError, formatRunErrorText, GENERIC_RUN_ERROR } from './errors';

/** The shape measured on a real block: the SDK hoists the body's fields onto the error. */
const blockedError = (risk: string, detail: string) => ({
  status: 400,
  code: '400',
  type: ErrorTypes.GUARDRAIL_BLOCKED,
  param: risk,
  message: `400 ${detail}`,
  error: {
    type: ErrorTypes.GUARDRAIL_BLOCKED,
    param: risk,
    code: '400',
    message: detail,
  },
});

const INJECTION_DETAIL =
  'This request was blocked by a security policy because it looks like an attempt ' +
  "to override the assistant's instructions. If this was a legitimate question, rephrase " +
  'it and try again. (reference: grd_oata7syzkvv33vnxr7jaxhjume)';

describe('formatRunError', () => {
  test('restates a gateway block as a typed payload the renderer can frame', () => {
    const payload = JSON.parse(formatRunError(blockedError('LLM01_INJECTION', INJECTION_DETAIL)));

    expect(payload).toEqual({
      type: ErrorTypes.GUARDRAIL_BLOCKED,
      risk: 'LLM01_INJECTION',
      reference: 'grd_oata7syzkvv33vnxr7jaxhjume',
    });
  });

  test.each(['LLM07_SYSTEM_PROMPT_LEAK', 'GUARDRAIL_UNAVAILABLE', 'LLM99_NOT_YET_KNOWN'])(
    'carries the risk code %s through untouched',
    (risk) => {
      const payload = JSON.parse(
        formatRunError(blockedError(risk, `Refused. (reference: grd_abc123)`)),
      );
      expect(payload.risk).toBe(risk);
    },
  );

  test('reads the discriminator from the parsed body when the SDK does not hoist it', () => {
    const payload = JSON.parse(
      formatRunError({
        message: '400 Refused. (reference: grd_zzz999)',
        error: {
          type: ErrorTypes.GUARDRAIL_BLOCKED,
          param: 'LLM01_INJECTION',
          message: 'Refused. (reference: grd_zzz999)',
        },
      }),
    );

    expect(payload).toEqual({
      type: ErrorTypes.GUARDRAIL_BLOCKED,
      risk: 'LLM01_INJECTION',
      reference: 'grd_zzz999',
    });
  });

  test('omits a reference the gateway did not send rather than inventing one', () => {
    const payload = JSON.parse(
      formatRunError({ type: ErrorTypes.GUARDRAIL_BLOCKED, param: 'LLM01_INJECTION' }),
    );

    expect(payload).toEqual({ type: ErrorTypes.GUARDRAIL_BLOCKED, risk: 'LLM01_INJECTION' });
  });

  test.each([
    ['a bare connection failure', { message: 'connect ECONNREFUSED 127.0.0.1:4000' }],
    ['an upstream 500', { status: 500, message: '500 Internal Server Error' }],
    [
      'a differently-typed provider error',
      { type: 'invalid_request_error', param: 'model', message: '400 Unknown model.' },
    ],
    ['a thrown string', 'connect ECONNREFUSED 127.0.0.1:4000' as unknown as Error],
    ['nothing at all', undefined],
  ])('leaves %s on the plain-text path', (_label, err) => {
    const text = formatRunError(err);

    expect(() => JSON.parse(text)).toThrow();
    expect(text).not.toContain(ErrorTypes.GUARDRAIL_BLOCKED);
  });

  test('still strips the leading status from a non-guardrail message', () => {
    expect(formatRunError({ message: '500 Upstream is on fire.' })).toBe('Upstream is on fire.');
    expect(formatRunError({})).toBe(GENERIC_RUN_ERROR);
  });
});

describe('formatRunErrorText', () => {
  test('surfaces an upstream refusal on its own, keeping the reference id', () => {
    const refusal =
      '400 This request was blocked by a security policy because it looks like an attempt ' +
      "to override the assistant's instructions. If this was a legitimate question, rephrase " +
      'it and try again. (reference: grd_oata7syzkvv33vnxr7jaxhjume)';

    const text = formatRunErrorText(refusal);

    expect(text).toBe(
      'This request was blocked by a security policy because it looks like an attempt ' +
        "to override the assistant's instructions. If this was a legitimate question, rephrase " +
        'it and try again. (reference: grd_oata7syzkvv33vnxr7jaxhjume)',
    );
    expect(text).not.toContain(GENERIC_RUN_ERROR);
    expect(text).toContain('grd_oata7syzkvv33vnxr7jaxhjume');
  });

  test.each([400, 401, 403, 429, 500, 503])('strips a leading %i status code', (status) => {
    expect(formatRunErrorText(`${status} Upstream refused the request.`)).toBe(
      'Upstream refused the request.',
    );
  });

  test('leaves a message with no status prefix untouched', () => {
    expect(formatRunErrorText('Upstream refused the request.')).toBe(
      'Upstream refused the request.',
    );
  });

  test('does not mistake a leading year or quantity for a status code', () => {
    expect(formatRunErrorText('2024 was the last training year.')).toBe(
      '2024 was the last training year.',
    );
    expect(formatRunErrorText('8000 tokens exceeds the limit.')).toBe(
      '8000 tokens exceeds the limit.',
    );
  });

  test.each([undefined, null, '', '   ', '400 ', 400 as unknown as string])(
    'falls back to the generic wrapper for %p',
    (message) => {
      expect(formatRunErrorText(message)).toBe(GENERIC_RUN_ERROR);
    },
  );
});
