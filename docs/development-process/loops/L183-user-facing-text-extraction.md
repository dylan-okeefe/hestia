# L183 — User-Facing Text Extraction

**Status:** Spec only  
**Branch:** `feature/l183-text-extraction` (from `feature/l179-rooms-interactive-nodes`)  
**Depends on:** L176–L179

## Intent

User-facing text is scattered across 15+ page components and dozens of shared components. Empty state titles, descriptions, button labels, helper text, placeholder text, error messages, modal copy, tooltip text, and confirmation dialogs are all hardcoded inline. This makes:
- Copy editing painful (hunt through 30+ files to change one message)
- Translation impossible (no central catalog)
- Inconsistency inevitable ("No users found" vs "No users available" vs "No users configured")
- Testing harder (assertions depend on literal strings spread across files)

The audit found ~64 distinct user-facing strings in pages alone, with 40+ more in components. This loop extracts all of them into a structured constant file.

## Scope

### §0 — Create text catalog structure

**Why:** We need a single source of truth for all user-facing strings.

In `web-ui/src/lib/text.ts`:

1. Create a hierarchical catalog organized by feature area:
   ```typescript
   export const TEXT = {
     common: {
       loading: 'Loading…',
       error: 'Something went wrong.',
       retry: 'Retry',
       save: 'Save',
       cancel: 'Cancel',
       delete: 'Delete',
       confirm: 'Confirm',
       close: 'Close',
       back: 'Back',
       edit: 'Edit',
       create: 'Create',
       search: 'Search',
       filter: 'Filter',
       clear: 'Clear',
       none: 'None',
       unknown: 'Unknown',
     },
     login: {
       title: 'Sign in to Hestia',
       step1Title: 'Who are you?',
       step1Description: 'Select your account to continue.',
       step2Title: 'Verify via…',
       step2Description: 'Choose where to receive your verification code.',
       step3Title: 'Enter code',
       step3Description: 'Enter the 6-digit code sent to your device.',
       codePlaceholder: '000000',
       resend: 'Resend code',
       verify: 'Verify',
       noUsersTitle: 'No users available',
       noUsersDescription: 'No users configured. Contact your admin.',
       noPlatformsTitle: 'No platforms available',
       noPlatformsDescription: 'No platforms configured for this user.',
     },
     profile: {
       title: 'Profile',
       displayNameLabel: 'Display Name',
       displayNamePlaceholder: 'Your name',
       roleLabel: 'Role',
       trustOverrideLabel: 'Personal trust override',
       trustOverrideHelper: (global: string) =>
         `Overrides the global trust level (currently: ${global}).`,
       trustUsingGlobal: (global: string) =>
         `Using global trust level: ${global}. Select a preset to override.`,
       effectiveTrustLabel: 'Effective trust level',
       notesLabel: 'Notes',
       notesPlaceholder: 'Facts about you that Hestia sees…',
       notesHelper: 'These notes are injected into Hestia\'s system prompt.',
       identitiesTitle: 'Connected Identities',
       identitiesEmpty: 'No identities connected.',
       addIdentityTitle: 'Add Identity',
       addIdentityPlatformLabel: 'Platform',
       addIdentityUserLabel: 'Platform User ID',
       roomsTitle: 'Rooms',
       roomsEmpty: 'No rooms yet. Telegram and Matrix group chats are registered automatically when a message is received. Run `hestia migrate-users` to register existing groups.',
       saveError: (msg: string) => `Failed to save: ${msg}`,
     },
     knowledge: {
       title: 'What Hestia Knows About You',
       memoriesTitle: 'Memories',
       memoriesDescription: 'Session summaries and notes from your conversations with Hestia.',
       memoriesEmpty: 'No memories yet — Hestia learns about you during conversations.',
       memoriesDeleteConfirm: 'Remove this memory? Hestia will forget this fact.',
       styleTitle: 'Style Profile',
       styleEmpty: 'No style metrics for this identity yet. Hestia builds a style profile over time.',
       sessionsTitle: 'Session History',
       sessionsEmpty: 'No recent sessions.',
       handoffsTitle: 'Handoff Summaries',
       handoffsDescription: 'What Hestia remembers from your last few sessions.',
       handoffsEmpty: 'No handoff summaries yet — these appear when Hestia carries context across sessions.',
       notesTitle: 'Your Notes',
       notesDescription: 'Edit your notes on the Profile page.',
       tagFilterShowing: (count: number, total: number) =>
         `Showing ${count} of ${total} memories`,
       tagFilterClear: 'Clear filters',
     },
     scheduler: {
       title: 'Scheduled Tasks',
       createButton: 'New Task',
       createTitle: 'Create Scheduled Task',
       editTitle: 'Edit Scheduled Task',
       nameLabel: 'Task Name',
       namePlaceholder: 'Daily weather check',
       promptLabel: 'Prompt / URL',
       promptPlaceholder: 'https://example.com or prompt text',
       cronLabel: 'Schedule (cron)',
       enabledLabel: 'Enabled',
       runNow: 'Run now',
       runNowConfirm: 'Run this task immediately?',
       deleteConfirm: 'Delete this scheduled task? This cannot be undone.',
       emptyTitle: 'No scheduled tasks',
       emptyDescription: 'Create one to run checks, fetch data, or send messages on a schedule.',
     },
     adminUsers: {
       title: 'User Management',
       accessDenied: 'Administrator access required.',
       createButton: 'New User',
       createTitle: 'Create User',
       editTitle: 'Edit User',
       deleteConfirm: (name: string) => `Delete user "${name}"? This cannot be undone.`,
       addIdentityPrompt: 'User created. Add an identity?',
     },
     errorDashboard: {
       title: 'Errors & Failures',
       emptyTitle: 'No errors found',
       emptyDescription: 'Hestia is running smoothly.',
       unresolvedCount: (count: number) => `${count} unresolved`,
       filterAll: 'All',
       filterUnresolved: 'Unresolved',
       filterResolved: 'Resolved',
       filterIgnored: 'Ignored',
       debugModalTitle: 'Debug with Agent',
       debugModalDescription: 'Copy this prompt and send it to Hestia to debug the error.',
       resolveButton: 'Mark resolved',
       ignoreButton: 'Ignore',
       debugButton: 'Debug with agent',
     },
     healthChecks: {
       title: 'Health Checks',
       rerunButton: 'Re-run checks',
       rerunButtonLoading: 'Running…',
       lastChecked: (when: string) => `Last checked: ${when}`,
       passRate: (pass: number, total: number) => `${pass} of ${total} passing`,
     },
     workflowEditor: {
       sendMessageTitle: 'Send Message',
       sendMessageHelper: 'Use {data.field_name} to reference trigger or upstream node outputs.',
       toolCallTitle: 'Tool Call',
       toolCallHelper: 'Arguments passed to the tool as a JSON object.',
       llmDecisionTitle: 'LLM Decision',
       llmDecisionBranchesHelper: 'Possible outcomes. The LLM selects one based on the prompt.',
       conditionTitle: 'Condition',
       conditionHelper: 'Supported: ==, !=, <, >, and, or, not. Reference data with data.field_name.',
       investigateTitle: 'Investigate',
       interactiveCheckbox: 'Wait for user response',
       interactiveTypeLabel: 'Response type',
       interactiveTypeButtons: 'Buttons',
       interactiveTypeText: 'Free text',
       interactiveTimeoutLabel: 'Timeout (seconds)',
       interactiveHelper: 'If enabled, the workflow pauses until the user responds or the timeout expires.',
     },
   } as const;
   ```
