# Workflow Basics

Hestia's workflow system lets you automate multi-step tasks by chaining nodes together on a visual canvas.

## Concepts

A **workflow** is a directed graph of **nodes** connected by **edges**. Each workflow has:
- A **trigger** — the event that starts the workflow
- A **graph** — nodes and edges defining what happens
- **Versions** — saved snapshots of the graph; one version is active at a time

## Triggers

The trigger determines when the workflow runs:

| Trigger | Fires when… |
|---------|-------------|
| **Manual** | You click "Test Run" in the editor |
| **Schedule** | A cron expression matches the current time |
| **Chat Command** | A user sends a message matching a command prefix |
| **Webhook** | An HTTP POST hits the workflow's webhook endpoint |
| **Message** | Any message arrives on a connected platform |
| **Email** | An email matches configured criteria |
| **Proposal** | A proposal is created, accepted, or rejected |
| **Tool Error** | A tool call fails |
| **Workflow Completed** | Another workflow finishes |
| **Session Started** | A new user session begins |

Trigger payload (e.g., the message text, email subject, or webhook body) is available inside nodes via variable interpolation.

## Nodes

| Node | What it does |
|------|--------------|
| **Tool Call** | Executes a Hestia tool (e.g., `terminal`, `read_file`) |
| **LLM Decision** | Asks the model a yes/no question and branches on the answer |
| **Send Message** | Sends a message to a platform user or room |
| **HTTP Request** | Makes an outbound HTTP GET or POST |
| **Condition** | Branches based on a JavaScript expression |
| **Investigate** | Delegates to a subagent for research |
| **Inference** | Runs a raw LLM inference and captures the output |

## Variables

Nodes can reference trigger data and upstream node outputs using `{{data.path}}` syntax:

- `{{data.command}}` — the command string (chat-command trigger)
- `{{data.message}}` — the full message text (message trigger)
- `{{data.email_subject}}` — email subject (email trigger)

The frontend inserts variables automatically when you click a field and select from the variable picker.

## Building a Workflow

1. Go to **Workflows** in the dashboard and click **Create**.
2. Set the trigger type in the top panel.
3. Drag nodes from the left sidebar onto the canvas.
4. Connect nodes by dragging from an output handle to an input handle.
5. Click each node to configure it in the right panel.
6. Click **Save Version** to snapshot the graph.
7. Click **Activate** on a version to make it live.

## Test Runs

Click **Test Run** to execute the workflow manually. The execution result shows:
- Overall status (`ok` or `failed`)
- Per-node status, elapsed time, and token usage
- Node outputs and errors

Use test runs to verify behavior before activating a version.

## Execution History

The **Workflows** list page shows the last execution status and timestamp for each workflow. Open a workflow and view the **Executions** tab for detailed history.

---

## Security Notes

### Webhook Endpoint Uniqueness

Each workflow with a webhook trigger generates a unique secret. If two workflows share the same webhook endpoint URL, a valid request signed with either secret will be accepted and broadcast to **both** workflows. Keep endpoint URLs unique per workflow.
