import { useState, type FormEvent } from 'react';
import { get, streamConsole, type StatusResponse } from '../../api';
import { Button } from '../../ui/button';

// `support` is a host-only command the hardened console cannot run, so it is not
// offered as a chip (typing it still returns the "run it on the box" note).
// `doctor` runs in-app against /api/status (read-only), not the host script.
const CMDS = ['status', 'logs', 'logs librechat', 'doctor'];
type Line = { text: string; error?: boolean; prompt?: boolean };

// A doctor read the hardened console CAN serve: the same per-service health the
// dashboard shows (/api/status), formatted like `nufi-box doctor`'s ok/FAIL lines.
async function doctorLines(): Promise<string[]> {
  const s = await get<StatusResponse>('/api/status');
  const out = s.services.map((h) => {
    const meta = [h.status, `${h.ms}ms`].filter(Boolean).join(', ');
    return `${h.ok ? ' ok ' : 'FAIL'} ${h.name}${meta ? ` (${meta})` : ''}${h.error ? ` — ${h.error}` : ''}`;
  });
  const bad = s.services.filter((h) => !h.ok).length;
  out.push(bad ? `${bad} service${bad === 1 ? '' : 's'} need attention` : 'All services healthy.');
  return out;
}

export function Console() {
  const [lines, setLines] = useState<Line[]>([]);
  const [busy, setBusy] = useState(false);
  const [input, setInput] = useState('');

  const run = async (cmd: string) => {
    setBusy(true);
    setLines([{ text: `root@nufi-box:~# ./nufi-box ${cmd}`, prompt: true }]);
    try {
      if (cmd === 'doctor') {
        for (const l of await doctorLines()) setLines((p) => [...p, { text: l }]);
      } else {
        await streamConsole(cmd, (l) => setLines((p) => [...p, { text: l }]));
      }
    } catch (e) {
      setLines((p) => [...p, { text: `error: ${(e as { error?: string }).error ?? 'command failed'}`, error: true }]);
    } finally {
      setBusy(false);
    }
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const cmd = input.trim();
    if (!cmd || busy) return;
    setInput('');
    void run(cmd);
  };

  return (
    <div data-testid="console">
      <h2 className="console-head">System Console</h2>
      <div className="console-term">
        <div className="console-term__out" data-testid="console-output">
          {lines.map((l, i) => (
            <div
              key={i}
              data-testid={l.error ? 'console-error' : undefined}
              className={l.error ? 'console-term__line--error' : l.prompt ? 'console-term__line--prompt' : undefined}
            >
              {l.text}
            </div>
          ))}
        </div>
        <form className="console-term__form" onSubmit={submit}>
          <span className="console-term__prompt" aria-hidden="true">root@nufi-box:~#</span>
          <input
            className="console-term__input"
            aria-label="Command"
            data-testid="console-input"
            placeholder="Enter command"
            value={input}
            disabled={busy}
            onChange={(e) => setInput(e.target.value)}
          />
        </form>
      </div>
      <div className="console-cmds">
        <span className="console-cmds__label">Available commands:</span>
        {CMDS.map((c) => (
          <Button
            key={c}
            variant="secondary"
            size="sm"
            disabled={busy}
            data-testid={`console-chip-${c.replace(' ', '-')}`}
            onClick={() => run(c)}
          >
            {c}
          </Button>
        ))}
        <span className="console-cmds__hint">Press ⏎ Enter to execute</span>
      </div>
    </div>
  );
}
