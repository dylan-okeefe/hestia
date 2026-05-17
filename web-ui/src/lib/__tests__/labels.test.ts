import { describe, it, expect } from 'vitest';
import { TRIGGER_LABELS, NODE_TYPE_LABELS, HEALTH_CHECK_LABELS, ROLE_LABELS, TRUST_PRESET_LABELS, label } from '../labels';

describe('label helper', () => {
  it('returns mapped label for known trigger key', () => {
    expect(label(TRIGGER_LABELS, 'chat_command')).toBe('Chat Command');
  });

  it('returns key itself for unknown value', () => {
    expect(label(TRIGGER_LABELS, 'unknown_trigger')).toBe('unknown_trigger');
  });

  it('returns mapped label for known health check', () => {
    expect(label(HEALTH_CHECK_LABELS, 'python_version')).toBe('Python Version');
  });

  it('returns mapped label for known role', () => {
    expect(label(ROLE_LABELS, 'admin')).toBe('Administrator');
  });

  it('returns mapped label for known trust preset', () => {
    expect(label(TRUST_PRESET_LABELS, 'prompt_on_mobile')).toBe('Prompt on Mobile');
  });

  it('returns mapped label for known node type', () => {
    expect(label(NODE_TYPE_LABELS, 'llm_decision')).toBe('LLM Decision');
  });
});
