import { useEffect, useState } from 'react';
import { fetchConfig, previewPrompt, type PreviewPromptResult } from '../api/client';
import { useToast } from '../hooks/useToast';
import PageCard from '../components/layout/PageCard';
import LoadingSkeleton from '../components/layout/LoadingSkeleton';
import './ContextLab.css';

interface ConfigValues {
  identityTokens: number;
  memoryTokens: number;
  contextLength: number;
}

export default function ContextLab() {
  const { addToast } = useToast();
  const [configValues, setConfigValues] = useState<ConfigValues | null>(null);
  const [identityTokens, setIdentityTokens] = useState(500);
  const [memoryTokens, setMemoryTokens] = useState(2000);
  const [contextLength, setContextLength] = useState(65536);
  const [historyTurns, setHistoryTurns] = useState(10);
  const [result, setResult] = useState<PreviewPromptResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [pageLoading, setPageLoading] = useState(true);
  const [expandedLayers, setExpandedLayers] = useState<Set<string>>(new Set());
  const [hasChanges, setHasChanges] = useState(false);

  useEffect(() => {
    fetchConfig()
      .then((cfg: Record<string, unknown>) => {
        const core = (cfg.core as Record<string, unknown>) || {};
        const identity = (core.identity as Record<string, unknown>) || {};
        const memory = (core.memory as Record<string, unknown>) || {};
        const inference = (core.inference as Record<string, unknown>) || {};

        const idTokens = (identity.max_tokens as number) || 500;
        const memTokens = (memory.epoch_max_tokens as number) || 2000;
        const ctxLen = (inference.context_length as number) || 65536;

        setConfigValues({ identityTokens: idTokens, memoryTokens: memTokens, contextLength: ctxLen });
        setIdentityTokens(idTokens);
        setMemoryTokens(memTokens);
        setContextLength(ctxLen);
        setPageLoading(false);
      })
      .catch((err) => {
        addToast({ message: err.message || 'Failed to load config', type: 'error', duration: 0 });
        setPageLoading(false);
      });
  }, [addToast]);

  useEffect(() => {
    if (!configValues) return;
    const changed =
      identityTokens !== configValues.identityTokens ||
      memoryTokens !== configValues.memoryTokens ||
      contextLength !== configValues.contextLength;
    setHasChanges(changed);
  }, [identityTokens, memoryTokens, contextLength, configValues]);

  const handleProcess = async () => {
    setLoading(true);
    try {
      const data = await previewPrompt({
        identity_tokens: identityTokens,
        memory_tokens: memoryTokens,
        context_length: contextLength,
        history_turns: historyTurns,
      });
      setResult(data);
    } catch (err: any) {
      addToast({
        message: err.message || 'Failed to preview prompt',
        type: 'error',
        duration: 0,
      });
    } finally {
      setLoading(false);
    }
  };

  const toggleLayer = (name: string) => {
    setExpandedLayers((prev) => {
      const next = new Set(prev);
      if (next.has(name)) {
        next.delete(name);
      } else {
        next.add(name);
      }
      return next;
    });
  };

  if (pageLoading) {
    return (
      <div className="context-lab-page">
        <PageCard>
          <LoadingSkeleton lines={4} />
        </PageCard>
      </div>
    );
  }

  const budgetPercent = result ? Math.min(100, (result.empty_used / result.budget) * 100) : 0;
  const isOverBudget = result ? result.empty_used > result.budget : false;

  return (
    <div className="context-lab-page">
      <h1>Context Lab</h1>
      <p className="context-lab-subtitle">
        Dry-run the system prompt assembly and tune your context budgets.
      </p>

      <PageCard>
        <div className="context-lab-controls">
          <div className="slider-group">
            <label htmlFor="identity-slider">
              Identity budget: <strong>{identityTokens}</strong> tokens
            </label>
            <input
              id="identity-slider"
              type="range"
              min={100}
              max={2000}
              step={50}
              value={identityTokens}
              onChange={(e) => setIdentityTokens(Number(e.target.value))}
            />
          </div>

          <div className="slider-group">
            <label htmlFor="memory-slider">
              Memory budget: <strong>{memoryTokens}</strong> tokens
            </label>
            <input
              id="memory-slider"
              type="range"
              min={100}
              max={8000}
              step={100}
              value={memoryTokens}
              onChange={(e) => setMemoryTokens(Number(e.target.value))}
            />
          </div>

          <div className="slider-group">
            <label htmlFor="context-slider">
              Context length: <strong>{contextLength.toLocaleString()}</strong> tokens
            </label>
            <input
              id="context-slider"
              type="range"
              min={4096}
              max={131072}
              step={4096}
              value={contextLength}
              onChange={(e) => setContextLength(Number(e.target.value))}
            />
          </div>

          <div className="slider-group">
            <label htmlFor="history-slider">
              Sample history turns: <strong>{historyTurns}</strong>
            </label>
            <input
              id="history-slider"
              type="range"
              min={0}
              max={50}
              step={1}
              value={historyTurns}
              onChange={(e) => setHistoryTurns(Number(e.target.value))}
            />
          </div>

          <button
            className="context-lab-process-btn"
            onClick={handleProcess}
            disabled={loading || !hasChanges}
          >
            {loading ? 'Processing…' : 'Process Preview'}
          </button>
        </div>
      </PageCard>

      {result && (
        <PageCard>
          <div className="context-lab-result">
            <h2>Budget Summary</h2>

            {isOverBudget ? (
              <div className="context-lab-over-budget">
                Static overhead ({result.empty_used.toLocaleString()} tokens) exceeds per-slot
                budget ({result.budget.toLocaleString()} tokens). Reduce Identity or Memory
                budget, or increase Context length.
              </div>
            ) : (
              <>
                <div className="budget-bar-container">
                  <div className="budget-bar">
                    <div
                      className="budget-bar-used"
                      style={{ width: `${budgetPercent}%` }}
                    />
                  </div>
                  <div className="budget-bar-labels">
                    <span>{result.empty_used.toLocaleString()} used</span>
                    <span>{result.budget.toLocaleString()} total</span>
                  </div>
                </div>

                <div className="budget-stats">
                  <div className="budget-stat">
                    <span className="budget-stat-label">Per-turn budget</span>
                    <span className="budget-stat-value">{result.budget.toLocaleString()}</span>
                  </div>
                  <div className="budget-stat">
                    <span className="budget-stat-label">Static overhead</span>
                    <span className="budget-stat-value">{result.empty_used.toLocaleString()}</span>
                  </div>
                  <div className="budget-stat">
                    <span className="budget-stat-label">History remaining</span>
                    <span className="budget-stat-value">
                      {(result.budget - result.empty_used).toLocaleString()}
                    </span>
                  </div>
                  <div className="budget-stat">
                    <span className="budget-stat-label">Sample history</span>
                    <span className="budget-stat-value">
                      {Math.floor(result.history_kept / 2)} /{' '}
                      {Math.floor(result.history_kept / 2) + result.history_truncated} turns
                    </span>
                  </div>
                </div>
              </>
            )}

            <h2>Prompt Layers</h2>
            <div className="prompt-layers">
              {result.layers.map((layer) => (
                <div
                  key={layer.name}
                  className={`prompt-layer ${layer.truncated ? 'prompt-layer--truncated' : ''}`}
                >
                  <button
                    className="prompt-layer-header"
                    onClick={() => toggleLayer(layer.name)}
                    aria-expanded={expandedLayers.has(layer.name)}
                  >
                    <span className="prompt-layer-name">{layer.name}</span>
                    <span className="prompt-layer-meta">
                      {layer.tokens.toLocaleString()} tokens
                      {layer.truncated && ' [TRUNCATED]'}
                    </span>
                    <span className="prompt-layer-toggle">
                      {expandedLayers.has(layer.name) ? '▾' : '▸'}
                    </span>
                  </button>
                  {expandedLayers.has(layer.name) && (
                    <pre className="prompt-layer-text">{layer.text}</pre>
                  )}
                </div>
              ))}
            </div>

            <h2>Assembled System Prompt</h2>
            <div className="assembled-prompt">
              <div className="assembled-prompt-meta">
                {result.assembled_tokens.toLocaleString()} tokens
              </div>
              <pre className="assembled-prompt-text">{result.assembled_system}</pre>
            </div>
          </div>
        </PageCard>
      )}
    </div>
  );
}
