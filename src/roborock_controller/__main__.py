import argparse
import asyncio
from pathlib import Path

from roborock_controller.login import login

DEFAULT_SECRETS = Path("config/secrets.json")


def main() -> None:
    parser = argparse.ArgumentParser(prog="roborock-controller")
    commands = parser.add_subparsers(dest="command", required=True)
    login_parser = commands.add_parser("login", help="log in with an e-mail code and store the credentials")
    login_parser.add_argument("--email", required=True)
    login_parser.add_argument("--secrets", type=Path, default=DEFAULT_SECRETS)
    args = parser.parse_args()

    if args.command == "login":
        asyncio.run(login(args.email, args.secrets))


if __name__ == "__main__":
    main()
