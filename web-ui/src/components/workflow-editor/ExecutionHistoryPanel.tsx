import { Fragment } from 'react';
import type { Node } from 'reactflow';
import type { ExecutionRecord, ExecutionResult } from '../../api/client';
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
                {executions.map((ex: ExecutionRecord) => (
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
                              {ex.node_results.map((nr) => (
                                <tr key={nr.node_id}>
                                  <td>
                                    {formatNodeLabel(nr.node_id, nodes)}
                                  </td>
                                  <td className={nr.status === 'ok' ? 'text-success' : 'text-danger'}>
                                    {nr.status}
                                  </td>
                                  <td>{nr.elapsed_ms}ms</td>
                                  <td>
                                    {typeof nr.output === 'string' ? nr.output : JSON.stringify(nr.output)?.slice(0, 100)}
                                  </td>
                                </tr>
                              ))}
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
      {(testResult || testError) && (
        <div className={show ? 'execution-history-panel__test-result' : ''}>
          {testResult && (
            <>
              <div className="execution-history-panel__test-meta">
                <strong>Status:</strong>
                <span className={testResult.status === 'ok' ? 'text-success' : 'text-danger'} className="font-bold">
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
                  {testResult.node_results.map((nr) => (
                    <tr key={nr.node_id}>
                      <td>
                        {formatNodeLabel(nr.node_id, nodes)}
                      </td>
                      <td className={nr.status === 'ok' ? 'text-success' : 'text-danger'}>{nr.status}</td>
                      <td>{nr.elapsed_ms}</td>
                      <td>{nr.prompt_tokens}</td>
                      <td>{nr.completion_tokens}</td>
                      <td>
                        {typeof nr.output === 'string' ? nr.output : JSON.stringify(nr.output)?.slice(0, 100)}
                      </td>
                    </tr>
                  ))}
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
