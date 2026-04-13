# Contributing to Hestia

## Quick start

```bash
uv sync && uv run pytest tests/unit/ tests/integration/ -q
```

## Code style

- **Ruff** for linting and formatting
- **mypy** for type checking

Run before submitting:

```bash
uv run ruff check src/
uv run mypy src/hestia/
```

## Branch model

- Feature branches from `develop`
- PRs merge into `develop`
- `main` is for releases
- Use gitflow naming: `feature/*`, `release/*`, `hotfix/*`

## Testing

All new code needs tests.

```bash
uv run pytest tests/unit/ tests/integration/ -q
```

Use `pytest-asyncio` for async tests.

## Commit messages

Conventional commits are preferred:

- `feat:` — new feature
- `fix:` — bug fix
- `docs:` — documentation
- `test:` — tests
- `refactor:` — code restructuring

## Reporting bugs

Open a GitHub issue with:

1. Reproduction steps
2. Expected vs actual behavior
3. System info (Python version, GPU, llama.cpp version)

## Design decisions

Major changes should include an ADR in `docs/adr/`. Read `docs/DECISIONS.md` for existing decisions.
