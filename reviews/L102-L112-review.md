# L102--L112 Implementation Review

Hestia 2 Branch --- Web UI, Chat Tools, and Config Changes
April 30, 2026

## Executive Summary

This review covers the implementation of loops L102 through L112 in the Hestia 2 working directory. These loops span PII and credential hardening (L102), chat-based proposal and style management tools (L103), the FastAPI web skeleton and API routes (L104--L105), the React SPA dashboard pages (L106--L111), and flipping reflection and style to enabled-by-default (L112).

The implementation delivers on the core intent of each loop. Tool registration follows existing patterns cleanly, the SELF_MANAGEMENT capability gating is correct, and the L112 opt-out flip is a clean default change. However, the review identified 6 bugs, 5 design issues, 8 minor items, and 5 test coverage gaps that need to be addressed before this work is shippable.

## Findings Summary

| Category | Count | Severity |
|----------|-------|----------|
| Bugs | 6 | **High --- need fix loops** |
| Design Issues | 5 | **Medium --- address before shipping** |
| Minor / Cleanup | 8 | Low --- cleanup pass |
| Test Coverage Gaps | 5 | **High --- tests non-functional** |

## What Looks Good

The tool registration follows existing codebase patterns cleanly. SELF_MANAGEMENT capability gating is correct: paranoid and prompt_on_mobile disable it, household and developer enable it. The L112 opt-out flip is a minimal, clean change (just default values on ReflectionConfig.enabled and StyleConfig.enabled). The FastAPI route structure is well-organized with a clean separation per resource. The web API context pattern is simple and adequate for the single-process architecture. MatrixConfig.__repr__ correctly masks the access_token. The CLI reflection commands and the new chat tools both call the same store methods, maintaining a single source of truth.

## Bugs

These are functional defects that will cause incorrect behavior or crashes at runtime. Each needs its own fix loop or should be grouped into a single cleanup loop.

| ID | Title | File | Detail |
|----|-------|------|--------|
| **BUG-1** | **reset_style_metric writes null instead of deleting** | *src/hestia/tools/builtin/style_tools.py:76* | Calls set_metric(..., None) which inserts a row with value_json: "null" instead of removing it. The StyleProfileStore has no delete_metric method. The metric continues to appear in the profile with a null value. Either add a delete_metric method to StyleProfileStore or use a raw DELETE statement. |
| **BUG-2** | **show_proposal crashes on None dates** | *src/hestia/tools/builtin/proposal_tools.py:82--83* | Calls strftime on created_at and expires_at without null guards. The web route for the same data does guard against None. If a proposal has missing timestamps, the tool raises an AttributeError. |
| **BUG-3** | **ProposalCard buttons render for resolved proposals** | *web-ui/src/components/ProposalCard.tsx* | Accept, Reject, and Defer buttons always render regardless of proposal status. On the History tab, users can re-accept an already-rejected proposal. Buttons should be conditionally hidden when status is not "pending". |
| **BUG-4** | **No client-side routing in the SPA** | *web-ui/src/App.tsx* | App.tsx uses useState for page switching but Playwright tests navigate to URL paths like /proposals and /scheduler. Those paths 404 because there is no router. All Playwright E2E tests are broken as a result. Either add react-router-dom or implement hash-based routing. |
| **BUG-5** | **DoctorCheckList expanded detail layout broken** | *web-ui/src/components/DoctorCheckList.tsx:62--65* | The expanded detail div is inside a flex row without flex-wrap. Detail text either renders inline (cramped) or is invisible depending on content length. Needs to be a separate div below the flex row, or the parent needs flex-wrap: wrap. |
| **BUG-6** | **Error handlers swallow failures across multiple components** | *Scheduler.tsx:40, ProposalCard.tsx, StyleProfile.tsx:31* | If API calls throw, acting/running state flags are never cleared because there is no try/catch/finally. Buttons become permanently disabled until page reload. Affects Scheduler handleRun, ProposalCard handleAccept/handleDefer, and StyleProfile handleReset. |

## Design Issues

These are architectural or design-level concerns that should be addressed before shipping but are not causing runtime failures today.

| ID | Title | File | Detail |
|----|-------|------|--------|
| **DES-1** | **put_config returns 200 for a no-op** | *src/hestia/web/routes/config.py:42--46* | The config PUT endpoint accepts the request, does nothing, and returns 200 with {"detail": "Configuration updated"}. A client believes the update succeeded. Should return 501 Not Implemented until real save logic is wired up. |
| **DES-2** | **reject_proposal missing requires_confirmation** | *src/hestia/tools/builtin/proposal_tools.py:135* | accept_proposal has requires_confirmation=True but reject_proposal does not. Both permanently change status. The asymmetry looks like an oversight. At minimum reject_proposal should match accept_proposal since both are irreversible. |
| **DES-3** | **No authentication on web API** | *src/hestia/web/ (all routes)* | The dashboard exposes config (with masked secrets), session data, traces, and allows accepting/rejecting proposals and triggering scheduler tasks. Binding to 127.0.0.1 mitigates remote access, but any local process can hit these endpoints. Should be documented as a known limitation and an auth loop queued. |
| **DES-4** | **cmd_serve config parameter typed Any** | *src/hestia/commands/serve.py:18* | The config parameter is typed as Any instead of HestiaConfig. This loses all type checking for config.telegram, config.matrix, config.web and related attribute access. |
| **DES-5** | **No Tailwind CSS in SPA** | *web-ui/package.json, all components* | The design artifact specifies React + Vite + Tailwind. The implementation uses all inline style={{}} objects. Not a functional bug, but a significant deviation from the design that makes the UI harder to maintain. |

