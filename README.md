# Pinterest Crawler

> Download images from public Pinterest boards with SSR parsing and `BoardFeedResource` pagination.

[![GitHub Stars](https://img.shields.io/github/stars/marsyule/pinterest-crawler?style=social)](https://github.com/marsyule/pinterest-crawler/stargazers)
[![GitHub Forks](https://img.shields.io/github/forks/marsyule/pinterest-crawler?style=social)](https://github.com/marsyule/pinterest-crawler/network/members)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Package Manager](https://img.shields.io/badge/package%20manager-uv-6e56cf)
![License](https://img.shields.io/badge/license-MIT-green)

Pinterest public board downloader for Python 3.11+.

The crawler targets public Pinterest boards and uses Pinterest's web data path:

- `#__PWS_INITIAL_PROPS__` SSR JSON for board metadata and the initial feed.
- `/resource/BoardFeedResource/get/` XHR pagination for remaining board pins.

It does not use Pinterest's deprecated v3 pidget endpoints or a public official API.

## Features

- Download images from public Pinterest boards
- Crawl all public boards from a Pinterest user profile
- Resume interrupted runs with per-board `manifest.json`
- Retry failed image downloads with ranked candidate fallback
- Stay HTTP-first, with optional Playwright bootstrap fallback when SSR or cookies are unavailable

## Quick Start

Sync dependencies:

```bash
uv sync
```

Download a single board:

```bash
uv run pinterest-crawler download https://www.pinterest.com/adryanlong/golden-hour/ --out downloads/golden-hour
```

Download all public boards from a user profile:

```bash
uv run python -m pinterest_crawler.cli download-user https://www.pinterest.com/adryanlong/ --out downloads/adryanlong
```

## Setup

Playwright is used only as a bootstrap fallback when plain HTTP cannot obtain usable SSR data
or cookies. Install the Chromium browser if you want that fallback available:

```bash
uv run playwright install chromium
```

## Download a Board

```bash
uv run pinterest-crawler download https://www.pinterest.com/adryanlong/golden-hour/ --out downloads/golden-hour
```

Useful options:

```bash
uv run pinterest-crawler download https://www.pinterest.com/adryanlong/golden-hour/ --out downloads/golden-hour --retries 2
uv run pinterest-crawler download https://www.pinterest.com/adryanlong/golden-hour/ --out downloads/golden-hour --overwrite
uv run pinterest-crawler download https://www.pinterest.com/adryanlong/golden-hour/ --out downloads/golden-hour --no-playwright
```

If the console script is not installed in the current virtual environment, run the same command
through the module entry point:

```bash
uv run python -m pinterest_crawler.cli download https://www.pinterest.com/adryanlong/golden-hour/ --out downloads/golden-hour
```

## Download All Public Boards for a User

```bash
uv run python -m pinterest_crawler.cli download-user https://www.pinterest.com/adryanlong/ --out downloads/adryanlong
```

This starts from the user's public profile page, reads public board URLs from
`initialReduxState.boards`, and then runs the normal board downloader for each board.

The output directory is organized by board slug:

```text
downloads/adryanlong/user_manifest.json
downloads/adryanlong/coastal-calm/manifest.json
downloads/adryanlong/golden-hour/manifest.json
```

`user_manifest.json` is the batch-level summary. Each board directory still has its own
`manifest.json` with per-pin resume and retry state.

## Naming

- Project name: `pinterest-crawler`
- CLI command: `pinterest-crawler`
- Python package: `pinterest_crawler`
- Default config file: `pinterest-crawler.yaml`

## Resume and Retry Behavior

Each output directory contains a `manifest.json` file with board metadata, pin records, image
candidates, attempted URLs, selected URL, local file path, status, and error details.

Runs are resumable by default:

- Existing successful records are reused when their local files still exist.
- Failed records are retried on the next run.
- `--overwrite` ignores successful existing files and downloads them again.
- `--retries N` tries each image candidate up to `N + 1` times, except `403` and `404`
  responses, which immediately fall through to the next candidate.
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
