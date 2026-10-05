const link = { all: 'unset', cursor: 'pointer', color: 'var(--navy-2)' } as const;

export function Breadcrumb({ path, onNavigate }: { path: string; onNavigate: (path: string) => void }) {
  const parts = path ? path.split('/') : [];
  return (
    <nav aria-label="Breadcrumb" style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap', marginBottom: 12 }}>
      <button type="button" style={link} onClick={() => onNavigate('')}>
        Files
      </button>
      {parts.map((p, i) => {
        const prefix = parts.slice(0, i + 1).join('/');
        return (
          <span key={prefix} style={{ display: 'inline-flex', gap: 6 }}>
            <span aria-hidden="true">›</span>
            {i === parts.length - 1 ? (
              <span aria-current="page">{p}</span>
            ) : (
              <button type="button" style={link} onClick={() => onNavigate(prefix)}>
                {p}
              </button>
            )}
          </span>
        );
      })}
    </nav>
  );
}
