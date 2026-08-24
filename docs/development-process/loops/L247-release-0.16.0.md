# L247: Release 0.16.0 — documentation, security disclosure, onboarding honesty

**Status:** ready to run · **Board card:** #52 · **Branch:** `docs/release-0.16.0` off `develop`
**Blocked by:** #44 (L245) merged to `develop`, and V1 gates confirmed green on the merge commit.

---

## Decisions already made — do not re-litigate, do not ask again

Dylan answered these on 2026-08-23. They are settled inputs to this loop.

| Question | Decision |
|---|---|
| Security disclosure path | **GitHub private vulnerability reporting.** No email address in `SECURITY.md`. |
| `pyproject.toml` author email | **dylanokeefedev@gmail.com** |
| Version | **0.16.0** |
| Card #35 (SOUL.md) | **In scope.** Added as Phase 4 below. |

**One dependency you must check, not assume:** GitHub private vulnerability reporting has to be switched on in the repository settings before `SECURITY.md` can point at it. If it is not enabled, `SECURITY.md` would be directing researchers at a form that does not exist, which is no better than the placeholder it replaces. Verify it is on. If you cannot verify it from where you are running, write the section as intended and flag it in the handoff as a one-click action Dylan must complete before tagging. Do not fall back to an email address.

## Why this loop exists

`main` is at 2026-06-10 (v0.15.1). `develop` is at 2026-08-23. That is **321 commits, 280 of them non-merge, across two and a half months**, and the `CHANGELOG.md` `[Unreleased]` section currently describes only L245.

This release is going to be read by people other than the author. That raises the bar on three documents that are currently either empty, stale, or carrying placeholder text:

- the changelog, which describes 5% of what shipped
- `SECURITY.md`, which tells a security researcher to email `security@example.com`
- `README.md`, which tells a new user to run `git clone <repo-url>`

A release with those three problems teaches a visitor that the project's documentation cannot be trusted, which is a worse outcome than not releasing.

This loop produces the release documentation and closes board cards #33 and #34.

## Preconditions, verify before starting

1. `#44` is merged to `develop`. If `git log --oneline develop | head -1` does not include the L245 merge, stop.
2. Gates green on `develop` at its current head, not on an earlier commit:
   ```
   uv run ruff check src tests && uv run mypy src/hestia && uv run pytest -q
   cd web-ui && npm run build && npx vitest run
   ```
   Record the actual numbers in the handoff. If anything is red, stop and report rather than fixing it as a drive-by; a red gate on `develop` is its own finding.
3. Branch: `git checkout -b docs/release-0.16.0 develop`.

## Version number

**0.16.0.** Not 0.15.2, because this release contains breaking changes. Not 1.0.0, because that is a statement about stability the project has not earned yet and is the author's call to make deliberately, not a side effect of a docs loop.

Bump in `pyproject.toml` (currently line 3, `version = "0.15.1"`). Grep for other hardcoded version strings and report what you find rather than assuming `pyproject.toml` is the only one.

---

# Phase 1: release documentation

## 1.1 The source material

**Do not crawl 280 commits.** The merge commits are already a thematic outline:

```
git log --oneline --merges main..develop
```

That returns roughly 40 entries, most of them already named by feature area: "merge audit-remediation-r1", "merge C1/C3 security re-posture", "Merge Loop A (L237) thread-scoped memory backend", "Merge L220-L223 (persistence split, session concurrency, trust boundary, blocked-actions digest)". Use that as the spine, then drill into individual commits only where a merge title is not specific enough to write an entry from.

Supporting material, in order of usefulness:

- `docs/audit/REMEDIATION_SUMMARY.md` — the "Choices made" section is a ready-made list of user-visible behavior changes from the audit remediation, already written in change-note register.
- `docs/adr/` — ADR-052 is new in this release; check for other ADRs added since June 10 and make sure anything they decided is reflected.
- `docs/development-process/loops/` and `docs/development-process/reviews/` — loop specs and reviews describe intent, which is often clearer than the commit.
- `docs/releases/v0.15.1.md` and earlier — the house format for release notes.
- Board card #50, which already contains a drafted set of changelog entries for the audit-remediation and L245 work. **Use those drafts; do not rewrite them from scratch.** They were reviewed.

