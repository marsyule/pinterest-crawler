# Pinterest Crawler

> Download images from public Pinterest boards, user `Created` feeds, and user saved boards.

[![GitHub Stars](https://img.shields.io/github/stars/marsyule/pinterest-crawler?style=social)](https://github.com/marsyule/pinterest-crawler/stargazers)
[![GitHub Forks](https://img.shields.io/github/forks/marsyule/pinterest-crawler?style=social)](https://github.com/marsyule/pinterest-crawler/network/members)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

Pinterest public board downloader for Python 3.11+.

The crawler targets three public Pinterest surfaces:

- normal public boards such as `https://www.pinterest.com/<user>/<board>/`
- public user `Created` feeds such as `https://www.pinterest.com/<user>/_created/`
- public saved boards discovered from a user's profile page

It uses Pinterest's web data path rather than a public official API:

- `#__PWS_INITIAL_PROPS__` SSR JSON for user-board discovery, board metadata, and initial board feed pages
- `/resource/BoardFeedResource/get/` XHR pagination for board pins
- `/resource/UserResource/get/` plus `/resource/UserActivityPinsResource/get/` for `Created` feeds

It does not use Pinterest's deprecated v3 pidget endpoints.

## Features

- Download images from public Pinterest boards
- Crawl a user's public `Created` feed and saved boards in one batch
- Download pins from a user's public `Created` feed
- Re-discover user targets on each `download-user` run so stale `user_manifest.json` files do not hide new boards
- Resume interrupted runs with per-target `manifest.json`
- Retry failed image downloads with ranked candidate fallback
- Stay HTTP-first, with optional Playwright bootstrap fallback when SSR or cookies are unavailable

## Quick Start

Recommended development setup with `uv`:

```bash
uv sync
```

Standard Python setup without `uv`, using your current Python environment:

```bash
python -m pip install -e .
```

Download a single board:

```bash
pinterest-crawler download https://www.pinterest.com/chumq9921/outfits/ --out downloads/outfits
```

Download a user's public `Created` feed and saved boards:

```bash
pinterest-crawler download-user https://www.pinterest.com/chumq9921/ --out downloads/chumq9921
```

Download a user's public `Created` feed:

```bash
pinterest-crawler download-created https://www.pinterest.com/chumq9921/_created/ --out downloads/chumq9921-created
```

If you are using `uv` without activating the virtual environment, prefix commands with `uv run`.

## Setup

Playwright is used only as a bootstrap fallback when plain HTTP cannot obtain usable SSR data
or cookies. Install the Chromium browser if you want that fallback available:

```bash
playwright install chromium
```

With `uv`, use `uv run playwright install chromium`.

## Download a Board

```bash
pinterest-crawler download https://www.pinterest.com/adryanlong/golden-hour/ --out downloads/golden-hour
```

Useful options:

```bash
pinterest-crawler download https://www.pinterest.com/adryanlong/golden-hour/ --out downloads/golden-hour --no-playwright
pinterest-crawler download https://www.pinterest.com/adryanlong/golden-hour/ --out downloads/golden-hour --dry-run
```

The internal Python module is kept for development and tests, but regular usage should go through
the `pinterest-crawler` command.

## Download a User's Created Feed and Saved Boards

```bash
pinterest-crawler download-user https://www.pinterest.com/adryanlong/ --out downloads/adryanlong
```

This command does two things:

- builds the user's canonical `Created` URL as `https://www.pinterest.com/<user>/_created/`
- fetches the user's public profile page and discovers saved-board URLs from `initialReduxState.boards`

It then runs the `Created` downloader once and the normal board downloader once per saved board.

The output directory is organized by target type:

```text
downloads/adryanlong/user_manifest.json
downloads/adryanlong/created/manifest.json
downloads/adryanlong/saved/coastal-calm/manifest.json
downloads/adryanlong/saved/golden-hour/manifest.json
```

`user_manifest.json` is the batch-level summary. It contains a `targets` list with one `created`
entry and one `saved_board` entry per discovered public board. Each target directory still has its
own `manifest.json` with per-pin resume and retry state.

`download-user` always refreshes target discovery before it runs downloads. If a previous
`user_manifest.json` only listed part of a user's current public content, rerunning the command in
the same output directory will still discover newly visible saved boards.

## Download a User's Public Created Feed

```bash
pinterest-crawler download-created https://www.pinterest.com/rileyaussies/_created/ --out downloads/rileyaussies-created
```

Use this when you want only the `Created` feed and do not want batch saved-board discovery.

## Naming

- Project name: `pinterest-crawler`
- CLI command: `pinterest-crawler`
- Python package: `pinterest_crawler`
- Default config file: `pinterest-crawler.yaml`

## Resume and Retry Behavior

Each board or created-feed output directory contains a `manifest.json` file with metadata, pin
records, image candidates, attempted URLs, selected URL, local file path, status, and error
details.

Runs are resumable by default:

- Existing successful records are reused when their local files still exist.
- Failed records are retried on the next run.
- If the best image URL fails, the downloader tries lower-ranked image candidates before
  marking the pin as failed.

The manifest is saved after each pin is processed, so an interrupted run preserves completed
work.

## Development

Run checks through `uv`:

```bash
uv run ruff check .
uv run ruff format .
uv run mypy .
uv run pytest
```

## Disclaimer

This project is provided for educational and research use only.

You are responsible for ensuring that your use of this project complies with Pinterest's Terms of Service, applicable laws, and the rights of content owners. Only download or access content you are legally allowed to use.

This project is provided "as is", without warranty of any kind. The authors and contributors are not responsible for account restrictions, access loss, legal claims, data loss, or any other consequences resulting from use of this project.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
