# L35 pre-release fixes arc handoff

L35a → L35b → L35c → L35d. Four mini-loops fixing pre-release bugs and
adding the upgrade checklist before the v0.8.0 tag.

## Loop manifest

| Loop | Branch | Merge commit | Lines changed | Tests added |
|------|--------|--------------|---------------|-------------|
| L35a | `feature/l35a-style-and-overhead-fixes` | `2575152` | +320 / −38 | 6 |
| L35b | `feature/l35b-policy-show-wiring` | `852d546` | +195 / −5 | 6 |
| L35c | `feature/l35c-hestia-doctor` | `71ea99f` | +959 / 0 | 24 |
| L35d | `feature/l35d-upgrade-doc-and-release-prep` | TBD | docs only | 0 |

## Why split

L29, L30, and L31 all hit the per-iteration step ceiling (`--max-steps-per-turn`)
when executed as monolithic loops. L32 and L33 validated that sub-letter
mini-loops (≤5 commits, single theme, one new test module) fit comfortably
under the ceiling and execute autonomously. L35 was split into four mini-loops
for the same reason: `hestia doctor` alone is nine checks × two test paths
plus a new module and CLI integration — the exact shape that broke L29–L31.
The docs amendment (L35d) was sequenced last because it depends on all prior
L35 changes being merged to `develop`.

## What shipped per loop

**L35a**
- Fixed `style disable` Click signature (`@click.pass_obj`, process-only docstring).
- Cached `ContextBuilder._join_overhead` lazily across builds; edge-case guard
  prevents caching a `0` from too-few-messages.
- Regression tests lock both fixes.

**L35b**
- Derived `_cmd_policy_show` from live tool registry and `PolicyConfig` instead
  of hand-written strings.
- Added `TrustConfig.preset` field and `DefaultPolicyEngine.retry_max_attempts`.
- Regression tests lock the wiring.

**L35c**
- `src/hestia/doctor.py` with nine read-only health checks and `--plain` output.
- `hestia doctor` CLI registration; returns non-zero when any check fails.
- 18 unit tests (green/red per check) + 4 CLI end-to-end tests.

**L35d**
- `UPGRADE.md` checklist for v0.2.2 → v0.8.0 (back up, pull, config additions,
  dependency notes, CLI changes, `hestia doctor` verification, first run).
- Amended `[0.8.0]` CHANGELOG with L35a–c bullets, new diagnostic commands,
  and upgrade docs subsections.

## Test counts

- Before L35a: **741 passed, 6 skipped**
- After L35d: **~778 passed, 6 skipped**
- Mypy: **0** errors
- Ruff: **44** errors baseline held

## Cursor's release actions (next)

Per Stage B of `docs/development-process/reviews/v0.8.0-pre-release-plan.md`:

- Verify this branch merges to `develop` cleanly with CI green.
- Re-tag `v0.8.0` at the post-L35d `develop` tip.
- `git checkout main && git merge --ff-only develop`
- Hand Dylan the three push commands:
  ```bash
  git push origin develop
  git push origin main
  git push origin v0.8.0
  ```

## Process notes

- Mini-loop chunking continues to work: all four loops executed autonomously
  without hitting the step ceiling.
- The `_join_overhead` cache edge case (don't cache `0` from too-few-messages)
  was subtle and correctly handled in L35a.
- No production code changes in L35d; docs-only loop kept the risk surface
  at zero.
