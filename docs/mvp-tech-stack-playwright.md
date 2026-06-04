# 0.1.0 Implementation Scope With Playwright

This document defines the current `0.1.0` implementation scope for the Pinterest public board downloader. It builds on `docs/pinterest-board-crawl-plan.md`, which has verified both the single-board crawl path and user-profile board discovery.

## Goal

Build a small, reliable `0.1.0` baseline that can download images from a public Pinterest board while excluding recommendation content appended after the board's own pins.

The current `0.1.0` scope includes:

- v1: single public board download.
- v1.1: resumable downloads, retry, image URL fallback, and incremental manifests.
- v1.2: user profile input that discovers public boards and downloads each board.

The downloader should:

- Accept a public board URL.
- Accept a public user profile URL and discover public board URLs.
- Resolve board metadata from Pinterest SSR data.
- Resolve public boards from a user profile's `initialReduxState.boards`.
- Collect board pins from SSR `BoardFeedResource` and paginated `BoardFeedResource` XHR calls.
- Filter out non-board and recommendation items at the data level.
- Select the best available image URL for each pin.
- Retry transient image failures and fall back through lower-ranked image candidates.
- Download images to a local output directory.
- Save per-board manifests so interrupted runs can be inspected and resumed.
- Save a user-level manifest for batch user-profile downloads.
- Use Playwright as a bootstrap and fallback layer when plain HTTP cannot obtain usable page data or cookies.

## Recommended Stack

### Runtime

- Python 3.11+
- `uv` for dependency and command management

### Naming Conventions

- Project/package distribution name: `pinterest-crawler`
- CLI command: `pinterest-crawler`
- Python import package: `pinterest_crawler`
- Default config file: `pinterest-crawler.yaml`

Python is the right default because the verified plan is mostly HTTP requests, JSON parsing, filesystem writes, and deterministic tests. It also keeps the implementation close to the existing reference project and repository conventions.

### Core Dependencies

- `httpx`: HTTP session, cookie reuse, XHR pagination, and image downloads.
- `beautifulsoup4`: extraction of `#__PWS_INITIAL_PROPS__` from Pinterest HTML.
- `playwright`: browser bootstrap fallback for difficult pages, cookie capture, and optional DOM boundary inspection.

### Development Dependencies

- `pytest`: focused unit and integration-style tests using local fixtures.
- `ruff`: formatting and linting.
- `mypy`: static type checks.

### Deferred Dependencies

Do not add these in `0.1.0` unless a concrete need appears:

- `typer`: useful later if the CLI grows beyond a few commands.
- `rich`: useful later for better progress displays.
- `pydantic`: useful later if external config and manifest schemas become large.
- `sqlite`: useful later for many-board job history, retry queues, or large resumable crawls.

## Architecture

The `0.1.0` implementation should stay modular but small.

```text
pinterest_crawler/
  __init__.py
  cli.py
  models.py
  http_client.py
  ssr.py
  board_feed.py
  images.py
  manifest.py
  downloader.py
  user_boards.py
  user_downloader.py
  playwright_bootstrap.py
tests/
  fixtures/
  test_ssr.py
  test_board_feed.py
  test_images.py
  test_manifest.py
  test_user_boards.py
  test_user_downloader.py
  test_cli.py
```

### `cli.py`

Owns argument parsing and user-facing command flow.

Initial command shape:

```bash
uv run pinterest-crawler download https://www.pinterest.com/<user>/<board>/ --out downloads/<board>
```

Module entry point shape, useful when the console script is not installed:

```bash
uv run python -m pinterest_crawler.cli download https://www.pinterest.com/<user>/<board>/ --out downloads/<board>
```

User-profile batch command:

```bash
uv run python -m pinterest_crawler.cli download-user https://www.pinterest.com/<user>/ --out downloads/<user>
```

Useful `0.1.0` options:

- `--out`: output directory.
- `--page-size`: pagination page size, default `15`.
- `--use-playwright`: force browser bootstrap.
- `--no-playwright`: fail instead of falling back to browser bootstrap.
- `--overwrite`: re-download images that already exist.
- `--retries`: retry each image candidate after transient failures, default `2`.

The `download-user` command reuses the same options and passes them to each board crawl.

### `http_client.py`

Owns browser-like headers, cookie persistence for one crawl session, request timeouts, and retry behavior.

Responsibilities:

- Fetch the board HTML.
- Fetch user profile HTML.
- Call `/resource/BoardFeedResource/get/`.
- Download image bytes.
- Keep one session per crawl so cookies from the board page are reused.

### `ssr.py`

Extracts and parses Pinterest SSR state from:

```html
<script id="__PWS_INITIAL_PROPS__">...</script>
```

Responsibilities:

- Parse HTML into JSON.
- Locate `initialReduxState`.
- Resolve the current board by URL or board ID.
- Locate the initial `BoardFeedResource` payload and bookmark.

### `user_boards.py`

Discovers public boards from a user profile page.

Responsibilities:

