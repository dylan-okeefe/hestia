import { Page } from '@playwright/test';

export const mockSessions = {
  sessions: [
    {
      id: 'sess_001',
      platform: 'cli',
      platform_user: 'alice',
      started_at: '2024-01-15T10:00:00Z',
      state: 'ACTIVE',
      temperature: 'COLD',
    },
  ],
};

export const mockTurns = {
  turns: [
    {
      id: 'turn_001',
      state: 'COMPLETED',
      started_at: '2024-01-15T10:05:00Z',
      iterations: 3,
      error: null,
    },
  ],
};

export const mockProposals = {
  proposals: [
    {
      id: 'prop_001',
      type: 'identity_update',
      summary: 'Add greeting preference',
      confidence: 0.9,
      evidence: ['turn_1'],
      action: { file: 'SOUL.md', append: '- Greeting: casual' },
      status: 'pending',
      created_at: '2024-01-15T10:00:00Z',
      expires_at: '2024-01-29T10:00:00Z',
      reviewed_at: null,
      review_note: null,
    },
    {
      id: 'prop_002',
      type: 'style_update',
      summary: 'Increase formality',
      confidence: 0.75,
      evidence: [],
      action: {},
      status: 'accepted',
      created_at: '2024-01-14T10:00:00Z',
      expires_at: '2024-01-28T10:00:00Z',
      reviewed_at: '2024-01-15T10:00:00Z',
      review_note: 'Looks good',
    },
  ],
};

export const mockStyleProfile = {
  profile: {
    formality: 0.8,
    preferred_length: 150,
  },
};

export const mockTasks = {
  tasks: [
    {
      id: 'task_001',
      description: 'Daily summary',
      prompt: 'Summarize today\'s activity',
      cron_expression: '0 9 * * *',
      last_run_at: '2024-01-15T09:00:00Z',
      next_run_at: '2024-01-16T09:00:00Z',
      last_error: null,
      enabled: true,
      notify: false,
    },
  ],
};

export const mockDoctor = {
  checks: [
    { name: 'Database', ok: true, detail: 'Connected' },
    { name: 'Inference', ok: true, detail: 'llama-server responsive' },
  ],
};

export const mockAudit = {
  findings: [
    { severity: 'info', category: 'general', message: 'All clear', details: {} },
  ],
};

export const mockEgress = {
  events: [
    {
      id: 'eg_001',
      url: 'https://api.example.com/data',
      domain: 'api.example.com',
      status: 200,
      size: 1024,
      created_at: '2024-01-15T10:00:00Z',
    },
  ],
};

export const mockConfig = {
  inference: { base_url: 'http://127.0.0.1:8001', model_name: 'test' },
  trust: { preset: 'developer' },
  web: { enabled: true, host: '127.0.0.1', port: 8765 },
};

export const mockConfigSchema = {
  schema: {
    'trust.preset': {
      type: 'enum',
      values: ['paranoid', 'prompt_on_mobile', 'household', 'developer'],
      default: 'developer',
    },
  },
};

export const mockWorkflows = {
  workflows: [
    {
      id: 'wf_001',
      name: 'Morning Greeting',
      trigger_type: 'cron',
      last_edited_at: '2024-01-15T08:00:00Z',
      active_version_id: 'v_001',
    },
    {
      id: 'wf_002',
      name: 'Daily Summary',
      trigger_type: 'manual',
      last_edited_at: '2024-01-14T10:00:00Z',
      active_version_id: null,
    },
  ],
};

export const mockWorkflowVersions = {
  versions: [
    {
      id: 'v_001',
      workflow_id: 'wf_001',
      version_number: 1,
      nodes: [
        { id: 'n1', type: 'default', position: { x: 100, y: 100 }, data: { label: 'Start' } },
        { id: 'n2', type: 'default', position: { x: 250, y: 100 }, data: { label: 'End' } },
      ],
      edges: [{ id: 'e1', source: 'n1', target: 'n2' }],
      created_at: '2024-01-15T08:00:00Z',
      activated_at: '2024-01-15T08:05:00Z',
    },
  ],
};

