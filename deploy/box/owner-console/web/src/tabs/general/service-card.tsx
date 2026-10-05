import { Badge } from '../../ui/badge';
import { Card } from '../../ui/card';

export function ServiceCard({ id, label, ok, detail }: { id: string; label: string; ok: boolean; detail?: string }) {
  return (
    <div data-testid={`service-${id}`}>
      <Card title={label} right={<Badge tone={ok ? 'ok' : 'bad'}>{ok ? 'Running' : 'Down'}</Badge>}>
        {detail && <p style={{ margin: 0, color: 'var(--gray-1)' }}>{detail}</p>}
      </Card>
    </div>
  );
}
