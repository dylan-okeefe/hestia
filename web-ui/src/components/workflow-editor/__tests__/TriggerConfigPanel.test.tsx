import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import TriggerConfigPanel from '../TriggerConfigPanel';
import * as client from '../../../api/client';

vi.mock('../../../api/client', async () => {
  const actual = await vi.importActual<typeof import('../../../api/client')>('../../../api/client');
  return {
    ...actual,
    fetchTools: vi.fn(),
  };
});

describe('TriggerConfigPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(client.fetchTools).mockResolvedValue({
      tools: [
        { name: 'weather', description: 'Get weather', parameters: {}, requires_confirmation: false, tags: [] },
        { name: 'remind', description: 'Set reminder', parameters: {}, requires_confirmation: false, tags: [] },
      ],
    });
  });

  it('renders trigger type dropdown with labels', () => {
    render(
      <TriggerConfigPanel
        triggerType="manual"
        onTriggerTypeChange={vi.fn()}
        triggerConfig={{}}
        onTriggerConfigChange={vi.fn()}
        onSaveTrigger={vi.fn()}
        triggerSaving={false}
        workflowId="wf-1"
        webhookUrl=""
        webhookSecret="secret"
      />
    );
    expect(screen.getByRole('combobox')).toBeInTheDocument();
    expect(screen.getByText('Manual')).toBeInTheDocument();
  });

  it('shows cron builder for schedule trigger', () => {
    render(
      <TriggerConfigPanel
        triggerType="schedule"
        onTriggerTypeChange={vi.fn()}
        triggerConfig={{ cron: '0 8 * * *' }}
        onTriggerConfigChange={vi.fn()}
        onSaveTrigger={vi.fn()}
        triggerSaving={false}
        workflowId="wf-1"
        webhookUrl=""
        webhookSecret="secret"
      />
    );
    expect(screen.getByRole('button', { name: /hourly/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /daily/i })).toBeInTheDocument();
  });

  it('shows tool dropdown for tool_error trigger', async () => {
    render(
      <TriggerConfigPanel
        triggerType="tool_error"
        onTriggerTypeChange={vi.fn()}
        triggerConfig={{}}
        onTriggerConfigChange={vi.fn()}
        onSaveTrigger={vi.fn()}
        triggerSaving={false}
        workflowId="wf-1"
        webhookUrl=""
        webhookSecret="secret"
      />
    );
    await waitFor(() => expect(screen.getByRole('combobox')).toBeInTheDocument());
    expect(screen.getByText('— Any —')).toBeInTheDocument();
    expect(screen.getByText('weather')).toBeInTheDocument();
  });

  it('shows chat command placeholder and helper', () => {
    render(
      <TriggerConfigPanel
        triggerType="chat_command"
        onTriggerTypeChange={vi.fn()}
        triggerConfig={{}}
        onTriggerConfigChange={vi.fn()}
        onSaveTrigger={vi.fn()}
        triggerSaving={false}
        workflowId="wf-1"
        webhookUrl=""
        webhookSecret="secret"
      />
    );
    expect(screen.getByPlaceholderText(/e\.g\. weather, remind, status/i)).toBeInTheDocument();
    expect(screen.getByText(/the word users type to activate this workflow/i)).toBeInTheDocument();
  });

  it('shows available variables for trigger type', () => {
    render(
      <TriggerConfigPanel
        triggerType="chat_command"
        onTriggerTypeChange={vi.fn()}
        triggerConfig={{}}
        onTriggerConfigChange={vi.fn()}
        onSaveTrigger={vi.fn()}
        triggerSaving={false}
        workflowId="wf-1"
        webhookUrl=""
        webhookSecret="secret"
      />
    );
    expect(screen.getByText(/available variables/i)).toBeInTheDocument();
    expect(screen.getByText(/{data.command}/i)).toBeInTheDocument();
  });

  it('opens and closes help modal', () => {
    render(
      <TriggerConfigPanel
        triggerType="manual"
        onTriggerTypeChange={vi.fn()}
        triggerConfig={{}}
        onTriggerConfigChange={vi.fn()}
        onSaveTrigger={vi.fn()}
        triggerSaving={false}
        workflowId="wf-1"
        webhookUrl=""
        webhookSecret="secret"
      />
    );
    fireEvent.click(screen.getByRole('button', { name: /show help/i }));
    expect(screen.getByText(/workflow editor help/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /close/i }));
    expect(screen.queryByText(/workflow editor help/i)).not.toBeInTheDocument();
  });
});
