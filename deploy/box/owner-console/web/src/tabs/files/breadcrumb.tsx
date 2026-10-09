import './file-table.css';

export function Breadcrumb({ path, onNavigate }: { path: string; onNavigate: (path: string) => void }) {
  const parts = path ? path.split('/') : [];
  return (
    <nav aria-label="Breadcrumb" className="files-crumb">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="files-crumb__ico">
        <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" />
      </svg>
      <button type="button" className="files-crumb__root" onClick={() => onNavigate('')}>
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
              <button type="button" className="file-table__link" onClick={() => onNavigate(prefix)}>
                {p}
              </button>
            )}
          </span>
        );
      })}
    </nav>
  );
}
