"""Command line interface for the Pinterest board downloader."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pinterest_crawler.config import load_runtime_config
from pinterest_crawler.created_downloader import crawl_created_feed
from pinterest_crawler.downloader import crawl_board
from pinterest_crawler.user_downloader import crawl_user_boards


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""

    parser = argparse.ArgumentParser(prog="pinterest-crawler")
    subparsers = parser.add_subparsers(dest="command", required=True)

    download = subparsers.add_parser("download", help="download a public Pinterest board")
    download.add_argument("board_url")
    download.add_argument("--out", type=Path, required=True)
    download.add_argument("--config", type=Path)
    download.add_argument("--dry-run", action="store_true")
    download.add_argument("--no-playwright", action="store_true")

    download_created = subparsers.add_parser(
        "download-created",
        help="download pins from a Pinterest user's public Created feed",
    )
    download_created.add_argument("created_url")
    download_created.add_argument("--out", type=Path, required=True)
    download_created.add_argument("--config", type=Path)
    download_created.add_argument("--dry-run", action="store_true")
    download_created.add_argument("--no-playwright", action="store_true")

    download_user = subparsers.add_parser(
        "download-user",
        help="download a Pinterest user's created feed and public saved boards",
    )
    download_user.add_argument("user_url")
    download_user.add_argument("--out", type=Path, required=True)
    download_user.add_argument("--config", type=Path)
    download_user.add_argument("--dry-run", action="store_true")
    download_user.add_argument("--no-playwright", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI."""

    parser = build_parser()
    args = parser.parse_args(argv)
    config = load_runtime_config(args.config)
    use_playwright = not args.no_playwright

    if args.command == "download":
        manifest = crawl_board(
            args.board_url,
            args.out,
            config,
            dry_run=args.dry_run,
            use_playwright=use_playwright,
        )
        print(
            f"Board {manifest.board_slug}: scan={manifest.scan_status}, "
            f"download={manifest.download_status}, records={len(manifest.records)}"
        )
        return 0

    if args.command == "download-created":
        manifest = crawl_created_feed(
            args.created_url,
            args.out,
            config,
            dry_run=args.dry_run,
            use_playwright=use_playwright,
        )
        print(
            f"Created feed {manifest.board_slug}: scan={manifest.scan_status}, "
            f"download={manifest.download_status}, records={len(manifest.records)}"
        )
        return 0

    if args.command == "download-user":
        user_manifest = crawl_user_boards(
            args.user_url,
            args.out,
            config,
            dry_run=args.dry_run,
            use_playwright=use_playwright,
        )
        completed = sum(1 for target in user_manifest.targets if target.status == "complete")
        failed = sum(1 for target in user_manifest.targets if target.status == "failed")
        print(
            f"User {user_manifest.username}: status={user_manifest.status}, "
            f"completed={completed}/{len(user_manifest.targets)}, failed={failed}"
        )
        return 0

    parser.error("Unknown command")
    return 2


if __name__ == "__main__":
    sys.exit(main())
