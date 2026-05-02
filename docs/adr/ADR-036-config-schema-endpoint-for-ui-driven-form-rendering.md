# ADR-036: Config Schema Endpoint for UI-Driven Form Rendering

- **Status:** Accepted
- **Date:** 2026-05-01
- **Context:** The config editor rendered all fields as plain text inputs. For
  enumerated fields like `trust.preset`, users had to know the valid values
  (`paranoid`, `prompt_on_mobile`, `household`, `developer`) and type them
  correctly. This was error-prone and unintuitive.

- **Decision:**
  1. Add `GET /api/config/schema` which returns metadata about config fields,
     including `type: 'enum'` and a `values` array for enumerated fields.
  2. The frontend fetches this schema on mount and renders `<select>` dropdowns
     for any field whose schema declares it as an enum.
  3. The schema is a static Python dict defined alongside the route handler,
     not generated via reflection. This keeps it explicit and avoids coupling
     the API to internal dataclass internals.
  4. Fields without schema metadata continue to render as their default input
     type (text, number, boolean checkbox, array text).

- **Consequences:**
  - The UI stays in sync with valid values without hardcoding them in the
    frontend. Adding a new enum field only requires updating the backend schema.
  - The schema is currently hand-maintained. If the config structure changes
    frequently, a reflection-based generator may be worth adding later.
  - This pattern can be extended to other metadata (descriptions, validation
    ranges, restart-required flags) in future loops.
