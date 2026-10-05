import { useState, type FormEvent } from 'react';
import { streamConsole } from '../../api';
import { Button } from '../../ui/button';
import { Card } from '../../ui/card';

const CMDS = ['status', 'logs', 'logs librechat', 'doctor', 'support'];
type Line = { text: string; error?: boolean };

export function Console() {
  const [lines, setLines] = useState<Line[]>([]);
  const [busy, setBusy] = useState(false);
  const [input, setInput] = useState('');

  const run = async (cmd: string) => {
    setBusy(true);
    setLines([{ text: `$ nufi-box ${cmd}` }]);
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
      <Card title="System Console">
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
          {CMDS.map((c) => (
            <Button key={c} variant="secondary" size="sm" disabled={busy} data-testid={`console-chip-${c.replace(' ', '-')}`} onClick={() => run(c)}>
              {c}
            </Button>
          ))}
        </div>
        <div
          data-testid="console-output"
          style={{ fontFamily: 'var(--mono)', fontSize: 12, minHeight: 160, maxHeight: 320, overflow: 'auto', whiteSpace: 'pre-wrap' }}
        >
          {lines.map((l, i) => (
            <div key={i} data-testid={l.error ? 'console-error' : undefined} style={l.error ? { color: 'var(--bad)' } : undefined}>
              {l.text}
            </div>
          ))}
        </div>
        <form onSubmit={submit} style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 8, fontFamily: 'var(--mono)', fontSize: 12 }}>
          <span aria-hidden="true">root@nufi-box:~#</span>
          <input
            aria-label="Command"
            data-testid="console-input"
            placeholder="Enter command"
            value={input}
            disabled={busy}
            onChange={(e) => setInput(e.target.value)}
            style={{ flex: 1, minWidth: 0, fontFamily: 'inherit', fontSize: 'inherit', border: 'none', outline: 'none', background: 'transparent', color: 'inherit' }}
          />
        </form>
      </Card>
    </div>
  );
}