## Minor / Cleanup

Lower-priority items that should be addressed in a cleanup pass. None are blocking, but they represent inconsistencies or technical debt.

| ID | Title | File | Detail |
|----|-------|------|--------|
| **MIN-1** | **Missing React key on Fragment in Dashboard.tsx** | *web-ui/src/pages/Dashboard.tsx:80* | Uses <> inside .map() instead of <React.Fragment key={s.id}>. React will warn and may mishandle reordering. |
| **MIN-2** | **Proposals History tab fetches all proposals** | *web-ui/src/pages/Proposals.tsx:28* | When tab is "history", passes status='' which fetches all proposals, then filters client-side. Should omit the param or pass a meaningful filter. |
| **MIN-3** | **ConfigForm.stripSecrets is a no-op** | *web-ui/src/components/ConfigForm.tsx:84--95* | Traverses the config recursively but returns every value unchanged. Either the masking logic is missing or the function should be removed. |
| **MIN-4** | **Egress page requires manual click to load** | *web-ui/src/pages/Egress.tsx* | Every other page auto-loads on mount. Egress starts empty until "Search" is clicked. Inconsistent UX. |
| **MIN-5** | **"Reset to defaults" resets to fetched config, not actual defaults** | *web-ui/src/pages/ConfigPage.tsx* | resetSection restores initialConfig[sectionKey], which is whatever the server returned. The button label "Reset to defaults" is misleading. |
| **MIN-6** | **Scheduler route uses getattr for "notify" field** | *src/hestia/web/routes/scheduler.py:35* | Uses getattr(t, "notify", False) suggesting uncertainty about the task model. If the field exists, access it directly; if it might not, fix the data model. |
| **MIN-7** | **Egress route uses dict access while all others use attrs** | *src/hestia/web/routes/egress.py:27--36* | Accesses e["id"], e["url"], etc. while every other route uses attribute access on dataclass objects. Inconsistency suggests either the egress store returns raw rows or the route was written against a different interface. |
| **MIN-8** | **Global mutable _ctx singleton in context.py** | *src/hestia/web/context.py* | Adequate for single-worker uvicorn but will break with multiple workers. Worth adding a comment noting this constraint. |

## Test Coverage Gaps

The Playwright test suite is essentially non-functional. These issues need to be addressed as a group, likely in a single foundational test infrastructure loop.

| ID | Title | Detail |
|----|-------|--------|
| **TST-1** | **All Playwright tests will fail** | Tests navigate to URL paths (/proposals, /style, etc.) that don't exist because there is no client-side router. This is a direct consequence of BUG-4. |
| **TST-2** | **No API mocking** | Tests hit http://127.0.0.1:8765 (a real server) with no route mocking or fixture data. Tests are non-deterministic and require a running backend. |
| **TST-3** | **Zero interaction coverage** | Apart from the broken proposals accept test, no test clicks a button, submits a form, expands a row, or verifies error states. Config save, trust presets, style reset, scheduler run-now, doctor re-run, audit run, and egress search are all untested. |
| **TST-4** | **dashboard.spec.ts expects wrong text** | Asserts h1 text "Hello Hestia" but the actual Dashboard component renders "Sessions". sessions.spec.ts also navigates to / and asserts different text. One of them is wrong. |
| **TST-5** | **No navigation tests** | The core nav mechanism (clicking nav buttons to switch pages) is never tested. |

## Recommendations

The following loops are recommended to address the findings in this review:

### Proposed Loop: L113 --- Chat Tool Bug Fixes

Covers BUG-1 (reset_style_metric delete vs. null), BUG-2 (show_proposal None guard), and DES-2 (reject_proposal requires_confirmation). These are all in the same two tool files and can be fixed together. Also add a delete_metric method to StyleProfileStore.

### Proposed Loop: L114 --- SPA Routing and Component Fixes

Covers BUG-4 (add react-router-dom or hash routing), BUG-3 (hide action buttons for non-pending proposals), BUG-5 (DoctorCheckList layout), BUG-6 (try/catch/finally on all async handlers), MIN-1 (React key on Fragment). These are all frontend fixes in the same codebase.

### Proposed Loop: L115 --- Playwright Test Infrastructure

Covers TST-1 through TST-5. Add API mocking with MSW or Playwright route interception. Fix test assertions to match actual component output. Add interaction tests for proposal actions, config save, scheduler run-now, style reset, and page navigation. This loop depends on L114 (routing must exist before tests can navigate).

### Proposed Loop: L116 --- Web API Hardening

Covers DES-1 (put_config 501), DES-3 (document no-auth limitation, queue auth loop), DES-4 (serve.py typing), MIN-6 (scheduler getattr), MIN-7 (egress dict vs. attr access), MIN-8 (context.py singleton comment). Backend cleanup that can be done independently of frontend work.

### Proposed Loop: L117 --- SPA Polish and Consistency

Covers DES-5 (Tailwind adoption or conscious deviation decision), MIN-2 (history tab fetch), MIN-3 (stripSecrets no-op), MIN-4 (egress auto-load), MIN-5 (reset-to-defaults label). Lower priority; can be deferred if needed, but should land before any external-facing demo.

### Dependency Chain

L113 and L116 are independent and can run in parallel. L114 must complete before L115 (tests need routing). L117 is independent but lowest priority. Suggested ordering: L113 + L116 in parallel, then L114, then L115, then L117.