2. Export a helper `t(path: string, ...args: any[]): string` for type-safe access.
3. All strings should use single quotes for consistency.

**Commit:** `feat(web-ui): create centralized user-facing text catalog`

### §1 — Extract text from Login, Profile, Knowledge

**Why:** These are the most text-heavy pages and the ones users interact with most.

In `web-ui/src/pages/Login.tsx`:
1. Replace all hardcoded strings with `TEXT.login.*` references.
2. Update tests to import `TEXT` and assert against it.

In `web-ui/src/pages/Profile.tsx`:
1. Replace all hardcoded strings with `TEXT.profile.*`.
2. For dynamic strings (trust override helper), use the function variants.

In `web-ui/src/pages/Knowledge.tsx`:
1. Replace all hardcoded strings with `TEXT.knowledge.*`.
2. Update tag filter text, empty states, section descriptions.

**Commit:** `refactor(web-ui): extract text from Login, Profile, and Knowledge`

### §2 — Extract text from Scheduler, AdminUsers, ErrorDashboard

In `web-ui/src/pages/Scheduler.tsx`:
1. Replace modal titles, labels, placeholders, confirmation text with `TEXT.scheduler.*`.

In `web-ui/src/pages/AdminUsers.tsx`:
1. Replace access denied text, modal titles, button labels with `TEXT.adminUsers.*`.

