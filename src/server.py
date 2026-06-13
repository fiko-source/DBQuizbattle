"""Startpunkt eines QuizBattle-Servers."""

import argparse
import asyncio
import logging

from quizbattle.identity import load_or_create_uuid, normalize_uuid
from quizbattle.protocol import local_ip
from quizbattle.server_app import QuizServer
from quizbattle.settings import DEFAULT_DISCOVERY_PORT, PROJECT_DIR, ServerConfig


def parse_config():
    """Lese Serveridentitaet, LAN-Adresse und Ports aus der Kommandozeile."""
    parser = argparse.ArgumentParser(description="Distributed QuizBattle server")
    identity = parser.add_mutually_exclusive_group()
    identity.add_argument("--uuid", help="Explicit server UUID")
    identity.add_argument("--identity-file", help="File containing the persistent UUID")
    parser.add_argument("--host", help="LAN IP advertised to other computers")
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--ws-port", type=int, default=5000)
    parser.add_argument("--control-port", type=int, default=6000)
    parser.add_argument("--discovery-port", type=int, default=DEFAULT_DISCOVERY_PORT)
    parser.add_argument("--broadcast", default="255.255.255.255")
    args = parser.parse_args()

    if args.uuid:
        server_uuid = normalize_uuid(args.uuid)
    else:
        identity_file = args.identity_file or (
            PROJECT_DIR / f".server_uuid_{args.control_port}"
        )
        server_uuid = load_or_create_uuid(identity_file)

    return ServerConfig(
        server_uuid=server_uuid,
        host=args.host or local_ip(),
        bind_host=args.bind,
        ws_port=args.ws_port,
        control_port=args.control_port,
        discovery_port=args.discovery_port,
        broadcast_ip=args.broadcast,
    )


async def main():
    """Konfiguriere Logging und betreibe den Server bis zum Programmende."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    server = QuizServer(parse_config())
    try:
        await server.start()
    finally:
        await server.stop()


if __name__ == "__main__":
    try:
        # asyncio.run erstellt und schliesst den zentralen Event-Loop.
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