- Normalize user profile URLs such as `https://www.pinterest.com/adryanlong/`.
- Parse profile SSR HTML with the shared `#__PWS_INITIAL_PROPS__` extractor.
- Read `initialReduxState.boards`.
- Keep only public boards with usable `id`, `name`, and `url` fields.
- Convert board paths like `/adryanlong/coastal-calm/` into absolute board URLs.
- Deduplicate boards by ID while preserving SSR order.

### `board_feed.py`

Owns board feed pagination and item filtering.

The minimal correctness rule from the crawl plan stays central:

```python
item.get("type") == "pin"
and str((item.get("board") or {}).get("id")) == board_id
and best_image_url is not None
```

Responsibilities:

- Build `BoardFeedResource` request payloads.
- Include required XHR headers, especially `X-Pinterest-PWS-Handler`.
- Stop when bookmarks equal `["-end-"]`.
- Exclude recommendation, interest, story, and non-board items unless they resolve to a real pin owned by the target board.

### `images.py`

Extracts and ranks image candidates.

Candidate order:

1. `images.orig.url`
2. `images.originals.url`
3. `images["1200x"].url`
4. `images["736x"].url`
5. `images["474x"].url`
6. `images["236x"].url`
7. Story Pin image candidates from `story_pin_data.pages[].blocks[]`

If no original URL exists, the `0.1.0` implementation may derive an `/originals/` URL from an `i.pinimg.com` size URL, but it must fall back to the verified size URL if the derived URL returns `403` or `404`.

### `manifest.py`

Saves crawl state and download results.

Use JSON for `0.1.0`. Prefer one manifest per board output directory:

```text
downloads/<board-slug>/manifest.json
```

Manifest should include:

- Board URL, ID, name, slug, pin count, and privacy.
- Pin ID.
- Source pin URL.
- Image candidates.
- Selected image URL.
- Attempted image URLs.
- Local file path.
- Download status.
- Error message, if any.

Historical `v1.1` resume behavior, now included in `0.1.0`:

- Load an existing `manifest.json` when crawling the same board.
- Reuse successful records when the local file still exists and `--overwrite` is not set.
- Retry failed records and missing files.
- Save the manifest after each processed pin so interrupted runs keep completed work.
- Keep old manifests readable when they do not have newer fields such as `attempted_urls`.

### `downloader.py`

Coordinates the end-to-end flow.

Responsibilities:

- Fetch page HTML.
- Parse SSR data.
- Collect initial feed pins.
- Paginate until completion.
- Deduplicate pins by ID.
- Download selected images with retry and candidate fallback.
- Update manifest incrementally.

Image download behavior:

- Try candidates in ranked order: `originals`, `1200x`, `736x`, `474x`, `236x`, `237x`, then unknown sizes.
- Retry transient failures up to `--retries` per candidate.
- Treat image `403` and `404` as non-retryable for that candidate and move to the next candidate.
- Record every attempted URL in the manifest.

### `user_downloader.py`

Coordinates user-profile batch downloads.

Responsibilities:

- Fetch the user profile page.
- Discover public boards with `user_boards.py`.
- Call `crawl_board()` for each public board.
- Write each board to `downloads/<user>/<board-slug>/`.
- Continue to later boards if one board fails.
- Save `downloads/<user>/user_manifest.json` with board-level results.

The user-level manifest includes:

- Username and normalized user URL.
- Discovered public boards.
- Per-board output directory.
- Per-board status, pin record count, and error message.

Each board directory still owns its own `manifest.json` and resume state.

### `playwright_bootstrap.py`

Playwright is included in `0.1.0`, but its role is deliberately narrow.

Use Playwright when:

- The initial HTTP board page does not contain `#__PWS_INITIAL_PROPS__`.
- Pinterest returns an interstitial, bot challenge, or unusable HTML.
- XHR pagination fails because cookies from plain HTTP are insufficient.
- A manual verification run needs to inspect the rendered page boundary.

Playwright responsibilities:

- Launch Chromium.
- Navigate to the board URL.
- Wait for the page to reach a usable state.
- Capture browser cookies for `pinterest.com`.
- Optionally capture rendered HTML for SSR parsing.
- Return cookies and HTML to the HTTP-first crawler.

Playwright should not become the primary pin extraction mechanism in `0.1.0`. Browser DOM extraction is only a last-resort diagnostic path because Pinterest layout, localized text, and CSS classes are less stable than resource JSON.

## Crawl Flow

### Single-board flow

1. Normalize the board URL.
2. Fetch board HTML with `httpx`.
3. Parse `#__PWS_INITIAL_PROPS__`.
4. If parsing fails and Playwright is enabled, bootstrap with Playwright and retry SSR parsing with browser HTML/cookies.
5. Resolve board metadata.
6. Extract initial `BoardFeedResource` data and bookmark from SSR.
7. Keep only target-board pins.
8. Paginate `BoardFeedResource` with session cookies and required XHR headers.
9. Stop on `bookmarks == ["-end-"]`.
10. Deduplicate by pin ID.
11. Load existing `manifest.json` for resume when present.
12. Select and rank image URL candidates for each pin.
13. Download images with retry and fallback.
14. Write or update `manifest.json` after each pin and again at the end.

