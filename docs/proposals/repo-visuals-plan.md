# Plan — Screenshots and visuals for the repo

**Status:** plan / not started

Two strategic calls drive everything: use **Mermaid** for architecture diagrams
(GitHub renders it inline, it lives in git as text, and it never goes stale the
way a screenshot does), and capture all UI screenshots from the **seeded demo
instance only**, never the real runtime, so no real names, sessions, or memories
land in a public repo's permanent git history.

## 1. What to add

**Architecture diagrams (Mermaid, inline):**
- System overview: platforms (Telegram/Matrix/Email/CLI/Web) → orchestrator (turn
  state machine) → llama.cpp slots + tools + CapabilityGate + persistence/memory.
- The turn lifecycle (state machine) and the trust-gate decision flow as smaller
  diagrams in the architecture/ADR docs.

**UI screenshots (showcase + guide illustrations):**
- README: one hero shot (Dashboard) plus the system diagram.
- Guides where they earn their place: `web-dashboard.md` (Dashboard + a couple
  pages), `workflows.md` (node editor), `browser-sessions.md` (session list + a
  live stream), and showcase shots of Context Lab, Security & Health, Scheduler.
- Deliberately NOT all 13 pages — screenshots drift, so capture the high-value,
  visually-interesting, stable ones and let the rest stay text.

## 2. Where they live

- `docs/assets/screenshots/` for PNGs, lowercase-kebab names (`dashboard.png`,
  `workflows-editor.png`, `browser-stream.png`).
- Mermaid diagrams inline in markdown (no files needed).
- Reference with relative paths so they render on GitHub and locally.

## 3. Capture process

- Run the seeded demo instance, not the live one. First enrich the seed so pages
  look alive (a few demo workflows, scheduled tasks, a populated dashboard, sample
  memories) — empty pages make bad screenshots.
- Fix capture settings: one browser, fixed window width (1440 is a good default),
  one canonical theme. Dark is the app default; light reads better against
  GitHub's light README background — pick one.
- Optimize PNGs (pngquant/oxipng) before committing; they live in git permanently,
  so keep them lean. Consider Git LFS only if the set grows large or is refreshed
  often; a handful of optimized shots is fine to commit plainly.

## 4. Maintenance

Favor diagrams over screenshots for anything conceptual (Mermaid is editable and
never stale). Treat screenshots as a per-release refresh chore on the demo
instance, and keep the set small enough that refreshing is quick.

## 5. Sequencing

- **Now, no capture needed:** author the Mermaid architecture diagrams into the
  README and architecture docs.
- **A capture session:** stand up and enrich the demo instance, drive a browser
  against it to capture the screenshot set, drop them in
  `docs/assets/screenshots/`, optimize, and wire references into the README and
  guides.
