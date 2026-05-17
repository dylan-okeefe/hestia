import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import NodePropertiesPanel from '../NodePropertiesPanel';
import * as client from '../../../api/client';

vi.mock('../../../api/client', async () => {
  const actual = await vi.importActual<typeof import('../../../api/client')>('../../../api/client');
  return {
    ...actual,
    fetchAuthStatus: vi.fn(),
    fetchUsers: vi.fn(),
    fetchTools: vi.fn(),
  };
});

function makeNode(type: string, data: Record<string, unknown> = {}) {
  return {
    id: 'node_1',
    type,
    position: { x: 0, y: 0 },
    data: { label: 'Test', ...data },
  } as import('reactflow').Node;
}

describe('NodePropertiesPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(client.fetchAuthStatus).mockResolvedValue({
      auth_enabled: true,
      authenticated: true,
      available_platforms: ['matrix', 'telegram'],
    });
    vi.mocked(client.fetchUsers).mockResolvedValue({
      users: [
        { id: 'u1', display_name: 'Alice', role: 'admin', trust_preset: null, notes: null, created_at: '' },
      ],
    });
    vi.mocked(client.fetchTools).mockResolvedValue({
      tools: [
        { name: 'weather', description: 'Get weather', parameters: { properties: { city: { description: 'City name' } } }, requires_confirmation: false, tags: [] },
      ],
    });
  });

  it('renders node type dropdown', () => {
    render(
      <NodePropertiesPanel
        selectedNode={makeNode('send_message', { platform: '', message: '', target_user: '' })}
        nodes={[]}
        edges={[]}
        onDeleteNode={vi.fn()}
        onUpdateNodeData={vi.fn()}
        onChangeNodeType={vi.fn()}
        tools={[]}
        toolSchemas={[]}
        triggerType="manual"
      />
    );
    expect(screen.getByRole('combobox')).toBeInTheDocument();
  });

  it('shows platform and user dropdowns for send_message', async () => {
    render(
      <NodePropertiesPanel
        selectedNode={makeNode('send_message', { platform: '', message: '', target_user: '' })}
        nodes={[]}
        edges={[]}
        onDeleteNode={vi.fn()}
        onUpdateNodeData={vi.fn()}
        onChangeNodeType={vi.fn()}
        tools={[]}
        toolSchemas={[]}
        triggerType="manual"
      />
    );
    await waitFor(() => expect(screen.getAllByRole('combobox').length).toBeGreaterThanOrEqual(2));
    expect(screen.getByText('Which adapter sends the message.')).toBeInTheDocument();
    expect(screen.getByText('The user or room that receives the message.')).toBeInTheDocument();
  });

  it('shows tag chips and add input for llm_decision branches', () => {
    const onUpdate = vi.fn();
    render(
      <NodePropertiesPanel
        selectedNode={makeNode('llm_decision', { prompt: '', branches: ['yes', 'no'] })}
        nodes={[]}
        edges={[]}
        onDeleteNode={vi.fn()}
        onUpdateNodeData={onUpdate}
        onChangeNodeType={vi.fn()}
        tools={[]}
        toolSchemas={[]}
        triggerType="manual"
      />
    );
    expect(screen.getByText('yes')).toBeInTheDocument();
    expect(screen.getByText('no')).toBeInTheDocument();
    const input = screen.getByPlaceholderText(/add branch/i);
    fireEvent.keyDown(input, { key: 'Enter', target: { value: 'maybe' } });
    expect(onUpdate).toHaveBeenCalledWith('branches', ['yes', 'no', 'maybe']);
  });

  it('removes branch chip on click', () => {
    const onUpdate = vi.fn();
    render(
      <NodePropertiesPanel
        selectedNode={makeNode('llm_decision', { prompt: '', branches: ['yes', 'no'] })}
        nodes={[]}
        edges={[]}
        onDeleteNode={vi.fn()}
        onUpdateNodeData={onUpdate}
        onChangeNodeType={vi.fn()}
        tools={[]}
        toolSchemas={[]}
        triggerType="manual"
      />
    );
    fireEvent.click(screen.getByRole('button', { name: /remove branch yes/i }));
    expect(onUpdate).toHaveBeenCalledWith('branches', ['no']);
  });

  it('shows variable picker for message body', async () => {
    const onUpdate = vi.fn();
    render(
      <NodePropertiesPanel
        selectedNode={makeNode('send_message', { platform: '', message: 'hello', target_user: '' })}
        nodes={[]}
        edges={[]}
        onDeleteNode={vi.fn()}
        onUpdateNodeData={onUpdate}
        onChangeNodeType={vi.fn()}
        tools={[]}
        toolSchemas={[]}
        triggerType="chat_command"
      />
    );
    const picker = screen.getByRole('combobox', { name: /insert variable/i });
    expect(picker).toBeInTheDocument();
    fireEvent.change(picker, { target: { value: 'command' } });
    expect(onUpdate).toHaveBeenCalledWith('message', '{data.command}hello');
  });

  it('shows schema-aware args for tool_call when schema available', async () => {
    render(
      <NodePropertiesPanel
        selectedNode={makeNode('tool_call', { tool_name: 'weather', args: { city: 'NYC' } })}
        nodes={[]}
        edges={[]}
        onDeleteNode={vi.fn()}
        onUpdateNodeData={vi.fn()}
        onChangeNodeType={vi.fn()}
        tools={['weather']}
        toolSchemas={[
          { name: 'weather', description: 'Get weather', parameters: { properties: { city: { description: 'City name' } } }, requires_confirmation: false, tags: [] },
        ]}
        triggerType="manual"
      />
    );
    await waitFor(() => expect(screen.getByDisplayValue('NYC')).toBeInTheDocument());
    expect(screen.getByText('City name')).toBeInTheDocument();
  });

  it('falls back to json textarea when no schema', () => {
    render(
      <NodePropertiesPanel
        selectedNode={makeNode('tool_call', { tool_name: 'weather', args: {} })}
        nodes={[]}
        edges={[]}
        onDeleteNode={vi.fn()}
        onUpdateNodeData={vi.fn()}
        onChangeNodeType={vi.fn()}
        tools={['weather']}
        toolSchemas={[]}
        triggerType="manual"
      />
    );
    expect(screen.getByPlaceholderText('{"query": "example"}')).toBeInTheDocument();
  });
});
