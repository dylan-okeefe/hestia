import { Fragment, useState, useCallback } from 'react';
import type { Node } from 'reactflow';
import type { ExecutionRecord, ExecutionResult, NodeResult } from '../../api/client';
import './ExecutionHistoryPanel.css';

interface ExecutionHistoryPanelProps {
  show: boolean;
  executions: ExecutionRecord[];
  loading: boolean;
  error: string | null;
  selectedExecution: string | null;
  onSelectExecution: (id: string | null) => void;
  testResult: ExecutionResult | null;
  testError: string | null;
  nodes?: Node[];
}

function formatNodeLabel(nodeId: string, nodes?: Node[]) {
  const node = nodes?.find((n) => n.id === nodeId);
  if (node) {
    const label = (node.data?.label as string) || nodeId;
    return `"${label}" (${node.type || 'default'})`;
  }
  return `${nodeId} (deleted node)`;
}

function formatOutput(output: unknown, raw: boolean): string {
  if (typeof output === 'string') {
    return output;
  }
  const json = JSON.stringify(output, null, 2);
  if (!raw) {
    return json;
  }
  return JSON.stringify(output);
}

function OutputCell({
  nr,
  expandedKey,
  isExpanded,
  isRaw,
  onToggleExpand,
  onToggleRaw,
}: {
  nr: NodeResult;
  expandedKey: string;
  isExpanded: boolean;
  isRaw: boolean;
  onToggleExpand: (key: string) => void;
  onToggleRaw: (key: string) => void;
}) {
  const outputText = formatOutput(nr.output, true);
  const displayText = formatOutput(nr.output, isRaw);
  const canExpand = outputText.length > 100 || typeof nr.output === 'object';

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(outputText);
    } catch {
      // ignore
    }
  }, [outputText]);

  return (
    <td className="execution-history-panel__output-cell">
      <div className="execution-history-panel__output-header">
        {!isExpanded ? (
          <span className="execution-history-panel__output-truncate">
            {outputText.slice(0, 100)}
            {outputText.length > 100 && '…'}
          </span>
        ) : (
          <pre className="execution-history-panel__output-pre">{displayText}</pre>
        )}
      </div>
      {canExpand && (
        <div className="execution-history-panel__output-actions">
          <button
            onClick={() => onToggleExpand(expandedKey)}
            className="execution-history-panel__output-btn"
          >
            {isExpanded ? 'Collapse' : 'Expand'}
          </button>
          {isExpanded && (
            <button
              onClick={() => onToggleRaw(expandedKey)}
              className="execution-history-panel__output-btn"
            >
              {isRaw ? 'Formatted' : 'Raw'}
            </button>
          )}
          <button
            onClick={handleCopy}
            className="execution-history-panel__output-btn"
          >
            Copy
          </button>
        </div>
      )}
    </td>
  );
}

