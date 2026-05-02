import { Fragment } from 'react';
import type { Node } from 'reactflow';
import type { ExecutionRecord, ExecutionResult } from '../../api/client';

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
    <div
      style={{
        borderTop: '1px solid #ddd',
        padding: '1rem',
        maxHeight: '40vh',
        overflowY: 'auto',
        background: '#fafafa',
      }}
    >
      {show && (
        <>
          <strong>Execution History</strong>
          {loading && <p>Loading…</p>}
          {error && <p style={{ color: 'red' }}>{error}</p>}
          {!loading && !error && executions.length === 0 && <p>No executions yet.</p>}
          {!loading && executions.length > 0 && (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem', marginTop: '0.5rem' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #ccc' }}>
                  <th style={{ textAlign: 'left', padding: '0.25rem' }}>Time</th>
                  <th style={{ textAlign: 'left', padding: '0.25rem' }}>Status</th>
                  <th style={{ textAlign: 'left', padding: '0.25rem' }}>Elapsed</th>
                  <th style={{ textAlign: 'left', padding: '0.25rem' }}>Tokens</th>
                  <th style={{ textAlign: 'left', padding: '0.25rem' }}>Nodes</th>
                </tr>
              </thead>
              <tbody>
                {executions.map((ex: ExecutionRecord) => (
                  <Fragment key={ex.id}>
                    <tr
                      style={{ borderBottom: '1px solid #eee', cursor: 'pointer' }}
                      onClick={() => onSelectExecution(ex.id === selectedExecution ? null : ex.id)}
                    >
                      <td style={{ padding: '0.25rem' }}>{new Date(ex.created_at).toLocaleString()}</td>
                      <td style={{ padding: '0.25rem', color: ex.status === 'ok' ? 'green' : 'red' }}>{ex.status}</td>
                      <td style={{ padding: '0.25rem' }}>{ex.total_elapsed_ms}ms</td>
                      <td style={{ padding: '0.25rem' }}>
                        {ex.total_prompt_tokens} prompt + {ex.total_completion_tokens} completion
                      </td>
                      <td style={{ padding: '0.25rem' }}>{ex.node_results.length}</td>
                    </tr>
                    {selectedExecution === ex.id && (
                      <tr>
                        <td colSpan={5} style={{ padding: '0.5rem', background: '#f0f0f0' }}>
                          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
                            <thead>
                              <tr style={{ borderBottom: '1px solid #ccc' }}>
                                <th style={{ textAlign: 'left', padding: '0.25rem' }}>Node</th>
                                <th style={{ textAlign: 'left', padding: '0.25rem' }}>Status</th>
                                <th style={{ textAlign: 'left', padding: '0.25rem' }}>Time</th>
                                <th style={{ textAlign: 'left', padding: '0.25rem' }}>Output</th>
                              </tr>
                            </thead>
                            <tbody>
                              {ex.node_results.map((nr) => (
                                <tr key={nr.node_id} style={{ borderBottom: '1px solid #eee' }}>
                                  <td style={{ padding: '0.25rem' }}>
                                    {formatNodeLabel(nr.node_id, nodes)}
                                  </td>
                                  <td style={{ padding: '0.25rem', color: nr.status === 'ok' ? 'green' : 'red' }}>
                                    {nr.status}
                                  </td>
                                  <td style={{ padding: '0.25rem' }}>{nr.elapsed_ms}ms</td>
                                  <td style={{ padding: '0.25rem' }}>
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
        <div style={{ marginTop: show ? '1rem' : 0 }}>
          {testResult && (
            <>
              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '0.5rem' }}>
                <strong>Status:</strong>
                <span style={{ color: testResult.status === 'ok' ? 'green' : 'red', fontWeight: 'bold' }}>
                  {testResult.status}
                </span>
                <span>
                  <strong>Total time:</strong> {testResult.total_elapsed_ms}ms
                </span>
                <span>
                  <strong>Tokens:</strong> {testResult.total_prompt_tokens} prompt + {testResult.total_completion_tokens} completion
                </span>
              </div>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #ccc' }}>
                    <th style={{ textAlign: 'left', padding: '0.25rem' }}>Node</th>
                    <th style={{ textAlign: 'left', padding: '0.25rem' }}>Status</th>
                    <th style={{ textAlign: 'left', padding: '0.25rem' }}>Time (ms)</th>
                    <th style={{ textAlign: 'left', padding: '0.25rem' }}>Prompt</th>
                    <th style={{ textAlign: 'left', padding: '0.25rem' }}>Completion</th>
                    <th style={{ textAlign: 'left', padding: '0.25rem' }}>Output</th>
                  </tr>
                </thead>
                <tbody>
                  {testResult.node_results.map((nr) => (
                    <tr key={nr.node_id} style={{ borderBottom: '1px solid #eee' }}>
                      <td style={{ padding: '0.25rem' }}>
                        {formatNodeLabel(nr.node_id, nodes)}
                      </td>
                      <td style={{ padding: '0.25rem', color: nr.status === 'ok' ? 'green' : 'red' }}>{nr.status}</td>
                      <td style={{ padding: '0.25rem' }}>{nr.elapsed_ms}</td>
                      <td style={{ padding: '0.25rem' }}>{nr.prompt_tokens}</td>
                      <td style={{ padding: '0.25rem' }}>{nr.completion_tokens}</td>
                      <td style={{ padding: '0.25rem' }}>
                        {typeof nr.output === 'string' ? nr.output : JSON.stringify(nr.output)?.slice(0, 100)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
          {testError && (
            <div style={{ color: 'red' }}>
              <strong>Test Run Failed:</strong> {testError}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
