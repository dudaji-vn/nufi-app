import { Badge } from '../../ui/badge';
import { Card } from '../../ui/card';

export function ServiceCard({ id, label, ok }: { id: string; label: string; ok: boolean }) {
  return (
    <div data-testid={`service-${id}`}>
      <Card title={label} right={<Badge tone={ok ? 'ok' : 'bad'}>{ok ? 'Running' : 'Down'}</Badge>} />
    </div>
  );
}