## 1.2 CHANGELOG.md

Convert `[Unreleased]` into `## [0.16.0] — 2026-MM-DD` and fill it out for the whole range.

Format is Keep a Changelog, already in use. Categories, in this order, omitting any that are empty: **Breaking changes, Added, Changed, Deprecated, Removed, Fixed, Security.**

Rules for entries:

- **Group by user-visible outcome, not by commit.** Ten commits that together added the command registry are one entry, or at most three.
- **If a change has no user-visible effect, it does not get an entry.** Internal refactors, test additions, doc updates, dependency bumps that changed no behavior: all excluded. The changelog is for someone deciding whether to upgrade and what will break, not a development diary.
- **Hard cap: 60 entries total across all categories.** This is not a formatting suggestion. If you have more than 60, you are listing commits instead of changes, and the correct response is to merge related entries upward, not to request an exception. If something genuinely cannot fit under the cap, say so in the handoff and leave it out.
- One line per entry where possible, two if a consequence needs stating. No paragraphs.
- Write in the past tense, describing what changed for a user of the software.

**Register warning.** This release contains an external audit of the project and the author's own remediation of it. Do not write the changelog as a narrative about how much was fixed or how thorough the audit was. A reader wants to know what changed in the software. "Workflow tool nodes now pass through the capability gate before dispatch" is a changelog entry. "A comprehensive security audit identified and remediated critical gaps" is not.

## 1.3 UPGRADE.md

`UPGRADE.md` exists at the repo root, is well maintained, and has a clear per-version pattern: heading, released date, a one-line characterization, then numbered steps with real commands. Read the v0.15.1 and v0.15.0 sections and match that structure exactly.

Add a `## v0.16.0` section at the top of the version list. It must cover, at minimum:

**Breaking change 1: allowlist-only tool authorization (L245).** Every existing workflow must be re-activated once. Explain concretely: open each workflow, activate its current version, and confirm the authorization diff that appears. Migration m011 pre-populates grants from each workflow's active version at startup, so most users will see no diff and can simply confirm. Workflows with no active version get no grant and will need one before they can run.

**Breaking change 2: terminal environment allowlist.** Child processes spawned by the `terminal` tool now receive only `PATH`, `HOME`, `USER`, `SHELL`, `TERM`, `TMPDIR`, and locale variables. Any command that depended on an inherited environment variable will no longer see it. Verify the exact list against `src/hestia/tools/builtin/terminal.py` before writing it down; do not copy it from this spec.

**Breaking change 3: `ToolRegistry.call` requires a `ToolCallContext`.** Only relevant to anyone who has written external tool modules or calls the registry directly. Point at ADR-052.

Also cover the schema migration (m010, m011) in the terms the existing document uses: the migration model note at the top of `UPGRADE.md` already explains that `create_tables()` plus idempotent runtime migrations run on every startup, so the honest instruction is "restart and the migrations apply." Say which migrations are new and what they change, so an operator who watches their database knows what to expect.

Preserve the document's existing voice. It addresses the reader directly and gives commands they can paste.

## 1.4 docs/releases/v0.16.0.md

Match the existing per-release notes format (`docs/releases/v0.15.1.md`, `v0.15.0.md`). This is the longer-form companion to the changelog: what the release is about, the headline changes with a sentence of context each, the breaking changes with a pointer to `UPGRADE.md`, and known limitations.

Optional cleanup while you are here: `docs/releases/` has no `v0.14.0.md` although the tag exists. If you can reconstruct it honestly from the changelog, add it. If you cannot, note the gap in the handoff and leave it alone. **Do not invent release notes for a release you cannot verify.**

## 1.5 Version bump

`pyproject.toml` version to `0.16.0`. Report any other location carrying a version string.

---

# Phase 2: card #33 — security disclosure and threat model

Two problems, one blocking.

## 2.1 The disclosure address is a placeholder (blocking)

`SECURITY.md` currently reads:

> Please report security issues privately to the maintainers at [security@example.com](mailto:security@example.com).

**This is the single worst line in the repository to ship to a public audience.** It tells a researcher who found a real vulnerability that nobody is listening.