export const mockExecutions = {
  executions: [
    {
      id: 'ex_001',
      workflow_id: 'wf_001',
      version: 1,
      status: 'ok',
      trigger_payload: {},
      node_results: [
        {
          node_id: 'n1',
          status: 'ok',
          elapsed_ms: 500,
          prompt_tokens: 100,
          completion_tokens: 50,
          output: 'hello',
          error: null,
        },
      ],
      total_elapsed_ms: 1234,
      total_prompt_tokens: 150,
      total_completion_tokens: 80,
      created_at: '2024-01-15T08:00:00Z',
    },
    {
      id: 'ex_002',
      workflow_id: 'wf_001',
      version: 1,
      status: 'failed',
      trigger_payload: {},
      node_results: [
        {
          node_id: 'n1',
          status: 'failed',
          elapsed_ms: 100,
          prompt_tokens: 0,
          completion_tokens: 0,
          output: null,
          error: 'Node failed',
        },
      ],
      total_elapsed_ms: 100,
      total_prompt_tokens: 0,
      total_completion_tokens: 0,
      created_at: '2024-01-15T07:00:00Z',
    },
  ],
};

export async function mockApis(page: Page) {
  await page.route('/api/sessions**', async (route) => {
    const url = route.request().url();
    if (url.includes('/turns')) {
      await route.fulfill({ json: mockTurns });
    } else {
      await route.fulfill({ json: mockSessions });
    }
  });

  await page.route('/api/proposals**', async (route) => {
    const method = route.request().method();
    if (method === 'POST') {
      await route.fulfill({ json: { id: 'prop_001', status: 'accepted' } });
    } else {
      await route.fulfill({ json: mockProposals });
    }
  });

  await page.route('/api/style/**', async (route) => {
    const method = route.request().method();
    if (method === 'DELETE') {
      await route.fulfill({ json: { deleted: true } });
    } else {
      await route.fulfill({ json: mockStyleProfile });
    }
  });

  await page.route('/api/scheduler/tasks**', async (route) => {
    const method = route.request().method();
    if (method === 'POST') {
      await route.fulfill({ json: { id: 'task_001', triggered: true } });
    } else {
      await route.fulfill({ json: mockTasks });
    }
  });

  await page.route('/api/doctor', async (route) => {
    await route.fulfill({ json: mockDoctor });
  });

  await page.route('/api/audit', async (route) => {
    await route.fulfill({ json: mockAudit });
  });

  await page.route('/api/egress**', async (route) => {
    await route.fulfill({ json: mockEgress });
  });

  await page.route('/api/auth/status', async (route) => {
    await route.fulfill({ json: { auth_enabled: false, authenticated: false } });
  });

  await page.route('/api/config/schema', async (route) => {
    await route.fulfill({ json: mockConfigSchema });
  });

  await page.route('/api/config', async (route) => {
    const method = route.request().method();
    if (method === 'PUT') {
      await route.fulfill({ status: 501, json: { detail: 'Not implemented' } });
    } else {
      await route.fulfill({ json: mockConfig });
    }
  });

  await page.route('/api/workflows', async (route) => {
    const method = route.request().method();
    if (method === 'POST') {
      await route.fulfill({ json: { id: 'wf_003', name: 'New Workflow', trigger_type: 'manual', last_edited_at: new Date().toISOString(), active_version_id: null } });
    } else {
      await route.fulfill({ json: mockWorkflows });
    }
  });

  await page.route('/api/workflows/**', async (route) => {
    const url = route.request().url();
    const method = route.request().method();
    if (url.includes('/versions')) {
      if (method === 'POST') {
        await route.fulfill({ json: { id: 'v_002', workflow_id: 'wf_001', version_number: 2, nodes: [], edges: [], created_at: new Date().toISOString(), activated_at: null } });
      } else if (url.includes('/activate')) {
        await route.fulfill({ json: { activated: true } });
      } else {
        await route.fulfill({ json: mockWorkflowVersions });
      }
    } else if (url.includes('/executions')) {
      await route.fulfill({ json: mockExecutions });
    } else if (url.includes('/test-run')) {
      await route.fulfill({ json: { status: 'ok', total_elapsed_ms: 0, total_prompt_tokens: 0, total_completion_tokens: 0, node_results: [], outputs: {} } });
    } else if (method === 'DELETE') {
      await route.fulfill({ json: { deleted: true } });
    } else if (method === 'PUT') {
      const body = await route.request().postDataJSON();
      await route.fulfill({ json: { ...mockWorkflows.workflows[0], ...body } });
    } else {
      await route.fulfill({ json: mockWorkflows.workflows[0] });
    }
  });
}
