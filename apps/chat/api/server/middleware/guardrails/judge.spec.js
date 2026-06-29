const { buildJudgeMessages, parseJudgeResponse } = require('./judge');

describe('buildJudgeMessages', () => {
  it('returns a system + user message pair containing the user text', () => {
    const msgs = buildJudgeMessages('hello world');
    expect(Array.isArray(msgs)).toBe(true);
    expect(msgs[0].role).toBe('system');
    expect(msgs[msgs.length - 1].role).toBe('user');
    expect(msgs[msgs.length - 1].content).toContain('hello world');
  });

  it('instructs the model to answer in the user’s own language as JSON', () => {
    const sys = buildJudgeMessages('x')[0].content.toLowerCase();
    expect(sys).toContain('json');
    expect(sys).toMatch(/inject|jailbreak/);
    expect(sys).toMatch(/language/);
  });
});

describe('parseJudgeResponse', () => {
  it('parses a clean JSON verdict', () => {
    const v = parseJudgeResponse('{"injection": true, "language": "vi", "message": "Đã chặn."}');
    expect(v).toEqual({ injection: true, language: 'vi', message: 'Đã chặn.' });
  });

  it('parses JSON wrapped in a markdown code fence', () => {
    const v = parseJudgeResponse(
      '```json\n{"injection": false, "language": "en", "message": ""}\n```',
    );
    expect(v.injection).toBe(false);
    expect(v.language).toBe('en');
  });

  it('extracts the JSON object embedded in extra prose', () => {
    const v = parseJudgeResponse(
      'Sure! {"injection": true, "language": "fr", "message": "Bloqué."} done',
    );
    expect(v.injection).toBe(true);
    expect(v.message).toBe('Bloqué.');
  });

  it('coerces a non-boolean injection field to boolean', () => {
    expect(parseJudgeResponse('{"injection":"true","language":"en","message":"x"}').injection).toBe(
      true,
    );
    expect(parseJudgeResponse('{"injection":"false","language":"en","message":""}').injection).toBe(
      false,
    );
  });

  it('returns null on unparseable content', () => {
    expect(parseJudgeResponse('totally not json')).toBeNull();
    expect(parseJudgeResponse('')).toBeNull();
    expect(parseJudgeResponse(undefined)).toBeNull();
  });
});
