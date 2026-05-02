import type { WorkflowVersion } from '../../api/client';

interface VersionPanelProps {
  versions: WorkflowVersion[];
  activeVersionId: string | null;
  onView: (version: WorkflowVersion) => void;
  onActivate: (versionId: string) => void;
}

export default function VersionPanel({ versions, activeVersionId, onView, onActivate }: VersionPanelProps) {
  return (
    <div
      style={{
        borderTop: '1px solid #ddd',
        padding: '1rem',
        maxHeight: '40vh',
        overflowY: 'auto',
        background: '#fafafa',
      }}
    >
      <strong>Versions</strong>
      {versions.length === 0 && <p>No versions yet.</p>}
      {versions.length > 0 && (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem', marginTop: '0.5rem' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid #ccc' }}>
              <th style={{ textAlign: 'left', padding: '0.25rem' }}>Number</th>
              <th style={{ textAlign: 'left', padding: '0.25rem' }}>Date</th>
              <th style={{ textAlign: 'left', padding: '0.25rem' }}>Status</th>
              <th style={{ textAlign: 'left', padding: '0.25rem' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {versions.map((v: WorkflowVersion) => (
              <tr key={v.id} style={{ borderBottom: '1px solid #eee' }}>
                <td style={{ padding: '0.25rem' }}>{v.version_number}</td>
                <td style={{ padding: '0.25rem' }}>{new Date(v.created_at).toLocaleString()}</td>
                <td style={{ padding: '0.25rem' }}>
                  {v.id === activeVersionId && (
                    <span
                      style={{
                        display: 'inline-block',
                        padding: '0.125rem 0.5rem',
                        borderRadius: '9999px',
                        background: '#dcfce7',
                        color: '#166534',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                      }}
                    >
                      Active
                    </span>
                  )}
                </td>
                <td style={{ padding: '0.25rem' }}>
                  <button
                    onClick={() => onView(v)}
                    style={{ padding: '0.125rem 0.5rem', fontSize: '0.75rem', marginRight: '0.5rem' }}
                  >
                    View
                  </button>
                  <button
                    onClick={() => onActivate(v.id)}
                    disabled={v.id === activeVersionId}
                    style={{ padding: '0.125rem 0.5rem', fontSize: '0.75rem' }}
                  >
                    Activate
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