**DECIDED: replace it with GitHub private vulnerability reporting.** Rewrite the section to direct reporters to the repository's Security tab, using GitHub's "Report a vulnerability" flow. No email address goes in this file.

Keep the parts of the existing section that are still good: the request for a clear description, reproduction steps, affected versions, and suggested mitigations; the 72-hour acknowledgement target; and the request not to disclose publicly before a fix. Only the reporting channel changes.

Check the repository setting is actually enabled (see the dependency note at the top of this spec). If you cannot verify it, write the section as specified and flag the enablement step in the handoff. **Do not substitute an email address under any circumstances.**

## 2.2 The supported-versions table is stale

It lists 0.14.0 as the newest supported version. 0.15.1 shipped in June and 0.16.0 is this release. Rewrite the table against reality. Decide and state a simple policy, for example "the current minor series is supported," rather than enumerating versions that will go stale again in two months.

## 2.3 Threat model and hardening guide

`docs/guides/security.md` currently covers prompt-injection annotation and little else. Write a concise threat-model and hardening guide covering:

- **The trust and authorization model.** Capability gate, trust presets, channel classification (trusted vs unattended), and allowlist-only authorization for unattended channels. ADR-052 is authoritative and new; cite it.
- **Deployment posture.** Loopback versus exposed, the auth requirement, and the startup guard that refuses an insecure exposed configuration. Card #31 implemented this; `_validate_web_security_posture` is the function.
- **Filesystem and terminal risk**, honestly stated. Path checks are resolve-before-open. The terminal tool has an env allowlist, an output cap, and a timeout clamp. Say what that does and does not protect against.
- **Egress and SSRF.** ADR-045 is explicitly best-effort and acknowledges DNS-rebinding gaps. Say so plainly rather than implying stronger guarantees.
- **Config files execute Python.** `SECURITY.md` already notes this; make sure the guide covers what it means for anyone running a config file they did not write.

**Tone rule:** understate rather than overstate. This is a solo local-first project, not a hardened multi-tenant service. A security document that oversells is worse than one that admits limits, because the first thing a competent reader does is look for a claim they can disprove. Where a control is best-effort, say "best-effort" and say what it misses.

---

# Phase 3: card #34 — onboarding honesty

The test for this phase: a competent stranger clones the repo and gets to a working install without guessing.

## 3.1 README quick start

`README.md` line 87 says `git clone <repo-url>`. Replace with the real URL.

Rewrite Quick Start so it branches by what the reader wants to run, because the current single path does not match the dependency reality:

- **CLI only** — the minimum to have a conversation
- **Chat platforms** — Telegram and Matrix, plus what configuration each needs
- **Web dashboard** — including the SPA build step

State per mode which extras are required. `uv sync` does not pull all feature dependencies; check `[project.optional-dependencies]` in `pyproject.toml` and make the instructions match what each mode actually imports. Verify by reading the code paths, not by assuming the extras are named accurately.

## 3.2 Migration documentation conflict

The deploy documentation and the runtime-migration story disagree. `UPGRADE.md` states the production path is `create_tables()` plus idempotent runtime migrations, with Alembic present only for reference. Find the places that say otherwise and align them to that statement. Report every location you changed.

## 3.3 CI

`.github/workflows/ci.yml` exists and runs, on Python 3.11 and 3.12: SPA build, `ruff check src/`, `mypy src/hestia`, and `pytest tests/unit/ tests/integration/`. Two gaps:

- **Frontend tests never run in CI.** The workflow builds the SPA but never runs `vitest`. Add it.
- **`ruff` only lints `src/`.** The local gate is `ruff check src tests`. Align CI to the local gate so a lint failure in `tests/` cannot reach `develop`.

Consider whether `ruff format --check` belongs there too, and say what you decided.

Do not add jobs beyond closing these gaps. CI expansion is its own conversation.

## 3.4 Project metadata

`pyproject.toml` `[project]` has `authors = [{ name = "Dylan O'Keefe", email = "user@example.com" }]`.

**DECIDED: use `dylanokeefedev@gmail.com`.** It is already the git author identity on every commit in the repository, so this is not new exposure.

