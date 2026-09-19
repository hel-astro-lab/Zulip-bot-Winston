"""Command line: `winston run`, `winston check <arxiv id>`, `winston run-feature <name>`."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from winston import arxiv

DEFAULT_CONFIG = Path("~/.config/winston/winston.toml").expanduser()


def _config_path(given: Path | None) -> Path:
    for candidate in ([given] if given else [Path("winston.toml"), DEFAULT_CONFIG]):
        if candidate.exists():
            return candidate
    sys.exit(f"no config file found (looked for {given or 'winston.toml and ' + str(DEFAULT_CONFIG)})")


def main(argv: list[str] | None = None) -> None:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", type=Path, help="winston.toml (default: ./winston.toml, then ~/.config/winston/winston.toml)")
    common.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    parser = argparse.ArgumentParser(prog="winston", description="Winston, the research group's Zulip bot")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("run", parents=[common], help="start the bot")
    check = commands.add_parser("check", parents=[common], help="fetch one arXiv paper and print its card; no Zulip needed")
    check.add_argument("id_or_url")
    once = commands.add_parser("run-feature", parents=[common], help="run one scheduled feature once and exit")
    once.add_argument("name")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.command == "check":
        ids = arxiv.extract_ids(args.id_or_url) or arxiv.extract_ids("arXiv:" + args.id_or_url)
        if not ids:
            sys.exit(f"not an arXiv id or link: {args.id_or_url}")
        papers = arxiv.fetch_papers(ids)
        if not papers:
            sys.exit(f"arXiv does not know {ids[0]}")
        print(arxiv.format_paper(papers[0]))
        return

    from winston.bot import Config, Winston  # imports zulip; only needed here

    bot = Winston(Config.load(_config_path(args.config)))
    try:
        if args.command == "run":
            bot.start()
        else:
            bot.run_feature_once(args.name)
    except KeyboardInterrupt:
        logging.info("stopped")


if __name__ == "__main__":
    main()
