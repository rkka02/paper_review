# Repository Guidelines

This repository currently contains early product/design notes for a personal “paper review” system (PDF/DOI ingestion → structured review output). There is no application source code yet; contributions are primarily documentation and planning artifacts.

## Project Structure & Module Organization

- `main.txt`: primary specification/backlog notes.
- Repo metadata: `.gitignore`, `LICENSE`.
- Suggested (when needed): `docs/` for design notes, `src/` for implementation, `tests/` for automated tests, `assets/` for diagrams/figures.

## Build, Test, and Development Commands

- No build/test commands are defined yet.
- If you introduce runnable code, add the canonical commands to `README.md` and keep them reproducible (examples: `python -m venv .venv`, `pytest`, `ruff check .`).

## Coding Style & Naming Conventions

- Prefer Markdown (`.md`) for new documents; keep sections short and use headings.
- Use UTF-8 for all text files (especially Korean) to avoid encoding issues.
- File naming: `docs/<topic>.md` or `docs/YYYY-MM-DD-<topic>.md`; lowercase with hyphens.
- If adding Python code, follow PEP 8 (4-space indentation, `snake_case`, type hints where practical).

## Testing Guidelines

- No testing framework is configured yet.
- If adding code, include tests alongside features (recommended: `tests/test_<module>.py`) and document how to run them.

## Commit & Pull Request Guidelines

- Git history currently only contains `Initial commit`; no established commit convention.
- Use clear, imperative messages; recommended: Conventional Commits (`docs: ...`, `feat: ...`, `fix: ...`).
- PRs should explain intent, scope, and tradeoffs; link issues/spec sections; include screenshots for UI/mock changes.

## Security & Configuration Tips

- Never commit secrets (OpenAI keys, Google OAuth credentials). Use `.env` files (already ignored) and document required variables in `README.md` (or `docs/config.md`).

## Agent-Specific Instructions

- Make small, reviewable diffs; avoid reorganizing files unless requested.
- When editing existing text, preserve language and meaning; keep UTF-8 encoding.
