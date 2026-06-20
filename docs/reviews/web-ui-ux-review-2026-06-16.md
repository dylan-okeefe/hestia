# Web UI UX Review — 2026-06-16

**Method:** Read-only walkthrough of all 13 nav routes on the live runtime
instance, via the browser extension. Navigation and screenshots only; no actions
were triggered (real account/data). Where a finding depends on triggering an
action (e.g. loading states), it is inferred from the static UI plus the prior
code review and marked as such.

## Overall

Much more coherent as a product than the code-only review implied. The dark
theme is consistent across every page, empty states are thoughtful (Proposals,
Style, Knowledge each explain what will appear and why), status dots and badges
(roles, trigger types, severity) are used well, and the newer pages are
genuinely polished. Security & Health, Errors, Users, Scheduler, and Browser
Sessions are reference-quality. The earlier "three products stitched together"
feeling is mostly gone.

Already fixed since the last review: the dashboard "Recent Sessions" mislabel now
correctly reads "Recent Executions," and Context Lab is reachable. The Security
page also correctly flags "Trust Preset Safe for Production" as failing, i.e. the
dev-trust posture surfacing as intended.

## Prioritized summary

1. Fix the three real bugs the walkthrough surfaced (below). These are not
   cosmetic.
2. Humanize raw IDs app-wide. Biggest single UX lift.
3. Add loading states to every async action.
4. Targeted per-page fixes (error timestamps, sortable browser columns, scheduler
   row verbosity, workflow Edit affordance, dashboard health, etc.).

## Real bugs surfaced (highest value)

- **Recurring `'list' object has no attribute 'get'`** across multiple sessions
  on the Errors page. A live AttributeError, not a model issue. Worth chasing.
  Alongside it: `max attempts exceeded`, `POST /v1/chat/completions timed out`,
  and `Degenerate pattern persisted after 3 corrections: read_only_streak`. 50
  unresolved errors total.
- **Matrix room IDs appearing as user records** on the Users page
  (`!JobaAjDMsxsiOaenRV:matrix.org`, `!FlnJLehKjOiKBdEmTn:matrix.org`), and one
  carries the **Administrator** role. This is the room auto-registration risk
  ADR-039 flagged, leaking rooms into the users table; a room with admin role is
  a real concern.
- **Raw tool-call XML stored as memories** on the Knowledge page (e.g.
  `<tool_call><function=read_file>...`), mixed in with the good clean summaries.
  Memory capture should filter tool-call/assistant turns before they become
  "memories."

## Raw IDs everywhere (top UX theme)

Opaque machine identifiers are shown where a human label belongs:
- Dashboard Recent Executions and Workflows "Active Version" show full UUIDs.
- Profile "Rooms" and Knowledge sessions show raw Telegram/Matrix room IDs.
- Errors "Source" shows long raw session IDs.
- Style/Profile show the raw numeric Telegram user ID.

Use friendly labels (workflow name instead of version UUID, room alias, short id
with full on hover) and the whole app gets easier to scan.

## Loading states (all async actions)

No in-flight feedback today, so a slow operation is indistinguishable from a dead
one, and on local hardware these are genuinely slow. Apply loading state
(disable + spinner, plus a result toast) to: Check Now and Stream (Browser),
Run Health Check / Re-run checks / Run audit (Security), Process Preview
(Context Lab), Run now (Scheduler), Save Notes (Profile/Knowledge). The Button
component already has a loading variant that is barely adopted, so this is mostly
an adoption pass, not new infrastructure.

## Cross-page inconsistency

Dashboard "System Health: Unknown" contradicts Security & Health's "83% passing
(10/12)" computed from real data. The dashboard widget is stale/lazy; it should
reflect the actual health status.

## Per-page findings

- **Errors:** no timestamp column at all (only Type/Source/Message). Add a
  timestamp and default-sort newest-first. Source IDs are raw and hard to scan.
- **Browser Sessions:** static headers, no sorting; the table is long (a couple
  dozen domains past the fold). Add sortable columns (Last Used, Last Checked,
  Status, Cookies) and filtering. The "Headed" checkbox column has no label/
  explanation.
- **Scheduler:** task rows dump the entire prompt as the description (walls of
  text). Use a short title with expand-on-click. Disabled tasks show a past
  "Next Run" date (April); show "—" or "Disabled" instead.
- **Workflows:** the Actions column only has Delete; there is no visible Edit/
  Open affordance, so opening the editor is hidden behind a row click. One
  workflow is named "New Workflow," confusing next to the "New Workflow" button.
- **Security & Health:** the "Audit Findings" header is duplicated.
- **Context Lab:** functional and reachable, but sparse; no explanation of what
  each budget does or what "Process Preview" produces until clicked.
- **Knowledge:** session titles are all empty ("—").

## Navigation

Flat 13-item list with no grouping. At this length it reads better grouped, e.g.
Activity / Automation / Account / System / Admin.

## Suggested implementation split

- **UX-polish loop:** raw-ID humanization, loading states, error timestamp +
  sort, browser sortable columns + filter, dashboard health, scheduler row
  verbosity + stale next-run, workflow Edit affordance, duplicate audit header,
  Context Lab guidance, empty session titles, nav grouping.
- **Bug-fix loop:** recurring `'list'.get` AttributeError, Matrix-rooms-as-users
  (and one as admin), raw tool-call XML stored as memories.
