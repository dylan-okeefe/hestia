import { EDITOR_NODE_TYPES } from './constants';

interface EditorToolbarProps {
  workflowName: string;
  isDirty: boolean;
  onNameChange: (name: string) => void;
  onNameBlur: () => void;
  addNodeType: string;
  onAddNodeTypeChange: (type: string) => void;
  onAddNode: () => void;
  onSave: () => void;
  onSaveAndActivate: () => void;
  onActivate: () => void;
  onTestRun: () => void;
  onToggleHistory: () => void;
  onToggleVersions: () => void;
  showHistory: boolean;
  showVersions: boolean;
  saving: boolean;
  testing: boolean;
  activeVersionId: string | null;
  error: string | null;
  testError: string | null;
  canUndo: boolean;
  canRedo: boolean;
  onUndo: () => void;
  onRedo: () => void;
}

export default function EditorToolbar({
  workflowName,
  isDirty,
  onNameChange,
  onNameBlur,
  addNodeType,
  onAddNodeTypeChange,
  onAddNode,
  onSave,
  onSaveAndActivate,
  onActivate,
  onTestRun,
  onToggleHistory,
  onToggleVersions,
  showHistory,
  showVersions,
  saving,
  testing,
  activeVersionId,
  error,
  testError,
  canUndo,
  canRedo,
  onUndo,
  onRedo,
}: EditorToolbarProps) {
  return (
    <div style={{ padding: '0.5rem 1rem', borderBottom: '1px solid #ddd', display: 'flex', alignItems: 'center', gap: '1rem' }}>
      <input
        value={workflowName}
        onChange={(e) => onNameChange(e.target.value)}
        onBlur={onNameBlur}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.currentTarget.blur();
          }
        }}
        style={{
          margin: 0,
          fontSize: '1.5rem',
          fontWeight: 'bold',
          border: 'none',
          borderBottom: '1px solid transparent',
          background: 'transparent',
          minWidth: 120,
        }}
        aria-label="Workflow name"
      />
      {isDirty && (
        <span style={{ color: '#666', fontSize: '0.875rem' }} aria-label="Unsaved changes">
          (unsaved)
        </span>
      )}
      <button onClick={onAddNode}>Add Node</button>
      <select
        value={addNodeType}
        onChange={(e) => onAddNodeTypeChange(e.target.value)}
        style={{ padding: '0.25rem 0.5rem' }}
        aria-label="Node type to add"
      >
        {EDITOR_NODE_TYPES.map((t: string) => (
          <option key={t} value={t}>
            {t}
          </option>
        ))}
      </select>
      <button onClick={onUndo} disabled={!canUndo} aria-label="Undo">
        Undo
      </button>
      <button onClick={onRedo} disabled={!canRedo} aria-label="Redo">
        Redo
      </button>
      <button onClick={onSave} disabled={saving}>
        {saving ? 'Saving…' : 'Save Version'}
      </button>
      <button onClick={onSaveAndActivate} disabled={saving}>
        {saving ? 'Saving…' : 'Save & Activate'}
      </button>
      <button onClick={onActivate} disabled={!activeVersionId}>
        Activate Version
      </button>
      <button onClick={onTestRun} disabled={testing}>
        {testing ? 'Running…' : 'Test Run'}
      </button>
      <button onClick={onToggleHistory}>
        {showHistory ? 'Hide History' : 'Execution History'}
      </button>
      <button onClick={onToggleVersions}>
        {showVersions ? 'Hide Versions' : 'Versions'}
      </button>
      {error && !testError && <span style={{ color: 'red', marginLeft: 'auto' }}>{error}</span>}
    </div>
  );
}
