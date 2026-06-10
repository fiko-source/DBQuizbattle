import asyncio
import copy
import logging
import time

from .control import ReliableControlChannel
from .discovery import BroadcastEndpoint
from .settings import HEARTBEAT_INTERVAL, HEARTBEAT_TIMEOUT


class ClusterManager:
    def __init__(self, config, get_state, set_state, became_leader):
        self.config = config
        self.get_state = get_state
        self.set_state = set_state
        self.became_leader = became_leader

        self.peers = {}
        self.dead_peers = set()
        self.leader_id = None
        self.participant = False

        self.tasks = []
        self.election_lock = asyncio.Lock()
        self.discovery = BroadcastEndpoint(
            config.bind_host,
            config.discovery_port,
            config.broadcast_ip,
            self.handle_discovery,
        )
        self.control = ReliableControlChannel(
            config,
            sender_address=self.server_address,
            peer_lookup=self.peers.get,
            sender_seen=self.control_sender_seen,
            message_handler=self.handle_control,
        )

    @property
    def is_leader(self):
        return self.leader_id == self.config.server_id

    def ring(self):
        return sorted([self.config.server_id, *self.peers])

    def successor(self):
        ring = self.ring()
        index = ring.index(self.config.server_id)
        return ring[(index + 1) % len(ring)]

    async def start(self):
        await self.discovery.start()
        await self.control.start()
        self.tasks.extend(
            [
                asyncio.create_task(self.heartbeat_loop()),
                asyncio.create_task(self.peer_monitor_loop()),
            ]
        )
        await self.send_discovery({"type": "SERVER_DISCOVER"})
        await self.broadcast_announcement("SERVER_JOIN")
        await asyncio.sleep(1.5)
        await self.start_election(force=True)

    def server_address(self):
        return {
            "server_id": self.config.server_id,
            "host": self.config.host,
            "ws_port": self.config.ws_port,
            "control_port": self.config.control_port,
            "leader_id": self.leader_id,
        }

    def server_message(self, message_type):
        return {"type": message_type, **self.server_address()}

    async def send_discovery(self, message, target=None):
        payload = {**message}
        if message.get("type", "").startswith("SERVER_"):
            payload = {**self.server_address(), **message}
        self.discovery.send(payload, target)

    async def broadcast_announcement(self, message_type):
        await self.send_discovery(self.server_message(message_type))

    async def handle_discovery(self, message, address):
        message_type = message.get("type")
        if message_type == "CLIENT_DISCOVER":
            if self.is_leader:
                await self.send_discovery(
                    {
                        "type": "LEADER_RESPONSE",
                        "server_id": self.config.server_id,
                        "host": self.config.host,
                        "ws_port": self.config.ws_port,
                    },
                    address,
                )
            return

        if message_type == "SERVER_DISCOVER":
            await self.send_discovery(self.server_message("SERVER_JOIN"), address)
            return

        if message_type not in {"SERVER_JOIN", "HEARTBEAT", "SERVER_LEAVE"}:
            return
        server_id = message.get("server_id")
        if not isinstance(server_id, int) or server_id == self.config.server_id:
            return

        if message_type == "SERVER_LEAVE":
            was_leader = server_id == self.leader_id
            self.remove_peer(server_id)
            if was_leader:
                await self.start_election(force=True)
            return

        is_new = self.register_peer(message, directly_seen=True)
        announced_leader = message.get("leader_id")
        if self.leader_id is None and isinstance(announced_leader, int):
            self.leader_id = announced_leader
        if message_type == "SERVER_JOIN":
            await self.send_discovery(self.server_message("HEARTBEAT"), address)
        if is_new:
            logging.info("Server %s entdeckt. Ring: %s", server_id, self.ring())
            await self.send_control(
                self.server_message("PEER_HELLO"), server_id
            )
            if self.is_leader:
                await self.replicate_to_peer(server_id)
            elif self.leader_id in self.peers:
                await self.synchronize_from_leader()
            await self.start_election(force=True)

    def register_peer(self, message, directly_seen=True):
        server_id = int(message["server_id"])
        if not directly_seen and server_id in self.dead_peers:
            return False
        if directly_seen:
            self.dead_peers.discard(server_id)

        is_new = server_id not in self.peers
        last_seen = time.monotonic()
        if not is_new and not directly_seen:
            last_seen = self.peers[server_id]["last_seen"]
        self.peers[server_id] = {
            "host": message["host"],
            "ws_port": int(message["ws_port"]),
            "control_port": int(message["control_port"]),
            "last_seen": last_seen,
        }
        return is_new

    def remove_peer(self, server_id):
        self.peers.pop(server_id, None)
        self.dead_peers.add(server_id)
        self.control.forget_peer(server_id)

    async def heartbeat_loop(self):
        while True:
            await self.broadcast_announcement("HEARTBEAT")
            heartbeat = {
                "type": "CONTROL_HEARTBEAT",
                "leader_id": self.leader_id,
                "members": [
                    {
                        "server_id": server_id,
                        "host": peer["host"],
                        "ws_port": peer["ws_port"],
                        "control_port": peer["control_port"],
                    }
                    for server_id, peer in self.peers.items()
                ],
            }
            await asyncio.gather(
                *[
                    self.send_control(heartbeat, server_id, retries=1)
                    for server_id in list(self.peers)
                ],
                return_exceptions=True,
            )
            await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def peer_monitor_loop(self):
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            now = time.monotonic()
            expired = [
                server_id
                for server_id, peer in self.peers.items()
                if now - peer["last_seen"] > HEARTBEAT_TIMEOUT
            ]
            leader_failed = self.leader_id in expired
            for server_id in expired:
                self.remove_peer(server_id)
                logging.warning("Server %s ausgefallen. Ring: %s", server_id, self.ring())
            if expired and (leader_failed or self.leader_id not in self.ring()):
                await self.start_election(force=True)

    async def control_sender_seen(self, sender):
        sender_is_new = self.register_peer(sender, directly_seen=True)
        if sender_is_new and self.is_leader:
            await self.replicate_to_peer(int(sender["server_id"]))

    async def send_control(self, message, server_id, retries=3):
        return await self.control.send(message, server_id, retries)

    async def handle_control(self, message):
        message_type = message.get("type")
        if message_type == "ELECTION":
            await self.handle_election(message)
        elif message_type == "LEADER":
            await self.handle_leader(message)
        elif message_type == "REPLICATE":
            if not self.is_leader:
                state = message["state"]
                if state.get("version", 0) >= self.get_state().get("version", 0):
                    self.set_state(state)
            return {"state_version": self.get_state().get("version", 0)}
        elif message_type == "STATE_REQUEST" and self.is_leader:
            return {"state": self.get_state()}
        elif message_type == "PEER_HELLO":
            server_id = int(message["server_id"])
            if server_id != self.config.server_id:
                is_new = self.register_peer(message, directly_seen=True)
                if is_new:
                    await self.start_election(force=True)
        elif message_type == "CONTROL_HEARTBEAT":
            new_peers = []
            announced_leader = message.get("leader_id")
            if self.leader_id is None and isinstance(announced_leader, int):
                self.leader_id = announced_leader
            for member in message.get("members", []):
                if int(member["server_id"]) != self.config.server_id:
                    if self.register_peer(member, directly_seen=False):
                        new_peers.append(int(member["server_id"]))
            if new_peers:
                logging.info("Ring aktualisiert: %s", self.ring())
                if self.is_leader:
                    for server_id in new_peers:
                        await self.replicate_to_peer(server_id)
                elif self.leader_id in self.peers:
                    await self.synchronize_from_leader()
                await self.start_election(force=True)
        return None

    async def start_election(self, force=False):
        async with self.election_lock:
            if self.participant and not force:
                return
            self.participant = True
            message = {
                "type": "ELECTION",
                "candidate": self.config.server_id,
            }
            successor = self.successor()
            logging.info("LCR-Wahl gestartet; Nachfolger ist Server %s", successor)
            response = await self.send_control(message, successor)
            if response is None and successor != self.config.server_id:
                self.remove_peer(successor)
                self.participant = False
                asyncio.create_task(self.start_election(force=True))

    async def handle_election(self, message):
        candidate = int(message["candidate"])
        if candidate == self.config.server_id:
            self.participant = False
            await self.become_leader()
            return

        if candidate > self.config.server_id:
            self.participant = True
            forwarded = {"type": "ELECTION", "candidate": candidate}
        elif not self.participant:
            self.participant = True
            forwarded = {
                "type": "ELECTION",
                "candidate": self.config.server_id,
            }
        else:
            return
        await self.send_control(forwarded, self.successor())

    async def become_leader(self):
        self.leader_id = self.config.server_id
        logging.info("Server %s ist neuer Leader.", self.config.server_id)
        if len(self.ring()) > 1:
            await self.send_control(
                {
                    "type": "LEADER",
                    "leader_id": self.config.server_id,
                    "origin": self.config.server_id,
                },
                self.successor(),
            )
        await self.became_leader()

    async def handle_leader(self, message):
        leader_id = int(message["leader_id"])
        origin = int(message["origin"])
        self.leader_id = leader_id
        self.participant = False
        logging.info("LCR-Ergebnis: Server %s ist Leader.", leader_id)

        if self.config.server_id != origin:
            await self.send_control(message, self.successor())

        if self.is_leader:
            await self.became_leader()
        else:
            response = await self.send_control({"type": "STATE_REQUEST"}, leader_id)
            if response and "state" in response:
                self.set_state(response["state"])

    async def replicate_state(self):
        if not self.is_leader:
            return set()
        state = copy.deepcopy(self.get_state())
        version = state.get("version", 0)
        server_ids = list(self.peers)
        responses = await asyncio.gather(
            *[
                self.send_control(
                    {"type": "REPLICATE", "state": state}, server_id
                )
                for server_id in server_ids
            ],
            return_exceptions=True,
        )
        acknowledged = {
            server_id
            for server_id, response in zip(server_ids, responses)
            if isinstance(response, dict)
            and response.get("state_version") == version
        }
        missing = set(server_ids) - acknowledged
        if missing:
            logging.warning(
                "Zustand %s nicht von Backups %s bestätigt.",
                version,
                sorted(missing),
            )
        return acknowledged

    async def replicate_to_peer(self, server_id):
        state = copy.deepcopy(self.get_state())
        response = await self.send_control(
            {"type": "REPLICATE", "state": state}, server_id
        )
        return bool(
            response
            and response.get("state_version") == state.get("version", 0)
        )

    async def synchronize_from_leader(self):
        if self.leader_id == self.config.server_id:
            return True
        response = await self.send_control(
            {"type": "STATE_REQUEST"}, self.leader_id
        )
        if response and "state" in response:
            self.set_state(response["state"])
            return True
        return False

    async def stop(self):
        await self.broadcast_announcement("SERVER_LEAVE")
        for task in self.tasks:
            task.cancel()
        await self.control.stop()
        self.discovery.close()
