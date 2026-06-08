# Web Dashboard Quickstart

Hestia ships a React-based web dashboard for administration and monitoring. It runs on the same port as the API (default `8765`) and is served as a static SPA.

## Access

Open `http://<host>:<port>` in your browser. If authentication is enabled, you will be redirected to the login page.

## Login

1. Select your user from the list (if multiple users exist).
2. Choose your platform (Telegram or Matrix).
3. Hestia sends a one-time code to your chat platform.
4. Enter the code to complete login.

For local development, set `web.debug_login=True` in your config to skip code
verification — selecting a user logs you in immediately.

The first admin is assigned by running `hestia migrate-users` (users in the legacy config with `is_admin=True` are promoted). Subsequent users receive the `user` role by default.

## Pages

### Dashboard
Overview of the system: active workflow count, recent executions, pending proposals, and connected platforms.

### Sessions
Browse active and archived chat sessions. View per-session turn history,
messages, and metadata. Telegram group chats display their title.

### Proposals
Review agent-generated proposals. Accept, reject, or defer each proposal with an optional reason.

### Style
Manage style profiles that influence how Hestia responds to you.

### Scheduler
View and manage scheduled tasks. Create new tasks with cron expressions, enable/disable existing ones, or trigger a task to run immediately.

### Security & Health
Run health checks (`hestia doctor` equivalent) and view security status.

### Config
View the current configuration. **Read-only** — edit `config.py` directly and restart the server to apply changes.

### Workflows
List all workflows. Click a workflow to open the visual editor.

In the editor:
- Drag nodes from the sidebar onto the canvas.
- Connect nodes by dragging from an output handle to an input handle.
- Click a node to configure it in the properties panel.
- Set the trigger type and config in the top panel.
- Save versions and activate one to make it live.
- Use **Test Run** to execute the workflow manually.
- Inspect execution history with per-node output drill-down.

### Browser Sessions *(admin only)*
Manage persistent browser sessions per-domain. Stream a headless or headed
browser to authenticate with JavaScript-heavy sites, run health checks, and
delete stale sessions.

### Profile
View your user profile and knowledge base entries.

### Knowledge
Search memory entries and browse session history.

### Errors *(admin only)*
View persisted errors with filtering and stack-trace inspection.

### Users *(admin only)*
List all registered users and their roles.

## Dark Mode

Click the moon/sun icon in the top-right corner to toggle dark mode. The dashboard respects your system preference on first load.

## Mobile

The dashboard is fully responsive. On small screens:
- The sidebar collapses into a hamburger menu.
- Tables scroll horizontally.
- Form inputs stack vertically.
