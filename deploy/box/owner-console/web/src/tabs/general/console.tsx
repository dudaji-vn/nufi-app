import { useState, type FormEvent } from 'react';
import { streamConsole } from '../../api';
import { Button } from '../../ui/button';

const CMDS = ['status', 'logs', 'logs librechat', 'doctor', 'support'];
type Line = { text: string; error?: boolean; prompt?: boolean };

export function Console() {
  const [lines, setLines] = useState<Line[]>([]);
  const [busy, setBusy] = useState(false);
  const [input, setInput] = useState('');

  const run = async (cmd: string) => {
    setBusy(true);
    setLines([{ text: `root@nufi-box:~# ./nufi-box ${cmd}`, prompt: true }]);
    try {
      await streamConsole(cmd, (l) => setLines((p) => [...p, { text: l }]));
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
