# ADR-020: CLI decomposition into `app.py` + `platforms/runners.py`

## Status

Accepted — implemented in v0.7.4 (loop L30).

## Context

`src/hestia/cli.py` had grown to **2,569 lines** and was doing three
fundamentally different jobs in one file:

1. **Subsystem bootstrapping** — the top-level `cli()` Click group ran a
   ~200-line constructor cascade on every invocation (including `hestia
   version` and `hestia health`), instantiating an `InferenceClient`
   plus an `httpx.AsyncClient` just to print a version string.
2. **Platform-specific runtime loops** — `run_telegram` and `run_matrix`
   were ~120 lines each of nearly-identical copy-paste: extract 10+ raw
   items from `ctx.obj`, build an `InjectionScanner`, construct an
   `Orchestrator` with a 12-kwarg call, define an `on_message` closure,
   start a `Scheduler`, run the poll loop.
3. **CLI command definitions** — Click decorators and command bodies
   buried alongside everything above.

The drift was visible at three call sites:

- `cli()` constructed an `Orchestrator` for the in-process REPL with
  one set of dependencies.
- `schedule_daemon` re-constructed an `Orchestrator` from `ctx.obj`,
  also re-constructing a `SchedulerStore` from `db` even though the
  app already had one.
- `run_telegram` / `run_matrix` constructed yet another `Orchestrator`
  from yet another raw-dict read of `ctx.obj`.

When loop L29 added a new `style_store` dependency, only two of those
three call sites were updated, and the third silently lost style
profiles in production.

## Decision

Split `cli.py` into three modules with single responsibilities:

### `src/hestia/app.py` — application context and command implementations

- `CliAppContext` dataclass — typed, lazy holder of every subsystem
  (config, db, inference, registries, stores, schedulers).
- `make_app(config)` — synchronous constructor; performs no I/O.
- `bootstrap_db()` — idempotent async DB setup. Safe to call from
  every command.
- `inference` — lazy `@property`. Built on first access; closed in
  `close()`.
- `reflection_scheduler` / `style_scheduler` — lazy `@property`
  unconditionally constructing the scheduler the first time they're
  read. Whether the scheduler actually **ticks** is governed by
  `config.reflection.enabled` checks at the start sites; construction
  is unconditional so callers can read failure history even when the
  scheduler is not auto-started.
- `make_orchestrator()` — the **only** place an `Orchestrator(...)`
  is constructed. Adding a new dependency to the orchestrator now
  requires editing exactly one file.
- `_cmd_*` async functions — one per CLI command. They take
  `app: CliAppContext` as the first argument. No Click coupling.

### `src/hestia/platforms/runners.py` — platform polling loops

- `run_platform(app, config, *, adapter_factory, on_message_factory)` —
  shared poll-loop helper.
- `run_telegram(app, config)` and `run_matrix(app, config)` — thin
  wrappers that build the platform adapter and call the helper.

### `src/hestia/cli.py` — Click definitions only (≤ 600 lines)

- One Click decorator stack per command, body delegates to
  `_cmd_xyz(app, ...)` from `hestia.app` (or `run_telegram` /
  `run_matrix` from `hestia.platforms.runners`).
- A `run_async` decorator wraps `async def cmd(app, ...)` into a
  Click-compatible sync handler that owns its own event loop. The
  per-command `asyncio.run(_inner())` boilerplate is gone.
- `ctx.obj` holds only the typed `CliAppContext`. The previous
  parallel raw-dict layer (`ctx.obj["inference"]`, etc.) is removed.

## Consequences

**Positive**

- Adding an `Orchestrator` dependency is a one-line change in
  `make_orchestrator()`. The three-call-site drift cannot recur.
- `hestia version` and `hestia health` no longer trigger an
  `InferenceClient` construction.
- `_cmd_*` functions are unit-testable without a Click runner.
- Every platform adapter now goes through the same `run_platform`
  helper. Adding a Discord adapter is ~30 lines, not ~120.

**Negative / accepted**

- `app.py` is large (≈1,520 lines). It is a deliberate junk drawer
  for command implementations; further splits (e.g. `commands/`
  package by topic) are deferred to a later loop if the file keeps
  growing.
- `CliAppContext` is mutable (lazy properties memoise on first
  access). Tests must reset state if they re-use a context across
  runs. The Click-runner tests construct a fresh app per invocation,
  so this is not currently a problem.

## Notes

- L29 had introduced 12 new `E501` line-too-long lints in `cli.py`;
  the L30 split naturally resolved most of those, and a `ruff --fix`
  pass took the project-wide count from **255 → 44**.
- The reflection scheduler property dropped its
  `config.reflection.enabled` gate at construction time so the
  `hestia reflection status` test contract (a patched
  `ReflectionScheduler.__init__` must fire when status is queried)
  continues to hold without forcing the operator to enable the
  background loop.
