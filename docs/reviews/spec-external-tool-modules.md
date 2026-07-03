# Spec — external tool modules (custom tool extension point)

**Status:** Spec ready, pending Dylan's okay to queue.
**Branch:** off `develop`.
**Motivation:** Hestia currently hardcodes every tool in
`app.py:register_tools()`. There is no way to add tools from outside the repo
without forking. This blocks keeping private/liability-sensitive tools (e.g. the
job-search scrapers on `feature/job-search-tools`) out of the public repo while
still running them on a personal instance. This adds one generic, opt-in seam so
external packages can contribute tools.

## Goal

Let an operator load additional `@tool`-decorated callables from external Python
modules named in config, registered alongside the built-ins, with the same
`ToolRegistry`, capability gating, and policy treatment. Core stays publishable;
private tools live in a separate repo.

## Decisions (implement as written)

1. **Opt-in by explicit config only.** New setting `extra_tool_modules: list[str]`
   (dotted module paths, importable from the runtime's environment). Empty by
   default. No directory scanning, no auto-discovery, no world-writable paths.
2. **Registration convention.** Each listed module must expose
   `def register(registry: ToolRegistry) -> None`. Hestia imports the module and
   calls `register(reg)` after the built-ins are registered. (Explicit hook, not
   decorator-scanning, so load order and failures are obvious.)
3. **Full-trust boundary, documented.** External tool code runs in-process with
   full trust and can declare any capability. This is acceptable only because it
   is explicit operator opt-in. Document prominently: only list modules you wrote
   or fully trust. Do not load from untrusted or shared locations.
4. **Fail loud, not silent.** If a listed module fails to import or has no
   `register`, log a clear error and skip that module; do not crash the whole
   process, and do not silently ignore it. Name collisions with an existing tool
   raise (reuse the registry's existing duplicate-name error).
5. **No capability escalation path.** External tools are still subject to the
   CapabilityGate and PolicyEngine exactly like built-ins. This seam does not
   bypass trust, filtering, or the scheduler/subagent restrictions.

## Implementation

- `config.py`: add `extra_tool_modules: list[str] = []` to the relevant config
  section (mirror how other list settings load from env, e.g.
  `HESTIA_EXTRA_TOOL_MODULES` comma-separated).
- `app.py:register_tools()`: after the built-in `reg.register(...)` calls, iterate
  `config ... extra_tool_modules`, `importlib.import_module(name)`, look up
  `register`, call it with `reg`. Wrap each in try/except with a clear log line.
- Reuse the existing `ToolRegistry.register` duplicate detection.

## Tests

- A fixture module exposing `register(reg)` that adds one tool is loaded and its
  tool is callable through the registry.
- A module missing `register` logs an error and is skipped; other tools still
  load.
- A module raising on import is skipped with a clear error; startup continues.
- An external tool that declares a capability is still filtered by
  `filter_tools` for a subagent/scheduler exactly like a built-in with that
  capability (proves no trust bypass).
- Empty/default config loads no external modules (no behavior change).

## Migration note (job-search tools)

Do NOT merge `feature/job-search-tools`. Its five tools
(`builtin_search`, `dice_search`, `linkedin_search`, `ziprecruiter_search`, and
the `indeed_search` rewrite) move to a private repo that Hestia loads through this
seam. Remove their `register_tools`/`__init__.py` lines from the public branch.
Reasons: ToS/anti-bot evasion (`use_curl_cffi`, stealth logged-in scraping) is a
public-release liability, and the tool descriptions carry personal job-search
taxonomy (`A-IN-*`, `C-IN-*`). In the private repo they get parser fixture tests
and generic descriptions.

## Doc deliverables

- A short ADR (external tool modules: opt-in, full-trust, explicit `register`
  hook).
- A `docs/guides/custom-tools.md` section (or update) showing how to write an
  external tool package and list it in config, with the trust warning.

## Critical rules

- No merge/push without Dylan's okay.
- Tests assert the invariants first.
- The seam is opt-in and never bypasses the CapabilityGate.
