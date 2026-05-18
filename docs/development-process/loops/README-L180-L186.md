# L180–L186: Post-Audit Remediation Roadmap

These 7 loops cover all findings from the L176–L179 comprehensive audit. They are designed to be worked independently where possible, with noted dependencies.

## Execution Order

```
Phase 1 (can run in parallel):
  ├── L180 — Security & Authorization Hardening
  ├── L181 — Performance & Resource Cleanup
  └── L182 — Backend Bug Fixes & Cleanup

Phase 2 (depends on L184):
  ├── L184 — Shared CSS System
  ├── L185 — Responsive Design
  └── L186 — Dark Mode

Phase 3 (independent):
  └── L183 — User-Facing Text Extraction
```

Phase 1 and Phase 3 can run concurrently. Phase 2 must run sequentially (L184 → L185 → L186) because each depends on the previous one's CSS foundation.

## Summary

| Loop | Focus | Key Deliverables | Est. Size |
|------|-------|------------------|-----------|
| **L180** | Security & Authorization | Per-user auth on sessions/memory/scheduler; admin-only errors; Pydantic validation; shared auth deps | Medium |
| **L181** | Performance & Resource Cleanup | Batch queries for list_users/list_sessions; TTL cleanup for WorkflowResponseStore; Telegram Bot caching; Matrix txn_id fix | Medium |
| **L182** | Backend Bug Fixes | Fix update_user null guard; remove raw SQL from errors; fix session messages endpoint; cap error state; validate interactive send | Small-Medium |
| **L183** | User-Facing Text Extraction | Centralized `text.ts` catalog; extract 100+ strings from 15+ files; standardize patterns | Medium |
| **L184** | Shared CSS System | CSS variables, utility classes; zero inline styles; Login padding fix; NodePropertiesPanel under 200 lines | Large |
| **L185** | Responsive Design | Mobile nav hamburger; card-based tables; stacked layouts; responsive modals; canvas scroll | Medium |
| **L186** | Dark Mode | Dark tokens; theme toggle; system preference; per-component fixes; syntax highlighting | Medium |

## Branch Strategy

Each loop branches from `feature/l179-rooms-interactive-nodes` and should merge back to it when complete. After all 7 loops are done, the combined branch is ready for merge to `main`.

```
feature/l179-rooms-interactive-nodes
├── feature/l180-security-hardening
├── feature/l181-performance-cleanup
├── feature/l182-backend-bug-fixes
├── feature/l183-text-extraction
├── feature/l184-shared-css
│   └── feature/l185-responsive-design
│       └── feature/l186-dark-mode
```

## Risk Notes

- **L180 (Security)** is the highest priority. It blocks any non-localhost deployment.
- **L184 (CSS)** is the most disruptive in terms of file count (touches almost every component).
- **L183 (Text)** and **L184 (CSS)** will have merge conflicts if worked simultaneously — coordinate or sequence them.
- **L181 §3 (WorkflowResponseStore TTL)** and **L182 §4 (send_message validation)** both touch `src/hestia/workflows/` — sequence or carefully coordinate.
