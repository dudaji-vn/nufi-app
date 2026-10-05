import { useStatus } from '../api';
import { Console } from './general/console';
import { Controls } from './general/controls';
import { ServiceCard } from './general/service-card';

// The four Figma cards, each backed by the health probe(s) that stand for it
// (matched by probe name; Database is a Postgres TCP probe, AI model is Ollama).
const CARDS = [
  { id: 'web-server', label: 'Web Server', probes: ['Console'] },
  { id: 'database', label: 'Database', probes: ['Database'] },
  { id: 'chat', label: 'chat', probes: ['Chat'] },
  { id: 'ai-model', label: 'AI model', probes: ['AI model'] },
];

export function General() {
  const { data, isPending, error } = useStatus();
  if (isPending) return <p role="status">Loading…</p>;
  if (error) return <p role="alert">Could not load status: {(error as { error?: string }).error ?? 'unknown error'}</p>;
  return (
    <div data-testid="general">
      <Controls />
      <div className="general-grid">
      {CARDS.map((c) => (
        <ServiceCard
          key={c.id}
          id={c.id}
          label={c.label}
          ok={c.probes.every((p) => data.services.find((s) => s.name === p)?.ok === true)}
        />
      ))}
      </div>
      <Console />
    </div>
  );
}
