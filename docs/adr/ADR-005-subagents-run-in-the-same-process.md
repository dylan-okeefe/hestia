# ADR-005: Subagents run in the same process

- **Status:** Accepted
- **Date:** 2026-04-09
- **Context:** Subagent delegation needs isolation but IPC (multiprocessing, gRPC,
  etc.) adds significant complexity for v1. One process is simpler to operate and
  debug. A supervisor can resurrect failed subagents by catching exceptions.
- **Decision:** Subagents are asyncio tasks within the same process, supervised
  by the orchestrator. Different slot, different session, but same Python process.
  Multi-process is deferred to post-v1 if needed.
- **Consequences:** A crashing subagent could crash the whole agent if not caught.
  GIL contention is not an issue because the workload is I/O bound (inference
  calls). Memory is shared, so subagents must not mutate global state.
