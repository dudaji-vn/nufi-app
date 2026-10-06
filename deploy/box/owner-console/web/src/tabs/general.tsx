import { useStatus } from '../api';
import { IconChat, IconDatabase, IconServer, IconSparkles } from '../ui/icons';
import { Console } from './general/console';
import { Controls } from './general/controls';
import { ServiceCard } from './general/service-card';
import './general/general.css';

// The four Figma cards, each backed by the health probe that stands for it
// (matched by probe name; Web Server is caddy, Database is a Postgres TCP probe,
// chat is librechat, AI Model is litellm-proxy/ollama). `tech` is the static
// subtitle shown when the probe reports no live detail; `fmt` shapes a live one.
const CARDS = [
  { id: 'web-server', label: 'Web Server', probe: 'Web Server', icon: <IconServer />, tech: 'Caddy' },
  { id: 'database', label: 'Database', probe: 'Database', icon: <IconDatabase />, tech: 'Postgres' },
  { id: 'chat', label: 'NuFi Chat App', probe: 'Chat', icon: <IconChat />, tech: 'LibreChat', fmt: (v: string) => `Version ${v}` },
  { id: 'ai-model', label: 'AI Model', probe: 'AI model', icon: <IconSparkles />, tech: 'Local model' },
];

export function General() {
  const { data, isPending, error } = useStatus();
  if (isPending) return <p role="status">Loading…</p>;
  if (error) return <p role="alert">Could not load status: {(error as { error?: string }).error ?? 'unknown error'}</p>;
  const svc = (name: string) => data.services.find((s) => s.name === name);
  const active = CARDS.every((c) => svc(c.probe)?.ok === true);
  return (
    <div data-testid="general">
      <Controls active={active} />
      <div className="general-grid">
        {CARDS.map((c) => {
          const detail = svc(c.probe)?.detail;
          return (
            <ServiceCard
              key={c.id}
              id={c.id}
              label={c.label}
              ok={svc(c.probe)?.ok === true}
              icon={c.icon}
              subtitle={detail ? (c.fmt ? c.fmt(detail) : detail) : c.tech}
            />
          );
        })}
      </div>
      <Console />
    </div>
  );
}
