# ADR-011: Calibration is two numbers (body factor + meta-tool overhead)

- **Status:** Accepted
- **Date:** 2026-04-09
- **Context:** ADR-009 accepted a single mean ratio (1.68) as the correction factor
  for `count_request()`, despite high variance (0.57 to 3.45). Analysis of the
  underlying data revealed the variance was bimodal: tool-free requests over-count
  (safe), tool-bearing requests under-count (dangerous). Hestia always sends the
  same two meta-tools, so the tool overhead is a constant.
- **Decision:** Split calibration into `body_factor` (measured on tool-free
  requests, applied as division) and `meta_tool_overhead_tokens` (measured once,
  added as constant when meta-tools are in the request). Formula:
  `corrected = int(predicted_body / body_factor) + meta_tool_overhead_tokens`.
  `count_request()` callers now always pass `tools=[]` for consistency.
- **Consequences:** Budget calculation is now directionally safe (over-counts,
  never under-counts). If we ever add tools beyond the two meta-tools to the
  request, the calibration needs to be extended. Supersedes ADR-009.
