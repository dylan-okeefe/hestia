# L189: Chunked Large-File Writes

## Goal
Prevent unclosed `write_file` XML blocks (the truncated-write regression fixtures) by teaching the model the chunked-write protocol and recovering gracefully when a write is truncated.

## Motivation
The regression fixtures include `write_file_unclosed_huge.xml`, a massive unclosed `write_file` block caused by the model trying to fit an entire job-search document into one tool call and hitting `max_tokens`. The fix is not in the parser; it is at source: the model must write in chunks, and when truncation happens we must not treat the file as complete.

## Scope
- Update system prompts and tool descriptions to instruct chunked writes (header via `write_file`, sections via `append_to_file`) when content exceeds 2000 characters.
- Change the `TRUNCATED_WRITE_FILE` degenerate-pattern handler so it:
  - Attempts to recover the partial `path` and `content` from the unclosed XML.
  - Writes the partial content to disk (if recoverable and under the limit).
  - Injects a correction telling the model the file was truncated, where it was saved, and to continue with `append_to_file`.
- Never let a truncated write finish the turn as if the file is complete.
- Do NOT change file-system trust/allowed-roots policy.

## Out of scope
- New tools (the existing `write_file` and `append_to_file` are sufficient).
- Automatic chunking/splitting by the orchestrator.

## §1 Instruct chunked-write protocol

### Implementation
Update `src/hestia/config.py` default system prompt and `config.runtime.py` system prompt:
- Add a clear rule: "If you need to write more than 2000 characters, create the file with a short header using `write_file`, then add each remaining section with `append_to_file`."
- Add a concrete example in the runtime prompt (since job search is the current use case):
  ```
  call_tool({"name": "write_file", "arguments": {"path": "/home/<user>/Documents/Job Search/listings.md", "content": "# Job Listings\n\n"}})
  call_tool({"name": "append_to_file", "arguments": {"path": "/home/<user>/Documents/Job Search/listings.md", "content": "## Listing 1\n..."}})
  call_tool({"name": "append_to_file", "arguments": {"path": "/home/<user>/Documents/Job Search/listings.md", "content": "## Listing 2\n..."}})
  ```
- Update `write_file` public description to: "... If content is longer than 2000 characters, write a short header first and append the rest with append_to_file."
- Update `append_to_file` public description similarly.

### Tests
Add/update tests in `tests/unit/test_config.py` or `tests/unit/tools/test_registry.py` that assert the descriptions mention the 2000-char limit and chunked protocol. System-prompt content can be checked by string assertions.

### Commit
`docs: teach chunked-write protocol in system prompts and tool descriptions`

## §2 Recover and continue truncated writes

### Implementation
In `src/hestia/orchestrator/quality.py`:
- Replace the current `TRUNCATED_WRITE_FILE` correction message with a recovery flow.
- Add helper `_recover_truncated_write_file(content: str) -> tuple[str, str] | None` that uses a lenient regex to extract `path` and `content` from an unclosed XML block, stopping at the truncation point. Example pattern:
  ```python
  re.search(r'"path"\s*:\s*"([^"]+)"', content)
  re.search(r'"content"\s*:\s*"(.*)', content, re.DOTALL)
  ```
  The content capture will be incomplete; treat it as the partial content.
- In `classify_turn`, when `TRUNCATED_WRITE_FILE` is detected:
  1. Call `_recover_truncated_write_file`.
  2. If recovery succeeds, call the underlying `write_file` tool function with the partial content and path. If the file already exists, append? No — this is the first chunk, so overwrite. If write succeeds, build a correction message that includes the saved path and byte count.
  3. If recovery fails or write fails, fall back to the generic correction.

Injected correction example:
> "Your write_file call was truncated before completion. The first 1,847 characters have been saved to /home/<user>/Documents/Job Search/listings.md. Continue by calling append_to_file with the next section. Do not try to rewrite the entire file in one call."

In `src/hestia/orchestrator/execution.py`, `_classify_and_maybe_correct` already calls `classify_turn` and injects the correction. The correction message is what drives model behavior. Ensure the turn does not end after the correction; it should return `True` so the loop continues.

### Tests
Add tests in `tests/unit/orchestrator/test_quality.py`:
- A truncated write_file XML is classified as `TRUNCATED_WRITE_FILE`.
- Recovery extracts path and partial content correctly.
- Recovery writes the partial content and the correction mentions `append_to_file`.
- A truncated append_to_file also triggers the correction (reuse the same helper).

Add a regression test in `tests/unit/core/test_regression_xml_tool_calls.py`:
- `write_file_unclosed_huge.xml` now results in a recovery ToolCall/correction, not zero tool calls.

### Commit
`feat: recover partial content from truncated write_file and continue with append_to_file`

## §3 Handoff
Update this spec with review carry-forward and write `docs/handoffs/L189-chunked-large-file-writes-handoff.md`.

## Quality gates
Run after each section:
```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

## Critical rules recap
- Do not merge or push without Dylan's okay.
- No trust/security policy changes.
- No new dependencies.
- Restart `hestia-serve.service` after deploying to runtime.
