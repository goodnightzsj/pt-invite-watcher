import argparse
import asyncio
import logging
import sys
from typing import Optional

import uvicorn

from pt_invite_watcher.app import app
from pt_invite_watcher.config import load_settings


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="pt-invite-watcher")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="Run web UI + scheduler")
    run.add_argument("--host", default=None)
    run.add_argument("--port", type=int, default=None)

    check = sub.add_parser("check-once", help="Run one scan cycle and exit")
    check.add_argument("--config", default=None, help="Path to config yaml (optional)")

    return parser.parse_args(argv)


async def _check_once(config_path: Optional[str]) -> None:
    from pt_invite_watcher.app_context import build_context

    settings = load_settings(config_path=config_path)
    logging.basicConfig(level=getattr(logging, settings.log_level, logging.INFO))
    ctx = await build_context(settings)
    await ctx.scanner.run_once()


def main(argv: Optional[list[str]] = None) -> None:
    args = _parse_args(argv or sys.argv[1:])
    if args.cmd == "run":
        settings = load_settings()
        host = args.host or settings.web.host
        port = args.port or settings.web.port
        uvicorn.run(app, host=host, port=port, log_level=settings.log_level.lower())
        return

    if args.cmd == "check-once":
        asyncio.run(_check_once(config_path=args.config))
        return

    raise SystemExit(2)


if __name__ == "__main__":
    main()
