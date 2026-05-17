# L172 — OpenUI Foundation & Shared Components

**Status:** Spec only  
**Branch:** `feature/l172-openui-foundation` (from `feature/l169-user-registry`)  
**Depends on:** L169 (user registry implementation on branch); L170 and L171 recommended for clean data layer

## Intent

The L169 branch built ten dashboard pages with raw HTML, inline styles, and no shared component library. The result is inconsistent spacing, typography, and color systems; every page rediscovers the same styling decisions. More importantly, the UI exposes raw code identifiers (`chat_command`, `tool_error`, `python_version`) as user-facing labels, uses free-text inputs where dropdowns belong, and provides zero contextual help. These are systemic issues that cannot be fixed page-by-page — they require shared infrastructure.

The existing ADR deferred OpenUI adoption, but that ADR was written before the user registry existed. Now that there is a user model, the UI needs to be user-aware throughout: session-based data fetching, role-based visibility, and consistent form patterns. Retrofitting this into ad-hoc pages is more work than starting from shared components.

This loop establishes the OpenUI framework and the shared layers (display names, data-bound inputs, layout primitives) so that subsequent loops (L173–L175) can rebuild pages quickly and consistently.

## Scope

### §0 — Install and configure OpenUI

**Why:** Without a component framework, every page invents its own buttons, inputs, and cards. OpenUI provides Zod-schema typed components that enforce consistent structure and reduce boilerplate.

In `web-ui/`:

1. `npm install @openuidev/react-ui`
2. Add OpenUI provider to `web-ui/src/main.tsx` (or `App.tsx`) wrapping the router:
   ```tsx
   import { OpenUIProvider } from "@openuidev/react-ui";
   
   <OpenUIProvider>
     <RouterProvider router={router} />
   </OpenUIProvider>
   ```
3. Configure the theme object with Hestia's color palette (derive from Config page's existing card styling):
   - Primary: indigo/slate blue used in trust preset cards
   - Danger: red for destructive actions
   - Surface: neutral grays for backgrounds
   - Font stack: system-ui, sans-serif
4. Verify the build still passes: `npm run build`.

**Commit:** `feat(web-ui): install and configure OpenUI component framework`

### §1 — Display-name mapping layer

**Why:** Users should never see `snake_case`, `camelCase`, or internal enum values. A centralized mapping layer ensures every identifier gets a human-readable label, and adding a new trigger type or health check only requires one dictionary entry.

In `web-ui/src/lib/labels.ts`:

1. Define mapping dictionaries:
   ```typescript
   export const TRIGGER_LABELS: Record<string, string> = {
     chat_command: "Chat Command",
     proposal_approved: "Proposal Approved",
     tool_error: "Tool Error",
     workflow_completed: "Workflow Completed",
     session_started: "Session Started",
     schedule: "Scheduled",
     webhook: "Webhook",
     email_received: "Email Received",
     // ... all trigger types
   };
   
   export const NODE_TYPE_LABELS: Record<string, string> = {
     send_message: "Send Message",
     tool_call: "Tool Call",
     llm_decision: "LLM Decision",
     condition: "Condition",
     investigate: "Investigate",
     // ... all node types
   };
   
   export const HEALTH_CHECK_LABELS: Record<string, string> = {
     python_version: "Python Version",
     dependencies_in_sync: "Dependencies in Sync",
     config_file_loads: "Config File Loads",
     // ... all health checks
   };
   
   export const ROLE_LABELS: Record<string, string> = {
     admin: "Administrator",
     trusted: "Trusted User",
     user: "User",
     child: "Child",
   };
   
   export const TRUST_PRESET_LABELS: Record<string, string> = {
     paranoid: "Paranoid",
     prompt_on_mobile: "Prompt on Mobile",
     household: "Household",
     developer: "Developer",
   };
   ```
2. Export a helper:
   ```typescript
   export function label(map: Record<string, string>, key: string): string {
     return map[key] ?? key;
   }
   ```
3. Use the helper in one existing page (e.g. Security & Health) as a proof of concept.

**Commit:** `feat(web-ui): centralized display-name mapping layer for all code identifiers`

### §2 — Shared data-bound form components

**Why:** Free-text inputs for known values (platforms, users, tools, trigger types) are bugs — they shift validation burden to the user, invite typos, and provide no discoverability. A shared set of dropdowns and multi-selects that fetch from backend endpoints solves this everywhere.

In `web-ui/src/components/forms/`:

1. **PlatformDropdown** — fetches from `GET /api/platforms` (or reuse `available_platforms` from auth status). Renders `<select>` with display names. Props: `value`, `onChange`, `includeEmpty?: boolean`.
2. **UserDropdown** — fetches from `GET /api/users`. Renders users by `display_name`. Props: `value`, `onChange`.
3. **ToolDropdown** — fetches from `GET /api/tools`. Renders tool names with display labels if available. Props: `value`, `onChange`, `includeAny?: boolean`.
4. **TriggerTypeDropdown** — static options from `TRIGGER_LABELS`. Props: `value`, `onChange`.
5. **NodeTypeDropdown** — static options from `NODE_TYPE_LABELS`. Props: `value`, `onChange`.
6. **RoleDropdown** — static options from `ROLE_LABELS`. Props: `value`, `onChange`, `disabledRoles?: string[]`.
7. **TrustPresetDropdown** — static options from `TRUST_PRESET_LABELS`. Props: `value`, `onChange`.
8. Each component handles its own loading and error states (spinner or "Failed to load" with retry).

