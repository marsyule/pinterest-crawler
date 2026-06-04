# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Pinterest public board downloader — downloads pins from public Pinterest boards (others' public collections). Python 3.11+.

## Development Setup

Package manager: **uv**. All commands go through `uv`.

```bash
uv sync                  # Install dependencies
uv run python main.py    # Run the project
uv run pytest            # Run all tests
uv run pytest tests/test_example.py              # Single file
uv run pytest tests/test_example.py::test_func   # Single test
uv run ruff format .     # Format code
uv run ruff check .      # Lint code
uv run mypy .            # Type check
```

No test framework configured yet. When adding, declare `pytest`, `ruff`, and `mypy` as dev dependencies in `pyproject.toml`.

## Architecture

**Active Pinterest scraping only works through two mechanisms** — no official public API:

1. **`#__PWS_INITIAL_PROPS__` SSR blob** — Pinterest injects JSON into every page with `initialReduxState` containing boards, pins, users, and images. Parse from HTML for initial data.
2. **`/resource/<Resource>Resource/get/` XHR endpoints** — Internal web API for pagination/search. Requires XHR headers (`X-Requested-With`, `X-Pinterest-AppState`) and session cookies. Key resources: `BoardsResource`, `BoardFeedResource`, `UserPinsResource`, `BaseSearchResource`. Pagination uses `bookmarks` arrays; end indicator is `"-end-"`.

**Dead APIs** — v3 pidgets (`/v3/pidgets/...`) and `pinterestapi.co.uk` no longer exist.

## Reference Projects

`reference_project/` — study patterns but don't copy directly:

| Project | Language | Key takeaway |
|---------|----------|-------------|
| **pinterest-downloader** | Python | **Primary reference.** `requests`+`BeautifulSoup`, SSR parsing, XHR endpoints, image size extraction, pin/video/story-pin handling. See `pinterest_downloader/pinterest.py`. |
| **Pinterest-LocalBoard** | JS (Chrome Ext) | Board detection heuristics, `237x`→`originals` URL derivation, concurrent download with retry, ZIP packaging. |
| **pinback** | JS Bookmarklet | `/resource/` XHR pagination patterns, `BoardsResource` usage. |
| **Pinterest-API** / **Pinwatcher** | PHP | **Outdated** — dead APIs only. |

## Key Implementation Details

- **Image URLs**: Size variants (`237x`, `474x`, `736x`, `originals`). Replace size path segment for different resolutions.
- **Pin data**: `initialReduxState.pins[pinId].data` — `images` dict keyed by size, `media_type`, `story_pin_data`, `videos.video_list`.
- **Board context**: `boards` dict keyed by board ID with `url`, `name`, `pin_count`, `privacy`, `cover`.

---

## Python Coding Conventions

### Syntax & Types

- Target Python 3.11+. Use `pathlib.Path`, f-strings, `dataclasses`.
- Use modern union syntax: `T | None` instead of `Optional[T]`, `list[str]` instead of `List[str]`.
- Add type hints to public functions and non-trivial internals. Prefer precise types over `Any`.
- Run `mypy` as part of CI checks — keep type checking clean.

### Docstrings & Comments

- **Module docstring** in every file: one sentence minimum. No `"""This is a Python file."""`.
- **Google-style docstrings** for public APIs with `Args`, `Returns`, `Raises`.
- **Inline comments**: only explain **why**, never **what**.

```python
# Good — explains why
# Pinterest returns 204 with empty body for successful deletes
if response.status_code == 204:
    return None
```

### Naming & Structure

- `snake_case` for modules/functions/variables, `PascalCase` for classes, `UPPER_SNAKE_CASE` for constants, `_prefix` for private.
- One responsibility per function. Explicit parameters over global state. Early returns over deep nesting.
- Import order: future → stdlib → third-party → local. No wildcard imports. Remove unused imports.

### Error Handling & Logging

- Catch specific exceptions — never bare `except`. No silent swallows.
- Wrap errors with context and preserve chain:

```python
try:
    data = json.loads(raw_text)
except json.JSONDecodeError as exc:
    raise ConfigError(f"Invalid JSON config: {path}") from exc
```

- Use `logging.getLogger(__name__)`. Levels: `debug` (diagnostics), `info` (progress), `warning` (recoverable), `error` (failures). No `print()` in library code.

### Testing

- Focused unit tests over e2e. Deterministic — no external network unless required. Use fixtures for shared data.
- Add regression tests for bug fixes.
- Run `uv run ruff check .`, `uv run ruff format .`, `uv run mypy .`, and `uv run pytest` before considering work done.

### Dependencies

- Prefer stdlib. Don't add a dependency for a small helper. Separate runtime from dev dependencies in `pyproject.toml`.