### User-profile flow

1. Normalize the user profile URL.
2. Fetch user profile HTML with `httpx`.
3. Parse `#__PWS_INITIAL_PROPS__`.
4. Read public boards from `initialReduxState.boards`.
5. Save an initial `user_manifest.json`.
6. For each public board, run the single-board flow into `downloads/<user>/<board-slug>/`.
7. Record per-board success or failure in `user_manifest.json`.
8. Continue after individual board failures.

Example output:

```text
downloads/adryanlong/user_manifest.json
downloads/adryanlong/coastal-calm/manifest.json
downloads/adryanlong/golden-hour/manifest.json
```

## Error Handling

The `0.1.0` implementation should fail clearly and preserve context.

Expected recoverable cases:

- Missing SSR script: try Playwright if enabled.
- Invalid `BoardFeedResource` request: surface the response body and headers used.
- Image candidate returns `403` or `404`: try the next candidate.
- Transient image download failure: retry the same candidate up to `--retries`.
- Duplicate pin ID: keep the first complete record.
- Existing file: skip unless `--overwrite` is set.
- One board fails in a user-profile batch: record the failure and continue with the next board.

Expected hard failures:

- Private board or unavailable board.
- Board metadata cannot be resolved.
- No valid board-owned pins found after SSR and pagination.
- User profile metadata cannot be fetched or parsed.
- Playwright fallback requested but browser bootstrap fails.

## Testing Strategy

Tests should avoid live Pinterest network access by default.

Use fixtures from the verified examples:

- SSR HTML containing `#__PWS_INITIAL_PROPS__`.
- Initial `BoardFeedResource` JSON.
- Paginated `BoardFeedResource` JSON.
- A feed containing non-pin or non-board recommendation items.
- Pins with multiple image sizes.
- Story Pin image payloads.

Important tests:

- SSR extraction returns `initialReduxState`.
- Board resolution finds the target board.
- User profile board discovery extracts public boards from `initialReduxState.boards`.
- Private, duplicate, or malformed board records are ignored.
- Initial feed parsing returns only board-owned pins.
- Pagination stops on `["-end-"]`.
- Non-board recommendations are filtered out.
- Image ranking prefers `/originals/`.
- Manifest writes stable, resumable records, including attempted URLs.
- Existing successful downloads are skipped during resume.
- Failed downloads are retried during resume.
- Image fallback tries the next candidate after a non-retryable candidate failure.
- User batch downloads write `user_manifest.json`.
- User batch downloads continue after one board fails.
- Playwright fallback is invoked only after HTTP SSR parsing fails.

Before considering implementation complete, run:

```bash
uv run ruff check .
uv run ruff format .
uv run mypy .
uv run pytest
```

## Dependency Plan

Initial `pyproject.toml` dependency direction:

```toml
[project]
dependencies = [
    "beautifulsoup4>=4.12",
    "httpx>=0.27",
    "playwright>=1.44",
]

[dependency-groups]
dev = [
    "mypy>=1.10",
    "pytest>=8.0",
    "ruff>=0.5",
]
```

After installing Playwright, browser binaries must be installed separately:

```bash
uv run playwright install chromium
```

## 0.1.0 Non-Goals

- No official Pinterest API integration.
- No deprecated v3 pidget endpoints.
- No web UI.
- No multi-user service.
- No distributed queue.
- No database requirement.
- No login-only/private-board support.
- No board section support.
- No user "all pins" mode.
- No video pin download support.
- No full browser-driven infinite scroll crawler unless the resource JSON path fails and a later design explicitly adds that mode.

## Recommended Implementation Order

1. Add dependencies and package layout.
2. Implement models and manifest schema.
3. Implement SSR extraction with tests.
4. Implement board metadata resolution with tests.
5. Implement initial `BoardFeedResource` extraction with tests.
6. Implement XHR pagination with fixture-based tests.
7. Implement image candidate extraction and ranking with tests.
8. Implement downloader orchestration.
9. Implement CLI.
10. Add Playwright bootstrap fallback.
11. Add v1.1 resume, retry, image fallback, and attempted URL manifest fields.
12. Add v1.2 user profile board discovery and `download-user`.
13. Run live smoke tests against verified public boards and at least one public user profile.
14. Update docs with any observed Pinterest response changes.

## Decision

Use a Python, `uv`, `httpx`, `beautifulsoup4`, and Playwright `0.1.0` baseline.

The primary crawler remains HTTP-first because the verified Pinterest data path is SSR plus `BoardFeedResource`. Playwright is included from the start as a narrow fallback for cookie and HTML bootstrap, not as the primary extraction engine.

For user-profile batch downloads, the primary discovery path is also HTTP-first: fetch the profile page, parse `#__PWS_INITIAL_PROPS__`, and read `initialReduxState.boards`. `BoardsFeedResource` pagination is deferred until a verified profile requires it.