**Commit:** `feat(web-ui): shared data-bound dropdown components for platforms, users, tools, roles, and presets`

### §3 — Shared layout primitives

**Why:** The nav bar scrolls off-screen on long pages, each page uses different card spacing, and there is no consistent empty-state pattern. Layout primitives enforce baseline expectations.

In `web-ui/src/components/layout/`:

1. **StickyNav** — wrap the existing navigation bar in a component with `position: sticky; top: 0; z-index: 50; background: white; border-bottom: 1px solid ...`. Use in `App.tsx` so it applies globally.
2. **PageCard** — a container with consistent padding, border radius, shadow, and background. Used by Config's trust preset cards; extract and generalize.
3. **EmptyState** — accepts `title`, `description`, and optional `action` (button + callback). Rendered when a list or table has no data.
   ```tsx
   <EmptyState
     title="No memories yet"
     description="Hestia learns about you during conversations. Start chatting to build your knowledge profile."
     action={{ label: "Start a conversation", onClick: ... }}
   />
   ```
4. **LoadingSkeleton** — a pulsing placeholder for async content areas.
5. **ErrorState** — accepts `message` and `onRetry`. Rendered when a fetch fails.

**Commit:** `feat(web-ui): shared layout primitives — sticky nav, cards, empty states, loading and error boundaries`

### §4 — Shared data-fetching hooks with state handling

**Why:** Multiple pages show "Loading..." forever, stale data, or blank screens on error because they lack explicit async state handling. A shared hook enforces the three required states: loading, success, and error.

In `web-ui/src/hooks/useApi.ts`:

1. Create `useApiQuery<T>(key, fetcher)` that wraps `useQuery` and returns:
   ```typescript
   {
     data: T | undefined;
     isLoading: boolean;
     isError: boolean;
     error: Error | null;
     refetch: () => void;
   }
   ```
2. Create `useApiMutation<TInput, TOutput>(mutator)` for POST/PUT/DELETE with `isPending`, `error`, and `mutateAsync`.
3. Both hooks log errors to the console (and eventually to an error boundary).
4. Update at least one existing page (Profile or Knowledge) to use these hooks as proof of concept.

**Commit:** `feat(web-ui): shared async data hooks with explicit loading, error, and retry states`

### §5 — Date, cron, and JSON display helpers

**Why:** Raw cron expressions (`0 9,10,11... * * *`), ISO timestamps, and JSON blobs are developer representations. End users need natural-language equivalents.

In `web-ui/src/lib/format.ts`:

1. `formatDate(isoString: string | null): string` — uses `Intl.DateTimeFormat` with `dateStyle: "medium", timeStyle: "short"`.
2. `formatRelativeDate(isoString: string): string` — "2 hours ago", "Yesterday at 3 PM".
3. `formatCron(cron: string): string` — uses `cronstrue` if available, otherwise a simple parser. Falls back to the raw string.
4. `formatJson(obj: unknown): string` — pretty-prints with 2-space indentation for read-only display.
5. `formatDuration(seconds: number): string` — "3 minutes", "1.5 hours".

**Commit:** `feat(web-ui): natural-language formatters for dates, cron, and JSON`

### §6 — Tests

1. **Label helper test:** `label(TRIGGER_LABELS, "chat_command")` returns `"Chat Command"`. Unknown key returns the key itself.
2. **Dropdown component tests:** Mock backend endpoint. Assert PlatformDropdown renders options. Assert selecting an option fires `onChange` with the correct value.
3. **Layout primitive tests:** EmptyState renders title and description. ErrorState renders message and retry button.
4. **Format helper tests:** `formatDate("2026-05-17T10:30:00Z")` returns a localized string. `formatCron("0 9 * * 1")` returns a human-readable description.

**Commit:** `test(web-ui): shared component and formatter unit tests`

## Evaluation

- OpenUI is installed, configured, and renders without build errors
- Every code identifier rendered in the UI passes through the display-name mapping layer
- Dropdown components for platforms, users, tools, roles, and trust presets exist and fetch from backend data
- Sticky navigation is applied globally and remains visible on scroll
- Empty states, loading skeletons, and error boundaries are available as shared components
- Date/cron/JSON formatters produce human-readable output

## Acceptance

- `npm run build` in `web-ui/` completes without errors
- Frontend tests pass
- At least one existing page (Security & Health or Config) uses the new label mapping to prove integration
- `ruff check src/ tests/` clean on any backend changes
- `.kimi-done` includes `LOOP=L172`
