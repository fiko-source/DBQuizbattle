import asyncio
import json
import socket
import threading
import uuid

import websockets

from .client_ordering import OrderedEventBuffer


class NetworkClient:
    def __init__(self, name, discovery_port, broadcast_ip, signals):
        self.name = name
        self.discovery_port = discovery_port
        self.broadcast_ip = broadcast_ip
        self.signals = signals
        self.token = None
        self.player_id = None
        self.websocket = None
        self.loop = None
        self.outbox = None
        self.stopped = False
        self.ordering = OrderedEventBuffer()
        self.pending_actions = {}

    @property
    def last_seq(self):
        return self.ordering.last_sequence

    def start(self):
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.outbox = asyncio.Queue()
        self.loop.run_until_complete(self.connection_loop())

    def send(self, message):
        if self.loop and self.outbox:
            if message.get("type") in {"ANSWER", "TEAM_ANSWER", "TEAM_CHAT"}:
                request_id = message.setdefault("request_id", uuid.uuid4().hex)
                self.pending_actions[request_id] = message
            asyncio.run_coroutine_threadsafe(self.outbox.put(message), self.loop)

    async def discover_leader(self):
        loop = asyncio.get_running_loop()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setblocking(False)
        sock.bind(("0.0.0.0", 0))
        request = json.dumps({"type": "CLIENT_DISCOVER"}).encode()
        deadline = loop.time() + 4
        try:
            while loop.time() < deadline:
                await loop.sock_sendto(
                    sock, request, (self.broadcast_ip, self.discovery_port)
                )
                try:
                    data, _ = await asyncio.wait_for(
                        loop.sock_recvfrom(sock, 4096), 1
                    )
                    response = json.loads(data.decode())
                    if response.get("type") == "LEADER_RESPONSE":
                        return response["host"], int(response["ws_port"])
                except asyncio.TimeoutError:
                    continue
        finally:
            sock.close()
        return None

    async def connection_loop(self):
        while not self.stopped:
            self.signals.status.emit("Suche Leader im Netzwerk...")
            leader = await self.discover_leader()
            if not leader:
                self.signals.status.emit("Kein Leader gefunden. Neuer Versuch...")
                await asyncio.sleep(2)
                continue

            uri = f"ws://{leader[0]}:{leader[1]}"
            try:
                async with websockets.connect(uri) as websocket:
                    self.websocket = websocket
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "JOIN",
                                "name": self.name,
                                "token": self.token,
                                "last_seq": self.last_seq,
                            }
                        )
                    )
                    self.signals.status.emit(f"Mit Leader {uri} verbunden.")
                    receiver = asyncio.create_task(self.receive_loop(websocket))
                    sender = asyncio.create_task(self.send_loop(websocket))
                    done, pending = await asyncio.wait(
                        [receiver, sender],
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for task in pending:
                        task.cancel()
                    for task in done:
                        task.result()
            except (
                OSError,
                websockets.ConnectionClosed,
                websockets.InvalidHandshake,
            ):
                self.signals.status.emit(
                    "Verbindung verloren. Suche neuen Leader..."
                )
                await asyncio.sleep(1)
            finally:
                self.websocket = None

    async def receive_loop(self, websocket):
        async for raw in websocket:
            message = json.loads(raw)
            message_type = message.get("type")
            if message_type == "NOT_LEADER":
                return
            if message_type == "WELCOME":
                self.token = message["token"]
                self.player_id = message["player_id"]
                self.signals.message.emit(message)
                continue
            if message_type == "ACTION_STATUS":
                self.pending_actions.pop(message.get("request_id"), None)
                self.signals.message.emit(message)
                continue

            sequence = message.get("seq")
            if not isinstance(sequence, int):
                self.signals.message.emit(message)
                continue

            delivered, missing = self.ordering.receive(message)
            if missing:
                await websocket.send(
                    json.dumps(
                        {
                            "type": "RESEND_REQUEST",
                            "from_seq": missing[0],
                            "to_seq": missing[1],
                        }
                    )
                )
            for event in delivered:
                self.signals.message.emit(event)
            await websocket.send(
                json.dumps({"type": "ACK", "seq": self.last_seq})
            )

    async def send_loop(self, websocket):
        for message in list(self.pending_actions.values()):
            await websocket.send(json.dumps(message, ensure_ascii=False))
        while True:
            try:
                message = await asyncio.wait_for(self.outbox.get(), timeout=1)
                request_id = message.get("request_id")
                if request_id is None or request_id in self.pending_actions:
                    await websocket.send(
                        json.dumps(message, ensure_ascii=False)
                    )
            except asyncio.TimeoutError:
                for message in list(self.pending_actions.values()):
                    await websocket.send(
                        json.dumps(message, ensure_ascii=False)
                    )
