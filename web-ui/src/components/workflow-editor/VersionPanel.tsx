import type { WorkflowVersion } from '../../api/client';
import './VersionPanel.css';

interface VersionPanelProps {
  versions: WorkflowVersion[];
  activeVersionId: string | null;
  onView: (version: WorkflowVersion) => void;
  onActivate: (versionId: string) => void;
}

export default function VersionPanel({ versions, activeVersionId, onView, onActivate }: VersionPanelProps) {
  return (
    <div className="version-panel">
      <strong>Versions</strong>
      {versions.length === 0 && <p>No versions yet.</p>}
      {versions.length > 0 && (
        <table className="version-panel__table">
          <thead>
            <tr>
              <th>Number</th>
              <th>Date</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {versions.map((v: WorkflowVersion) => (
              <tr key={v.id}>
                <td>{v.version_number}</td>
                <td>{new Date(v.created_at).toLocaleString()}</td>
                <td>
                  {v.id === activeVersionId && (
                    <span className="version-panel__active-badge">
                      Active
                    </span>
                  )}
                </td>
                <td>
                  <button
                    onClick={() => onView(v)}
                    className="version-panel__action-btn" className="mr-2"
                  >
                    View
                  </button>
                  <button
                    onClick={() => onActivate(v.id)}
                    disabled={v.id === activeVersionId}
                    className="version-panel__action-btn"
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
