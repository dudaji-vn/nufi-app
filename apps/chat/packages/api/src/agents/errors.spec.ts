import { formatRunErrorText, GENERIC_RUN_ERROR } from './errors';

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
