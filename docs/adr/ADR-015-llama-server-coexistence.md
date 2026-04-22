# ADR-015: llama-server coexistence modes

## Status

Accepted

## Context

Dylan's runtime currently shares a single llama-server between Hestia and Hermes:

- Same process on port 8001
- Same slot directory (`~/.hermes/cache/slots/`)
- Same Matrix room (both bots present as "Silas")

This produced the "Cannot compress further" overflow message from Silas during a
Hestia post-merge check — the two bots share a server *and* a room, so errors from
one appear in the other's UI.

Hestia could try to auto-detect or auto-launch a llama-server, but that adds
complexity, couples us to llama.cpp's CLI flags, and makes deployments less
predictable.

## Decision

Hestia **does not** auto-detect or auto-launch a llama-server. The operator is
responsible for running a dedicated llama-server per agent identity.

We document two coexistence modes:

- **Mode A (dedicated, recommended):** Hestia runs its own llama-server on its
  own port with its own slot directory. No sharing, no coupling, clear context
  budget. Use `deploy/hestia-llama.service` (port 8001) or
  `deploy/hestia-llama.alt-port.service.example` (port 8002) if 8001 is taken.

- **Mode B (shared):** Hestia points at an existing llama-server (e.g. Hermes's).
  Saves VRAM at the cost of coupling and noisy-neighbor slot evictions.
  `slot_dir` must match the server's `--slot-save-path`.

## Consequences

### Positive

- **Predictable context budget:** Dedicated server means Hestia owns the entire
  `--ctx-size / --parallel` budget.
- **No auto-launch complexity:** We don't need to parse llama.cpp flags, manage
  processes, or handle port conflicts.
- **Clear operator ownership:** If the server is down, the operator knows which
  unit to check.

### Negative

- **Extra VRAM for dedicated mode:** Running two llama-servers uses more GPU
  memory than sharing one.
- **Operator must configure:** New users need to understand the port/slot_dir
  relationship.

## Related

- `deploy/hestia-llama.alt-port.service.example`
- `docs/guides/runtime-setup.md`
