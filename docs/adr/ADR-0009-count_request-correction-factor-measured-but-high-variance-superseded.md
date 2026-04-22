# ADR-0009: count_request correction factor measured but high variance [SUPERSEDED]

- **Status:** Superseded by ADR-0011
- **Date:** 2026-04-09
- **Context:** `InferenceClient.count_request()` tokenizes a JSON-serialized request
  body to estimate token count. The actual `prompt_tokens` from llama-server depends
  on the chat template transformation, which is different from raw JSON.
- **Decision:** Measured mean ratio of 1.68 ± 0.84 across 10 conversation shapes.
  High variance (0.57 to 3.45) indicates `count_request` is not reliable for exact
  budgeting. ContextBuilder will use it for rough estimation only; actual overflow
  is handled by the server error response. The correction factor is stored in
  `docs/calibration.json` but is advisory only.
- **Consequences:** Token budgeting is approximate. We may overflow context and get
  a server error in edge cases. The orchestrator should catch and handle this.
  Exact context management requires server-side tokenization which is too slow
  for iterative budget checking.
- **Superseded by:** ADR-0011 (two-number calibration is more accurate and safe)
