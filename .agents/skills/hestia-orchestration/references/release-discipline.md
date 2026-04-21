# Release Discipline

## Rule

After a release tag is placed on `develop` (and especially after that tag has been pushed to `origin`), **do not merge any further feature branches into `develop`** until a new release-prep document exists — a file under `docs/development-process/prompts/` or `docs/development-process/reviews/` that **names the upcoming version and lists, by exact `feature/*` branch name, every loop going into it**.

The release-prep doc is the authoritative scope. A branch that is not listed by exact name in the doc does **not** merge, even if it is on the same overall train, shares a theme with other listed branches, or has `.kimi-done` and a handoff. Thematic affinity is not authorization.

## During the post-release window

- Feature branches are fine. Work may continue on them.
- Merging those branches into `develop` is **forbidden** until the next release-prep doc exists and names them.
- Loop completion means: feature branch pushed to origin, handoff written, `KIMI_CURRENT.md` advanced. It does **NOT** mean merged to `develop`.

## Allowed exceptions

No release-prep doc needed for:
- Pre-tag hotfixes that are themselves part of the in-flight release
- Pure planning/spec docs under `docs/development-process/` (loop specs, ADRs, queue updates, release-prep docs themselves)
- `.cursorrules` and `AGENTS.md` policy updates

## Correct behavior example

1. `v0.8.0` tagged at `develop` tip.
2. Kimi runs L36 on `feature/l36-app-commands-split`. Branch pushed.
3. Kimi runs L37 on `feature/l37-cleanup-sweep`. Branch pushed.
4. Do **NOT** merge L36 or L37 to `develop`.
5. Dylan opens `v0.8.1` release prep. Cursor drafts `v0.8.1-release-prep.md` listing BY EXACT NAME:
   - `feature/l36-app-commands-split`
   - `feature/l37-cleanup-sweep`
6. On Dylan's sign-off, merge the two named branches to `develop` and tag `v0.8.1`.

## Incorrect behavior example

1. `v0.8.0` tagged and pushed.
2. Feature branches `feature/l40-copilot-cleanup`, `feature/voice-shared-infra`, `feature/voice-phase-a-messages` all complete and pushed.
3. Write `v0.8.x-multi-user-safety-release-prep.md` listing ONLY the L45 branches by name.
4. Merge all six branches to `develop`, bump version to 0.9.0 — on the theory that the L45 doc implicitly authorizes the "v0.9.0 train" as a whole.
5. The mistake: four branches merged without being named in any release-prep doc.

## Release sequence

1. Write release-prep doc naming all branches
2. Get Dylan's sign-off on scope
3. Merge named branches to `develop` in order
4. Bump version in `pyproject.toml`
5. Update `CHANGELOG.md`
6. Place annotated tag: `git tag -a vX.Y.Z -m "..."`
7. Fast-forward `main` to `develop`
8. Dylan pushes: `git push origin develop main vX.Y.Z`
