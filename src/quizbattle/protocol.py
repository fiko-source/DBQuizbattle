import asyncio
import json
import socket
import struct


MAX_FRAME_SIZE = 10 * 1024 * 1024


def local_ip():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("10.255.255.255", 1))
        ip = sock.getsockname()[0]
        return ip if ip and not ip.startswith("127.") else "127.0.0.1"
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def json_bytes(message):
    return json.dumps(
        message, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def frame_message(message):
    payload = json_bytes(message)
    return struct.pack("!I", len(payload)) + payload


async def read_frame(reader):
    header = await reader.readexactly(4)
    length = struct.unpack("!I", header)[0]
    if length > MAX_FRAME_SIZE:
        raise ValueError("Control message is too large")
    payload = await reader.readexactly(length)
    return json.loads(payload.decode("utf-8"))


async def send_frame(writer, message):
    writer.write(frame_message(message))
    await writer.drain()


class DatagramProtocol(asyncio.DatagramProtocol):
    def __init__(self, callback):
        self.callback = callback

    def datagram_received(self, data, address):
        try:
            message = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        asyncio.create_task(self.callback(message, address))
