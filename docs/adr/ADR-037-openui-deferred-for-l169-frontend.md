# ADR-037: OpenUI deferred for L169 frontend pages

- **Status:** Accepted
- **Date:** 2026-05-14
- **Context:** L169 (User Registry & Profile Management) required new frontend pages (Profile, Knowledge, Login user-selection). The loop spec originally called for adopting `@openuidev/react-ui` as the component framework for these pages, with the rationale that it would speed up development and provide a clean UI until a design language was established.
- **Decision:** We decided **not** to adopt OpenUI for L169. The Profile, Knowledge, and updated Login pages were built with the existing raw React + inline styles approach, consistent with the rest of the web UI.
- **Consequences:**
  - **Faster delivery:** No time spent on component library integration, build config, type definitions, or learning a new API.
  - **Lower risk:** Avoided potential build breakage or dependency conflicts mid-project.
  - **Consistent codebase:** New pages match the existing StyleProfile, Dashboard, and Config pages in structure and style.
  - **Future migration cost:** If a design system is adopted later, these two pages (Profile, Knowledge) will need to be migrated along with the rest of the UI.
  - **Reversibility:** OpenUI can still be evaluated and adopted in a future loop if a design language stabilizes.