In `web-ui/src/pages/ErrorDashboard.tsx`:
1. Replace empty states, filter labels, modal text with `TEXT.errorDashboard.*`.

**Commit:** `refactor(web-ui): extract text from Scheduler, AdminUsers, and ErrorDashboard`

### §3 — Extract text from shared components

In `web-ui/src/components/DoctorCheckList.tsx`:
1. Replace "Re-run checks", "Running…", pass-rate text with `TEXT.healthChecks.*`.

In `web-ui/src/components/workflow-editor/NodePropertiesPanel.tsx`:
1. Replace node type titles, helper text, interactive labels with `TEXT.workflowEditor.*`.

In `web-ui/src/components/ConfigForm.tsx`:
1. Replace section descriptions, button labels with `TEXT.config.*` (create this section in `text.ts`).

In `web-ui/src/components/layout/EmptyState.tsx`:
1. This component already accepts `title` and `description` as props — no change needed. Just ensure callers use `TEXT.*`.

**Commit:** `refactor(web-ui): extract text from shared components`

### §4 — Extract text from remaining pages

In `web-ui/src/pages/SessionDetail.tsx`, `Dashboard.tsx`, `Security.tsx`, `StyleProfile.tsx`, `Proposals.tsx`, `Workflows.tsx`:
1. Replace all remaining hardcoded strings with `TEXT.*` references.
2. Create new sections in `text.ts` as needed: `sessionDetail`, `dashboard`, `security`, `styleProfile`, `proposals`, `workflows`.

**Commit:** `refactor(web-ui): extract text from remaining pages`

### §5 — Audit for consistency

**Why:** After extraction, we can spot inconsistencies easily.

1. Search for similar phrases across the catalog:
   - "No … found" vs "No … available" vs "No … yet"
   - "Loading…" vs "Loading …" (with space)
   - Sentence case vs Title Case
2. Standardize on one pattern for each category.
3. Ensure all empty states follow the format: "No [things] yet — [explanation of why + what to do]."

**Commit:** `docs(web-ui): standardize user-facing text patterns`

### §6 — Tests

1. **Catalog completeness test:** Parse `text.ts` exports. Assert every key has a non-empty string value.
2. **No hardcoded strings test:** Run a regex search across `pages/` and `components/` for English words in JSX text nodes. Assert the count is near zero (allowing for numbers and single-word aria labels).
3. **Consistency test:** Assert no duplicate phrases with different casing.

**Commit:** `test(web-ui): text catalog completeness and consistency tests`

## Evaluation

- All user-facing text lives in `web-ui/src/lib/text.ts`
- No hardcoded English strings in page or component files
- Empty states follow a consistent pattern
- Copy can be edited in one place
- Future i18n (translation) is structurally possible

## Acceptance

- `npm run build` in `web-ui/` passes
- Frontend tests pass
- `npx vitest run` green
- `.kimi-done` includes `LOOP=L183`
