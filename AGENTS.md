# AGENTS.md

This file provides guidance to Codex and other coding agents when working with code in this repository.

## Project Overview

Pinterest public board downloader: downloads pins from public Pinterest boards (other users' public collections). Python 3.11+.

## Development Setup

Package manager: **uv**. Run project commands through `uv`.

```bash
uv sync
uv run python main.py
uv run pytest
uv run pytest tests/test_example.py
uv run pytest tests/test_example.py::test_func
uv run ruff format .
uv run ruff check .
uv run mypy .
```

No test framework is configured yet. If you add one, declare `pytest`, `ruff`, and `mypy` as dev dependencies in `pyproject.toml`.

## Architecture

Active Pinterest scraping currently works through only two mechanisms. Do not rely on a public official API.

1. `#__PWS_INITIAL_PROPS__` SSR blob
   Pinterest injects JSON into each page. `initialReduxState` contains boards, pins, users, and images. Parse HTML to get initial data.
2. `/resource/<Resource>Resource/get/` XHR endpoints
   Pinterest internal web API used for pagination and search. Requires XHR headers such as `X-Requested-With` and `X-Pinterest-AppState`, plus session cookies. Important resources include `BoardsResource`, `BoardFeedResource`, `UserPinsResource`, and `BaseSearchResource`. Pagination uses `bookmarks` arrays, and the end indicator is `"-end-"`.

Dead APIs: v3 pidgets (`/v3/pidgets/...`) and `pinterestapi.co.uk` no longer work.

## Reference Projects

Use `reference_project/` for study and pattern comparison, not direct copying.

| Project | Language | Key takeaway |
|---------|----------|--------------|
| `pinterest-downloader` | Python | Primary reference. Uses `requests` + `BeautifulSoup`, SSR parsing, XHR endpoints, image size extraction, and pin/video/story-pin handling. See `pinterest_downloader/pinterest.py`. |
| `Pinterest-LocalBoard` | JavaScript (Chrome extension) | Board detection heuristics, `237x` -> `originals` URL derivation, concurrent download with retry, ZIP packaging. |
| `pinback` | JavaScript bookmarklet | `/resource/` XHR pagination patterns, especially `BoardsResource`. |
| `Pinterest-API` / `Pinwatcher` | PHP | Outdated. These rely on dead APIs only. |

## Key Implementation Details

- Image URLs use size variants such as `237x`, `474x`, `736x`, and `originals`. Swapping the size path segment can derive alternate resolutions.
- Pin data generally lives under `initialReduxState.pins[pinId].data`, including `images`, `media_type`, `story_pin_data`, and `videos.video_list`.
- Board context lives in the `boards` dictionary keyed by board ID, with fields such as `url`, `name`, `pin_count`, `privacy`, and `cover`.

## Python Coding Conventions

### Syntax and Types

- Target Python 3.11+.
- Prefer `pathlib.Path`, f-strings, and `dataclasses`.
- Use modern type syntax: `T | None`, `list[str]`, `dict[str, str]`.
- Add type hints to public functions and non-trivial internal functions.
- Prefer precise types over `Any`.
- Keep `mypy` clean.

### Docstrings and Comments

- Add a meaningful module docstring to every Python file.
- Use Google-style docstrings for public APIs with `Args`, `Returns`, and `Raises` where relevant.
- Inline comments should explain why, not what.

### Naming and Structure

- Use `snake_case` for modules, functions, and variables.
- Use `PascalCase` for classes.
- Use `UPPER_SNAKE_CASE` for constants.
- Prefix private helpers with `_` when appropriate.
- Prefer small functions with one responsibility.
- Prefer explicit parameters over hidden global state.
- Prefer early returns over deep nesting.
- Keep imports ordered as: future, standard library, third-party, local.
- Do not use wildcard imports.
- Remove unused imports.

### Error Handling and Logging

- Catch specific exceptions, never bare `except`.
- Preserve exception chains when wrapping errors with additional context.
- Use `logging.getLogger(__name__)`.
- Use log levels intentionally: `debug` for diagnostics, `info` for progress, `warning` for recoverable issues, `error` for failures.
- Do not use `print()` in library code.

### Testing

- Favor focused unit tests over end-to-end tests.
- Keep tests deterministic and avoid external network access unless truly required.
- Use fixtures for shared setup.
- Add regression tests for bug fixes.
- Before considering work complete, run:
  - `uv run ruff check .`
  - `uv run ruff format .`
  - `uv run mypy .`
  - `uv run pytest`

### Dependencies

- Prefer the Python standard library when practical.
- Do not add a dependency for a very small helper.
- Keep runtime and development dependencies separate in `pyproject.toml`.

## Agent Working Rules

- Read and follow this file before making code changes.
- Preserve the repository's existing structure and patterns unless the task clearly requires change.
- When implementing Pinterest scraping logic, prefer the two known working mechanisms above and avoid reviving deprecated API paths.
- When using reference code, adapt ideas to this repository instead of copying code wholesale.
- If you add tests or tooling, wire them through `uv`.