Add the standard metadata a reader and a package index expect: `keywords`, `classifiers`, and a `[project.urls]` table pointing at the repository, issue tracker, and documentation. Do not publish to PyPI as part of this loop; that is a separate decision.

---

---

# Phase 4: card #35 — stop shipping the operator's persona

`SOUL.md` in the public repository is Dylan's own operator-specific persona content (the "Silas" persona). It is not a defect in the software, but it is personal configuration sitting in a repo strangers are about to read, and it gives a new user a confusing starting point: they clone the project and inherit somebody else's assistant.

**This mirrors an existing pattern in the repo.** Card #14 did exactly this for `config.runtime.py`: untracked the real file, gitignored it, and shipped `config.runtime.example.py` with safe defaults. Follow that precedent rather than inventing an approach.

Steps:

1. Read `config.runtime.example.py` and how `config.runtime.py` is gitignored. Mirror that structure.
2. Write `SOUL.example.md`: a sanitized, generic persona that demonstrates the format and the available knobs without carrying Dylan's personal content. It should be usable as-is by someone who just cloned the repo, and obviously a starting point rather than a finished character.
3. Untrack the real file: `git rm --cached SOUL.md`, and add `SOUL.md` to `.gitignore`.
4. Check how `SOUL.md` is loaded. If a missing file crashes or silently degrades, make the loader fall back to `SOUL.example.md` with a clear log line, or fail with a message that names the file to create. A fresh clone must not break.
5. Document it wherever the config files are documented, including the README quick start from Phase 3.

**Critical care point.** `SOUL.md` is live configuration for Dylan's running instance. `git rm --cached` removes it from tracking while leaving it on disk, which is what you want, but verify that is what happened before moving on: the file must still exist in the working tree afterwards. Report explicitly in the handoff that you confirmed the file is still present on disk and that only its tracking changed.

If anything about the loader's behavior on a missing `SOUL.md` is ambiguous, describe what you found and stop rather than guessing. Breaking the persona load on a live assistant is a worse outcome than shipping the file for one more release.

---

# Phase 5: setup honesty (added 2026-08-24, post-Phase-4)

Two unrelated problems, both of which make a fresh install lie to the person doing it. Grouped because they ship together and both are release-blocking for a release whose purpose is that a stranger can follow the docs successfully.

- **5A** — three starter personas disagree
- **5B** — the instance starts up without saying what it could not find

## 5A: three starter personas disagree

Phase 4 created `SOUL.example.md` without noticing two other starter personas already existed. There are now three, with different content:

| Where | Size | Origin | Who gets it |
|---|---|---|---|
| `SOUL.example.md` (root) | 1607 B | new, Phase 4 | anyone following the README's copy instruction |
| `deploy/SOUL.md.example` | 753 B | Apr 30, commit `dd74dd6` | nobody; unreferenced |
| `_SOUL_TEMPLATE` in `src/hestia/commands/admin.py` | — | Apr 30, same commit | **anyone running the documented `hestia init --with-soul`** |

So the two documented onboarding paths hand a new user two different personas, in the release whose stated purpose is that a stranger can follow the docs and get a working install. That is a first-five-minutes defect in exactly the area Phase 3 covers, which is why it is in this loop rather than a follow-up card.

## The packaging constraint decides the design

`pyproject.toml` uses the `uv_build` backend with no package-data configuration, so the wheel contains `src/hestia/` and nothing else. Root-level `SOUL.example.md` and `deploy/` are **not** in an installed package.

That is why `_SOUL_TEMPLATE` is a Python string constant: it is the only copy an installed `hestia init --with-soul` can reach. **Do not "simplify" by having init read the root file.** That breaks every non-clone install, and the breakage is invisible from a source checkout, which is where you will be testing.

**Verify this claim before relying on it.** Build a wheel (`uv build`) and list its contents. If root markdown files turn out to be included, say so and the design below can be simplified. If they are not, proceed as specified.

## Required shape

One canonical text, shipped inside the package, plus a detector on any convenience copy.

