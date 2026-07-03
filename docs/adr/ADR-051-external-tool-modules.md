# ADR-051: External tool modules

- **Status:** Accepted
- **Date:** 2026-07-03
- **Context:** Hestia ships with a fixed set of built-in tools. Operators repeatedly asked for a way to add private or domain-specific tools without forking the repository or patching `src/hestia/app.py`.
- **Decision:** Add an opt-in `extra_tool_modules` config field. Each entry is a dotted Python import path. After built-in tools are registered, Hestia imports each configured module and, if it exposes a callable named `register`, calls `register(registry)` with the `ToolRegistry`.
- **Constraints:**
  - This extension point is opt-in only. No directory scanning, no autoloading, and no implicit discovery. If a module is missing, has no `register` callable, or its registration raises `ValueError`, Hestia logs a warning and continues.
  - External tools are first-class registry citizens. They are subject to the same `CapabilityGate` and `DefaultPolicyEngine.filter_tools()` logic as built-ins; there is no special casing or trust bypass.
- **Consequences:**
  - Operators can keep private tooling in separate packages and wire it in through config.
  - The explicit `register(registry)` hook keeps the seam small and easy to reason about.
  - Because external tools share the same capability labels and policy enforcement, mistakes in a custom module cannot accidentally escape the trust boundary.
