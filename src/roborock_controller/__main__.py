import argparse
import asyncio
import logging
import os
from pathlib import Path

from roborock_controller.login import login
from roborock_controller.service import Settings, serve

DEFAULT_SECRETS = Path("config/secrets.json")


def main() -> None:
    parser = argparse.ArgumentParser(prog="roborock-controller")
    commands = parser.add_subparsers(dest="command", required=True)
    login_parser = commands.add_parser("login", help="log in with an e-mail code and store the credentials")
    login_parser.add_argument("--email", required=True)
    login_parser.add_argument("--secrets", type=Path, default=DEFAULT_SECRETS)
    commands.add_parser("serve", help="run the HTTP API and the metrics endpoint")
    args = parser.parse_args()

    if args.command == "login":
        asyncio.run(login(args.email, args.secrets))
    elif args.command == "serve":
        logging.basicConfig(
            level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s"
        )
        asyncio.run(serve(_settings()))


def _settings() -> Settings:
    return Settings(
        secrets=Path(os.environ.get("ROBOROCK_SECRETS", DEFAULT_SECRETS)),
        cache=Path(os.environ.get("ROBOROCK_CACHE", "cache/roborock.cache")),
        device_name=os.environ.get("ROBOROCK_DEVICE"),
        api_port=int(os.environ.get("API_PORT", "8080")),
        metrics_port=int(os.environ.get("METRICS_PORT", "9105")),
        refresh_seconds=int(os.environ.get("REFRESH_SECONDS", "30")),
    )


if __name__ == "__main__":
    main()