1. Move the canonical starter persona to `src/hestia/data/SOUL.example.md` (or the nearest existing convention for package data; check whether one exists before inventing a directory). Content should be Phase 4's 1607-byte version, which is the sanitized one written for this release.
2. `_SOUL_TEMPLATE` is replaced by a read of that packaged file. Confirm it still works from an installed wheel, not only from the source tree.
3. Keep `SOUL.example.md` at the repo root. It is worth having for someone browsing the repository on GitHub, which is a real audience for this release. It is a convenience copy, not a second source.
4. **Add a test asserting the root copy is byte-identical to the packaged canonical file.** This is the detector. Duplication that cannot be removed gets a test that fails when the copies drift, rather than a comment asking people to be careful.
5. Delete `deploy/SOUL.md.example`. Stale, unreferenced, and contradicts both others.
6. Make sure the README's instruction and `hestia init --with-soul` now produce the same persona, and say which one the README recommends.

## If the design does not work out

If packaged data turns out to be awkward with `uv_build`, the acceptable fallback is: `_SOUL_TEMPLATE` stays the canonical text, `SOUL.example.md` is asserted identical to it by a test, and `deploy/SOUL.md.example` is still deleted. That is two copies with a detector rather than one copy, which is worse but not much worse. **Do not** ship three, and do not ship two without the test.

Report which shape you landed on and why.

---

## 5B: startup does not say what it could not find

`_warn_on_missing_files` in `app.py` covers exactly two things: `SOUL.md` and `docs/calibration.json`. Everything else that is gitignored and required is silently absent. Two cases matter.

### 5B-1: missing platform credentials

`deploy/hestia-serve.service` sets `EnvironmentFile=%h/Hestia-runtime/.env`, and `.env` is gitignored. Without it the instance boots **degraded**: enabled platforms have no credentials, and Hestia itself says nothing.

**Do not implement this as a check for `.env`.** That file is a systemd deployment detail, not Hestia's. Hestia never reads it; systemd reads it and hands Hestia environment variables. Someone running from the CLI, from a container, or with credentials exported another way has no `.env` and is perfectly fine, and warning them would be a false alarm that trains people to ignore the warnings.

Check the actual precondition instead: **for each platform enabled in config, is the credential it needs actually present and non-empty?** Telegram enabled with no bot token is the real defect; the absence of a particular file is not.

Behavior: warn per platform, name the platform and the missing variable, and continue. Do not fail startup. Someone may deliberately run with one adapter unconfigured.

Verify how each adapter currently obtains its credentials before writing the check. Do not assume every platform reads an environment variable, or that they share a naming convention.

### 5B-2: silently empty database

`runtime-data/` is gitignored, so a fresh deploy comes up with an empty database and no comment. Empty is **correct** on a genuine first install, so this must not be an error and must not block startup. The problem is that nothing distinguishes "first install" from "deployed to the wrong path and my history is somewhere else."

Behavior: when the database file does not exist at the resolved path, emit one line at startup naming the **full resolved path** it is creating. The path is the whole point; "creating a new database" without it tells a person nothing about why theirs is missing.

Wording should read as unremarkable on a first install and informative to someone who expected data. Something in the shape of "No existing database at /full/path — creating a new one." Avoid alarm words; this is the normal first-run path.

### Both

- These are `app.py` changes. Gates apply, and the whole-tree command with its count goes in the handoff.
- Add a test for each: a config with an enabled platform and no credential produces the warning; an absent database file produces the path line. Drive the real startup path, do not reimplement the check in the test.
- If `_warn_on_missing_files` is now doing more than its name says, rename it. A function called `_warn_on_missing_files` that also validates credentials is the kind of small dishonesty that makes the next reader miss a case.
- Keep it to these two. Do not audit the rest of `.gitignore` and add warnings for everything; `.matrix.secrets.py` is optional by design and needs nothing.

## Guardrails

These are not optional and they exist because of specific, observed failure modes.

**1. Verify every citation.** In previous loops this model stated that the tool `search_web` did not exist when it does, and attributed a finding to SEC-004 when SEC-004 was a different finding entirely. A changelog and a security guide are almost entirely citations: file paths, symbol names, ADR numbers, version numbers, finding IDs. **Grep for every name before you write it down.** If you cannot verify a claim, do not make it.