export default function ExecutionHistoryPanel({
  show,
  executions,
  loading,
  error,
  selectedExecution,
  onSelectExecution,
  testResult,
  testError,
  nodes,
}: ExecutionHistoryPanelProps) {
  const [expandedOutputs, setExpandedOutputs] = useState<Set<string>>(new Set());
  const [rawModeOutputs, setRawModeOutputs] = useState<Set<string>>(new Set());
  const [statusFilter, setStatusFilter] = useState<'all' | 'ok' | 'error'>('all');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [nodeNameFilter, setNodeNameFilter] = useState('');

  const toggleExpand = useCallback((key: string) => {
    setExpandedOutputs((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  }, []);

  const toggleRaw = useCallback((key: string) => {
    setRawModeOutputs((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  }, []);

  const filteredExecutions = executions.filter((ex) => {
    if (statusFilter !== 'all' && ex.status !== statusFilter) return false;
    if (dateFrom) {
      const from = new Date(dateFrom);
      from.setHours(0, 0, 0, 0);
      if (new Date(ex.created_at) < from) return false;
    }
    if (dateTo) {
      const to = new Date(dateTo);
      to.setHours(23, 59, 59, 999);
      if (new Date(ex.created_at) > to) return false;
    }
    if (nodeNameFilter.trim()) {
      const query = nodeNameFilter.trim().toLowerCase();
      const matchesNode = ex.node_results.some((nr) => {
        const label = formatNodeLabel(nr.node_id, nodes).toLowerCase();
        return label.includes(query);
      });
      if (!matchesNode) return false;
    }
    return true;
  });

  if (!show && !testResult && !testError) return null;

  return (
    <div className="execution-history-panel">
      {show && (
        <>
          <strong>Execution History</strong>
          {loading && <p>Loading…</p>}
          {error && <p className="text-danger">{error}</p>}
          {!loading && !error && executions.length === 0 && <p>No executions yet.</p>}
          {!loading && executions.length > 0 && (
            <>
              <div className="execution-history-panel__filters">
                <label className="execution-history-panel__filter">
                  <span>Status</span>
                  <select
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value as 'all' | 'ok' | 'error')}
                  >
                    <option value="all">All</option>
                    <option value="ok">Success</option>
                    <option value="error">Failure</option>
                  </select>
                </label>
                <label className="execution-history-panel__filter">
                  <span>From</span>
                  <input
                    type="date"
                    value={dateFrom}
                    onChange={(e) => setDateFrom(e.target.value)}
                  />
                </label>
                <label className="execution-history-panel__filter">
                  <span>To</span>
                  <input
                    type="date"
                    value={dateTo}
                    onChange={(e) => setDateTo(e.target.value)}
                  />
                </label>
                <label className="execution-history-panel__filter">
                  <span>Node</span>
                  <input
                    type="text"
                    placeholder="Node name…"
                    value={nodeNameFilter}
                    onChange={(e) => setNodeNameFilter(e.target.value)}
                  />
                </label>
              </div>
              {filteredExecutions.length === 0 && (
                <p className="execution-history-panel__no-results">No executions match the filters.</p>
              )}
              {filteredExecutions.length > 0 && (
                <table className="execution-history-panel__table">
                  <thead>
                    <tr>
                      <th>Time</th>
                      <th>Status</th>
                      <th>Elapsed</th>
                      <th>Tokens</th>
                      <th>Nodes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredExecutions.map((ex: ExecutionRecord) => (
                      <Fragment key={ex.id}>
                        <tr
                          onClick={() => onSelectExecution(ex.id === selectedExecution ? null : ex.id)}
                        >
                          <td>{new Date(ex.created_at).toLocaleString()}</td>
                          <td className={ex.status === 'ok' ? 'text-success' : 'text-danger'}>{ex.status}</td>
                          <td>{ex.total_elapsed_ms}ms</td>
                          <td>
                            {ex.total_prompt_tokens} prompt + {ex.total_completion_tokens} completion
                          </td>
                          <td>{ex.node_results.length}</td>
                        </tr>
                        {selectedExecution === ex.id && (
                          <tr>
                            <td colSpan={5} className="execution-history-panel__detail">
                              <button
                                onClick={() => onSelectExecution(null)}
                                className="execution-history-panel__back-btn"
                              >
                                ← Back to history
                              </button>
                              <table className="execution-history-panel__detail-table">
                                <thead>
                                  <tr>
                                    <th>Node</th>
                                    <th>Status</th>
                                    <th>Time</th>
                                    <th>Output</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {ex.node_results.map((nr) => {
                                    const key = `${ex.id}-${nr.node_id}`;
                                    return (
                                      <tr key={nr.node_id}>
                                        <td>{formatNodeLabel(nr.node_id, nodes)}</td>
                                        <td className={nr.status === 'ok' ? 'text-success' : 'text-danger'}>
                                          {nr.status}
                                        </td>
                                        <td>{nr.elapsed_ms}ms</td>
                                        <OutputCell
                                          nr={nr}
                                          expandedKey={key}
                                          isExpanded={expandedOutputs.has(key)}
                                          isRaw={rawModeOutputs.has(key)}
                                          onToggleExpand={toggleExpand}
                                          onToggleRaw={toggleRaw}
                                        />
                                      </tr>
                                    );
                                  })}
                                </tbody>
                              </table>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          )}
        </>
      )}
      {(testResult || testError) && (
        <div className={show ? 'execution-history-panel__test-result' : ''}>
          {testResult && (
            <>
              <div className="execution-history-panel__test-meta">
                <strong>Status:</strong>
                <span className={`${testResult.status === 'ok' ? 'text-success' : 'text-danger'} font-bold`}>
                  {testResult.status}
                </span>
                <span>
                  <strong>Total time:</strong> {testResult.total_elapsed_ms}ms
                </span>
                <span>
                  <strong>Tokens:</strong> {testResult.total_prompt_tokens} prompt + {testResult.total_completion_tokens} completion
                </span>
              </div>
              <table className="execution-history-panel__table">
                <thead>
                  <tr>
                    <th>Node</th>
                    <th>Status</th>
                    <th>Time (ms)</th>
                    <th>Prompt</th>
                    <th>Completion</th>
                    <th>Output</th>
                  </tr>
                </thead>
                <tbody>
                  {testResult.node_results.map((nr) => {
                    const key = `test-${nr.node_id}`;
                    return (
                      <tr key={nr.node_id}>
                        <td>{formatNodeLabel(nr.node_id, nodes)}</td>
                        <td className={nr.status === 'ok' ? 'text-success' : 'text-danger'}>{nr.status}</td>
                        <td>{nr.elapsed_ms}</td>
                        <td>{nr.prompt_tokens}</td>
                        <td>{nr.completion_tokens}</td>
                        <OutputCell
                          nr={nr}
                          expandedKey={key}
                          isExpanded={expandedOutputs.has(key)}
                          isRaw={rawModeOutputs.has(key)}
                          onToggleExpand={toggleExpand}
                          onToggleRaw={toggleRaw}
                        />
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </>
          )}
          {testError && (
            <div className="text-danger">
              <strong>Test Run Failed:</strong> {testError}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
