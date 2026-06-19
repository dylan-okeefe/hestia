# ADR-046: Chunked large-file writes with truncated-write recovery

- **Status:** Accepted
- **Date:** 2026-06-16
- **Context:** A token-limited local model truncates a large `write_file` call
  mid-content, producing both a corrupt file and an unclosed tool-call XML block.
  This is a prevent-at-source problem: repairing the parse alone cannot recover
  the bytes the model never emitted (L218).

- **Decision:**
  1. `write_file` advertises a chunk-size limit and instructs the model to write
     a header first, then continue with `append_to_file` for large content.
  2. When the quality monitor detects an oversized unclosed `write_file` block,
     it drops the incomplete trailing line, writes the safe prefix, and instructs
     the model to continue with `append_to_file` from the next complete line,
     rather than failing the turn or persisting a corrupt file.
  3. A byte-for-byte recovery test takes a real file, truncates it mid-line, runs
     the recovery plus continuation, and asserts the result equals the original.

- **Consequences:** Large writes are reliable on a small model, and the recovery
  is provably lossless at the seam rather than producing a duplicated or mangled
  join.

- **Related:** `tools/builtin/write_file.py`, `tools/builtin/append_to_file.py`,
  `orchestrator/quality.py`.
