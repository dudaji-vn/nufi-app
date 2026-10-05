import { useState } from 'react';
import { streamConsole } from '../../api';
import { Button } from '../../ui/button';
import { Card } from '../../ui/card';

const CMDS = ['status', 'logs', 'logs librechat', 'doctor', 'support'];

export function Console() {
  const [lines, setLines] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  const run = async (cmd: string) => {
    setBusy(true);
    setLines([`$ nufi-box ${cmd}`]);
    try {
      await streamConsole(cmd, (l) => setLines((p) => [...p, l]));
    } catch (e) {
      setLines((p) => [...p, `error: ${(e as { error?: string }).error ?? 'command failed'}`]);
    } finally {
      setBusy(false);
    }
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
        <pre
          data-testid="console-output"
          style={{ fontFamily: 'Menlo, Monaco, Consolas, monospace', fontSize: 12, minHeight: 160, maxHeight: 320, overflow: 'auto', margin: 0, whiteSpace: 'pre-wrap' }}
        >
          {lines.join('\n')}
        </pre>
      </Card>
    </div>
  );
}