**2. Do not invent placeholders' replacements.** Two placeholders in this loop, `security@example.com` and `user@example.com`, need a human answer. Mark them, flag them, move on.

**3. Do not pad.** The 60-entry changelog cap is real. So is the instruction to omit changes with no user-visible effect. Volume is not thoroughness here; it is the opposite, because it buries the three things a reader actually needs to know.

**4. Documentation must match shipped code, not intent.** Before describing a behavior, read the code that implements it. The terminal environment allowlist in this spec is a worked example: verify it against `terminal.py` rather than copying it from here.

**5. Report what you did not do.** Anything skipped, any gap you found and left alone, any place where the code and the documentation disagreed in a way you could not resolve. A named gap is a finding; a silent one is a defect.

**6. Do not overwrite the board card's note.** Append a delivery report under its own heading at the bottom. On 2026-08-23 a completion summary replaced an entire card, destroying its scope and review history.

**7. No merge or push to `develop` or `main` without Dylan's approval.** Land the work on `docs/release-0.16.0`, push the branch, and stop.

## Definition of done

- [ ] Preconditions verified and recorded (L245 merged, gate numbers captured)
- [ ] `CHANGELOG.md` `[0.16.0]` covers 2026-06-10 to now, under the 60-entry cap, breaking changes first
- [ ] `UPGRADE.md` has a v0.16.0 section matching the existing structure, with all three breaking changes and the migration note
- [ ] `docs/releases/v0.16.0.md` written in the house format
- [ ] `pyproject.toml` at 0.16.0, other version strings reported
- [ ] `SECURITY.md` disclosure path resolved or flagged as blocking, supported-versions table corrected
- [ ] `docs/guides/security.md` threat model and hardening guide written, best-effort controls labeled as such
- [ ] `README.md` clone URL fixed, Quick Start split by mode, extras verified against the code
- [ ] Migration documentation conflict resolved, locations listed
- [ ] CI runs vitest and lints `tests/`
- [ ] `pyproject.toml` metadata added, author email set to dylanokeefedev@gmail.com
- [ ] `SOUL.example.md` written, `SOUL.md` untracked and gitignored, loader handles a missing file, working-tree copy confirmed still present
- [ ] 5A: wheel contents checked; one canonical starter persona shipped in the package; root copy pinned by a byte-identical test; `deploy/SOUL.md.example` deleted; README instruction and `hestia init --with-soul` agree
- [ ] 5B-1: per-platform credential check (NOT a `.env` file check), warns and continues, one test
- [ ] 5B-2: absent database emits one line naming the full resolved path, does not block startup, one test
- [ ] `_warn_on_missing_files` renamed if it now does more than its name says
- [ ] Gates green on the final commit, numbers recorded
- [ ] Handoff written to `docs/handoffs/`, including everything skipped and every unresolved placeholder
- [ ] Branch pushed, card #51 updated by appending, nothing merged

## Explicitly out of scope

- Publishing to PyPI
- Tagging the release or merging to `main` (Dylan does this)
- Any code change beyond the CI workflow, `pyproject.toml`, the SOUL loader and packaging (5A), the startup checks named in 5B, and the sanctioned calibration-path fix
- Auditing the rest of `.gitignore` for missing-file warnings. 5B covers exactly two cases and stops there.
- Deciding the 1.0 question (0.16.0 is settled for this release; 1.0 is a separate deliberate call)
- Enabling GitHub private vulnerability reporting in repository settings, which only Dylan can do
- Card #45 (L246, test-blindness audit) and card #47 (small cleanups), which are separate loops

## Cards closed by this loop

#52 (this loop), #33 (security docs), #34 (onboarding honesty), #35 (SOUL.example.md), #50 (changelog). Update all five when the branch is ready; move them to In Review, not Done.


## Merged (2026-08-24)

Dylan approved merge. `docs/release-0.16.0` merged into develop as
4bad5dd7 and pushed. Gates on the merge commit (command reported):
`uv run pytest -q` -> 2,356 passed / 12 skipped / 0 failed; ruff clean.
Remaining pre-tag actions are Dylan's: enable GitHub private vulnerability
reporting, tag v0.16.0, merge develop -> main.
