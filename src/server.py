import argparse
import asyncio
import logging

from quizbattle.protocol import local_ip
from quizbattle.server_app import QuizServer
from quizbattle.settings import DEFAULT_DISCOVERY_PORT, ServerConfig


def parse_config():
    parser = argparse.ArgumentParser(description="Distributed QuizBattle server")
    parser.add_argument("--id", type=int, required=True)
    parser.add_argument("--host", help="LAN IP advertised to other computers")
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--ws-port", type=int, default=5000)
    parser.add_argument("--control-port", type=int, default=6000)
    parser.add_argument("--discovery-port", type=int, default=DEFAULT_DISCOVERY_PORT)
    parser.add_argument("--broadcast", default="255.255.255.255")
    args = parser.parse_args()
    return ServerConfig(
        server_id=args.id,
        host=args.host or local_ip(),
        bind_host=args.bind,
        ws_port=args.ws_port,
        control_port=args.control_port,
        discovery_port=args.discovery_port,
        broadcast_ip=args.broadcast,
    )


async def main():
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
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
