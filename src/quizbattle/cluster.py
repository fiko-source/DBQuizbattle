"""Servercluster mit Discovery, Heartbeats, LCR-Wahl und Replikation."""

import asyncio
import copy
import logging
import time

from .control import ReliableControlChannel
from .discovery import BroadcastEndpoint
from .identity import normalize_uuid, uuid_order_key
from .settings import (
    HEARTBEAT_INTERVAL,
    HEARTBEAT_LOG_INTERVAL,
    HEARTBEAT_TIMEOUT,
)


class ClusterManager:
    """Verwalte bekannte Server und den replizierten Primary-Backup-Verbund."""

    def __init__(self, config, get_state, set_state, became_leader):
        """Baue Discovery und Kontrollkanal um die Serverkonfiguration auf."""
        self.config = config
        self.get_state = get_state
        self.set_state = set_state
        self.became_leader = became_leader

        self.peers = {}
        self.dead_peers = set()
        self.leader_uuid = None
        self.participant = False
        self.last_heartbeat_log = 0.0

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
        """Zeige an, ob dieser Prozess momentan der gewaehlte Leader ist."""
        return self.leader_uuid == self.config.server_uuid

    def ring(self):
        """Gib alle bekannten Server-UUIDs in der logischen Ringreihenfolge zurueck."""
        return sorted(
            [self.config.server_uuid, *self.peers],
            key=uuid_order_key,
        )

    def successor(self):
        """Bestimme den naechsten Server im zyklischen, sortierten Ring."""
        ring = self.ring()
        index = ring.index(self.config.server_uuid)
        return ring[(index + 1) % len(ring)]

    async def start(self):
        """Starte Netzwerkdienste, entdecke Peers und beginne die erste Wahl."""
        await self.discovery.start()
        await self.control.start()
        logging.info(
            "Cluster gestartet: Server %s, WebSocket %s:%s, Control TCP %s, "
            "Discovery UDP %s, Heartbeat alle %.0fs, Timeout %.0fs",
            self.config.server_uuid,
            self.config.host,
            self.config.ws_port,
            self.config.control_port,
            self.config.discovery_port,
            HEARTBEAT_INTERVAL,
            HEARTBEAT_TIMEOUT,
        )
        self.tasks.extend(
            [
                asyncio.create_task(self.heartbeat_loop()),
                asyncio.create_task(self.peer_monitor_loop()),
            ]
        )
        await self.send_discovery({"type": "SERVER_DISCOVER"})
        await self.broadcast_announcement("SERVER_JOIN")
        # Kurze Sammelzeit: vorhandene Server koennen auf Discovery antworten,
        # bevor aus der bekannten Ringansicht eine Wahl gestartet wird.
        await asyncio.sleep(1.5)
        await self.start_election(force=True)

    def server_address(self):
        """Erzeuge die im Netzwerk bekannt gegebene Beschreibung dieses Servers."""
        return {
            "server_uuid": self.config.server_uuid,
            "host": self.config.host,
            "ws_port": self.config.ws_port,
            "control_port": self.config.control_port,
            "leader_uuid": self.leader_uuid,
        }

    def server_message(self, message_type):
        """Ergaenze einen Nachrichtentyp um die eigene Serveradresse."""
        return {"type": message_type, **self.server_address()}

    async def send_discovery(self, message, target=None):
        """Sende eine UDP-Nachricht und ergaenze bei Servermeldungen die Adresse."""
        payload = {**message}
        if message.get("type", "").startswith("SERVER_"):
            payload = {**self.server_address(), **message}
        self.discovery.send(payload, target)

    async def broadcast_announcement(self, message_type):
        """Sende eine Servermeldung an alle Teilnehmer im lokalen Netz."""
        await self.send_discovery(self.server_message(message_type))

    def should_log_heartbeat(self):
        """Drossele normale Heartbeat-Logs, ohne das Senden zu verlangsamen."""
        now = time.monotonic()
        if now - self.last_heartbeat_log >= HEARTBEAT_LOG_INTERVAL:
            self.last_heartbeat_log = now
            return True
        return False

    async def handle_discovery(self, message, address):
        """Verarbeite Clientsuche sowie Beitritt, Heartbeat und Austritt von Servern."""
        message_type = message.get("type")
        if message_type == "CLIENT_DISCOVER":
            # Laut Architektur antwortet nur der aktuelle Leader. Ein Client
            # braucht keine Liste der Backups, sondern genau einen Einstiegspunkt.
            if self.is_leader:
                logging.info(
                    "Client-Discovery von %s:%s beantwortet: Ich bin der Leader.",
                    address[0],
                    address[1],
                )
                await self.send_discovery(
                    {
                        "type": "LEADER_RESPONSE",
                        "server_uuid": self.config.server_uuid,
                        "host": self.config.host,
                        "ws_port": self.config.ws_port,
                    },
                    address,
                )
            return

        if message_type == "SERVER_DISCOVER":
            # Die direkte Antwort geht an den zufaelligen Absenderport des neuen
            # Servers und enthaelt alle Daten fuer spaetere TCP-Verbindungen.
            logging.info("SERVER_DISCOVER von %s:%s empfangen.", address[0], address[1])
            await self.send_discovery(self.server_message("SERVER_JOIN"), address)
            return

        if message_type not in {"SERVER_JOIN", "HEARTBEAT", "SERVER_LEAVE"}:
            return
        try:
            server_uuid = normalize_uuid(message.get("server_uuid"))
        except (TypeError, ValueError, AttributeError):
            return
        if server_uuid == self.config.server_uuid:
            return

        if message_type == "SERVER_LEAVE":
            # Ein sauber beendeter Leader loest sofort eine Neuwahl aus; bei
            # einem Absturz uebernimmt dies spaeter der Heartbeat-Monitor.
            was_leader = server_uuid == self.leader_uuid
            self.remove_peer(server_uuid)
            if was_leader:
                await self.start_election(force=True)
            return

        is_new = self.register_peer(message, directly_seen=True)
        announced_leader = message.get("leader_uuid")
        if self.leader_uuid is None and announced_leader:
            self.leader_uuid = normalize_uuid(announced_leader)
        if message_type == "HEARTBEAT":
            if self.should_log_heartbeat():
                logging.info(
                    "PONG UDP Broadcast: HEARTBEAT von Server %s gesehen.",
                    server_uuid,
                )

        if message_type == "SERVER_JOIN":
            logging.info("SERVER_JOIN von %s empfangen.", server_uuid)
            await self.send_discovery(self.server_message("HEARTBEAT"), address)
        if is_new:
            logging.info("Server %s entdeckt. Ring: %s", server_uuid, self.ring())
            # PEER_HELLO bestaetigt die Erreichbarkeit ueber den zuverlaessigen
            # TCP-Kanal und gleicht danach Wahl und Zustand ab.
            await self.send_control(
                self.server_message("PEER_HELLO"), server_uuid
            )
            if self.is_leader:
                await self.replicate_to_peer(server_uuid)
            elif self.leader_uuid in self.peers:
                await self.synchronize_from_leader()
            await self.start_election(force=True)

    def register_peer(self, message, directly_seen=True):
        """Speichere oder aktualisiere einen Server in der lokalen Ringansicht."""
        server_uuid = normalize_uuid(message["server_uuid"])
        # Ein nur ueber andere Server gemeldeter Peer darf einen bereits als
        # ausgefallen erkannten Eintrag nicht versehentlich wiederbeleben.
        if not directly_seen and server_uuid in self.dead_peers:
            return False
        if directly_seen:
            self.dead_peers.discard(server_uuid)

        is_new = server_uuid not in self.peers
        last_seen = time.monotonic()
        if not is_new and not directly_seen:
            last_seen = self.peers[server_uuid]["last_seen"]
        self.peers[server_uuid] = {
            "host": message["host"],
            "ws_port": int(message["ws_port"]),
            "control_port": int(message["control_port"]),
            "last_seen": last_seen,
        }
        return is_new

    def remove_peer(self, server_uuid):
        """Entferne einen Server und merke ihn als ausgefallen."""
        self.peers.pop(server_uuid, None)
        self.dead_peers.add(server_uuid)
        self.control.forget_peer(server_uuid)

    async def heartbeat_loop(self):
        """Melde die eigene Erreichbarkeit und verteile regelmaessig die Ringansicht."""
        while True:
            # UDP macht neue und bestehende Server im LAN schnell sichtbar.
            log_heartbeat = self.should_log_heartbeat()
            if log_heartbeat:
                logging.info(
                    "PING UDP Broadcast: HEARTBEAT an %s:%s",
                    self.config.broadcast_ip,
                    self.config.discovery_port,
                )
            await self.broadcast_announcement("HEARTBEAT")
            heartbeat = {
                "type": "CONTROL_HEARTBEAT",
                "leader_uuid": self.leader_uuid,
                "members": [
                    {
                        "server_uuid": server_uuid,
                        "host": peer["host"],
                        "ws_port": peer["ws_port"],
                        "control_port": peer["control_port"],
                    }
                    for server_uuid, peer in self.peers.items()
                ],
            }
            # Der zusaetzliche bestaetigte TCP-Heartbeat prueft die tatsaechliche
            # Erreichbarkeit und verteilt bekannte Mitglieder als Gossip.
            peer_ids = list(self.peers)
            if log_heartbeat and peer_ids:
                logging.info(
                    "PING TCP Control: CONTROL_HEARTBEAT an %s",
                    sorted(peer_ids),
                )
            responses = await asyncio.gather(
                *[
                    self.send_control(heartbeat, server_uuid, retries=1)
                    for server_uuid in peer_ids
                ],
                return_exceptions=True,
            )
            for server_uuid, response in zip(peer_ids, responses):
                if isinstance(response, dict) and response.get("type") == "CONTROL_ACK":
                    if log_heartbeat:
                        logging.info(
                            "PONG TCP Control von Server %s erhalten.",
                            server_uuid,
                        )
                elif isinstance(response, Exception):
                    logging.warning(
                        "Kein PONG von Server %s: %s", server_uuid, response
                    )
                else:
                    logging.warning("Kein PONG von Server %s erhalten.", server_uuid)
            await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def peer_monitor_loop(self):
        """Entferne Server ohne rechtzeitigen Heartbeat und starte falls noetig eine Wahl."""
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            now = time.monotonic()
            expired = [
                server_uuid
                for server_uuid, peer in self.peers.items()
                if now - peer["last_seen"] > HEARTBEAT_TIMEOUT
            ]
            leader_failed = self.leader_uuid in expired
            for server_uuid in expired:
                self.remove_peer(server_uuid)
                logging.warning(
                    "Server %s ausgefallen. Ring: %s",
                    server_uuid,
                    self.ring(),
                )
            if expired and (leader_failed or self.leader_uuid not in self.ring()):
                await self.start_election(force=True)

    async def control_sender_seen(self, sender):
        """Aktualisiere einen Peer, sobald eine TCP-Nachricht von ihm eintrifft."""
        sender_is_new = self.register_peer(sender, directly_seen=True)
        if sender_is_new and self.is_leader:
            await self.replicate_to_peer(
                normalize_uuid(sender["server_uuid"])
            )

    async def send_control(self, message, server_uuid, retries=3):
        """Leite eine Kontrollnachricht an den zuverlaessigen TCP-Kanal weiter."""
        return await self.control.send(message, server_uuid, retries)

    async def handle_control(self, message):
        """Verteile eingehende Kontrollnachrichten auf Wahl und Replikation."""
        message_type = message.get("type")
        if message_type == "ELECTION":
            await self.handle_election(message)
        elif message_type == "LEADER":
            await self.handle_leader(message)
        elif message_type == "REPLICATE":
            # Nur Backups uebernehmen replizierte Zustaende. Aeltere Versionen
            # werden verworfen, falls Nachrichten verspaetet eintreffen.
            if not self.is_leader:
                state = message["state"]
                if state.get("version", 0) >= self.get_state().get("version", 0):
                    self.set_state(state)
            return {"state_version": self.get_state().get("version", 0)}
        elif message_type == "STATE_REQUEST" and self.is_leader:
            return {"state": self.get_state()}
        elif message_type == "PEER_HELLO":
            server_uuid = normalize_uuid(message["server_uuid"])
            if server_uuid != self.config.server_uuid:
                is_new = self.register_peer(message, directly_seen=True)
                if is_new:
                    await self.start_election(force=True)
        elif message_type == "CONTROL_HEARTBEAT":
            sender = message.get("sender", {})
            sender_uuid = sender.get("server_uuid")
            if sender_uuid and self.should_log_heartbeat():
                logging.info("PING TCP Control von Server %s empfangen.", sender_uuid)
            # Mitglieder aus fremden Ringansichten werden indirekt registriert.
            # Erst direkter Kontakt entfernt sie aus dead_peers.
            new_peers = []
            announced_leader = message.get("leader_uuid")
            if self.leader_uuid is None and announced_leader:
                self.leader_uuid = normalize_uuid(announced_leader)
            for member in message.get("members", []):
                member_uuid = normalize_uuid(member["server_uuid"])
                if member_uuid != self.config.server_uuid:
                    if self.register_peer(member, directly_seen=False):
                        new_peers.append(member_uuid)
            if new_peers:
                logging.info("Ring aktualisiert: %s", self.ring())
                if self.is_leader:
                    for server_uuid in new_peers:
                        await self.replicate_to_peer(server_uuid)
                elif self.leader_uuid in self.peers:
                    await self.synchronize_from_leader()
                await self.start_election(force=True)
        return None

    async def start_election(self, force=False):
        """Starte eine LCR-Leaderwahl mit der eigenen Server-UUID als Kandidat."""
        async with self.election_lock:
            if self.participant and not force:
                return
            self.participant = True
            message = {
                "type": "ELECTION",
                "candidate": self.config.server_uuid,
            }
            successor = self.successor()
            logging.info("LCR-Wahl gestartet; Nachfolger ist Server %s", successor)
            response = await self.send_control(message, successor)
            if response is None and successor != self.config.server_uuid:
                # Ein nicht erreichbarer Nachfolger wird entfernt. Danach wird
                # die Wahl mit dem naechsten Ringmitglied neu begonnen.
                self.remove_peer(successor)
                self.participant = False
                asyncio.create_task(self.start_election(force=True))

    async def handle_election(self, message):
        """Wende die LCR-Regeln auf eine empfangene Kandidaten-UUID an."""
        candidate = normalize_uuid(message["candidate"])
        # Kehrt die eigene UUID zurueck, ist sie einmal um den Ring gelaufen und
        # damit groesser als alle konkurrierenden UUIDs.
        if candidate == self.config.server_uuid:
            self.participant = False
            await self.become_leader()
            return

        if uuid_order_key(candidate) > uuid_order_key(self.config.server_uuid):
            # Groessere UUIDs werden unveraendert weitergereicht.
            logging.info(
                "LCR: Kandidat %s ist groesser, leite weiter an %s.",
                candidate,
                self.successor(),
            )
            self.participant = True
            forwarded = {"type": "ELECTION", "candidate": candidate}
        elif not self.participant:
            # Eine kleinere UUID wird durch die eigene ersetzt, solange dieser
            # Server in der aktuellen Wahl noch nicht teilgenommen hat.
            logging.info(
                "LCR: Ersetze Kandidat %s durch eigene UUID %s.",
                candidate,
                self.config.server_uuid,
            )
            self.participant = True
            forwarded = {
                "type": "ELECTION",
                "candidate": self.config.server_uuid,
            }
        else:
            return
        await self.send_control(forwarded, self.successor())

    async def become_leader(self):
        """Markiere diesen Server als Leader und verteile das Wahlergebnis."""
        self.leader_uuid = self.config.server_uuid
        logging.info("Ich bin der Leader: Server %s.", self.config.server_uuid)
        if len(self.ring()) > 1:
            await self.send_control(
                {
                    "type": "LEADER",
                    "leader_uuid": self.config.server_uuid,
                    "origin": self.config.server_uuid,
                },
                self.successor(),
            )
        await self.became_leader()

    async def handle_leader(self, message):
        """Uebernehme und leite das im Ring umlaufende Leader-Ergebnis weiter."""
        leader_uuid = normalize_uuid(message["leader_uuid"])
        origin = normalize_uuid(message["origin"])
        self.leader_uuid = leader_uuid
        self.participant = False
        if self.is_leader:
            logging.info("LCR-Ergebnis: Ich bin der Leader.")
        else:
            logging.info("LCR-Ergebnis: Server %s ist der Leader.", leader_uuid)

        if self.config.server_uuid != origin:
            await self.send_control(message, self.successor())

        if self.is_leader:
            await self.became_leader()
        else:
            # Ein Backup zieht nach der Wahl den aktuellen Zustand vom Leader,
            # damit es sofort als Ersatz bereitsteht.
            response = await self.send_control(
                {"type": "STATE_REQUEST"},
                leader_uuid,
            )
            if response and "state" in response:
                self.set_state(response["state"])

    async def replicate_state(self):
        """Sende als Leader eine Zustandskopie parallel an alle Backups."""
        if not self.is_leader:
            return set()
        state = copy.deepcopy(self.get_state())
        version = state.get("version", 0)
        server_uuids = list(self.peers)
        # gather wartet auf alle Backups, ohne die Nachrichten nacheinander zu
        # versenden. Fehler eines einzelnen Backups brechen die anderen nicht ab.
        responses = await asyncio.gather(
            *[
                self.send_control(
                    {"type": "REPLICATE", "state": state}, server_uuid
                )
                for server_uuid in server_uuids
            ],
            return_exceptions=True,
        )
        acknowledged = {
            server_uuid
            for server_uuid, response in zip(server_uuids, responses)
            if isinstance(response, dict)
            and response.get("state_version") == version
        }
        missing = set(server_uuids) - acknowledged
        if missing:
            logging.warning(
                "Zustand %s nicht von Backups %s bestätigt.",
                version,
                sorted(missing),
            )
        elif acknowledged:
            logging.info(
                "Zustand %s von allen Backups bestätigt: %s.",
                version,
                sorted(acknowledged),
            )
        return acknowledged

    async def replicate_to_peer(self, server_uuid):
        """Uebertrage den aktuellen Zustand gezielt an einen neuen Server."""
        state = copy.deepcopy(self.get_state())
        response = await self.send_control(
            {"type": "REPLICATE", "state": state}, server_uuid
        )
        success = bool(
            response
            and response.get("state_version") == state.get("version", 0)
        )
        if success:
            logging.info(
                "Zustand %s an neuen Backup-Server %s repliziert.",
                state.get("version", 0),
                server_uuid,
            )
        else:
            logging.warning(
                "Zustand %s konnte nicht an Backup-Server %s repliziert werden.",
                state.get("version", 0),
                server_uuid,
            )
        return success

    async def synchronize_from_leader(self):
        """Fordere als Backup den vollstaendigen Zustand des Leaders an."""
        if self.leader_uuid == self.config.server_uuid:
            return True
        response = await self.send_control(
            {"type": "STATE_REQUEST"}, self.leader_uuid
        )
        if response and "state" in response:
            self.set_state(response["state"])
            return True
        return False

    async def stop(self):
        """Melde den Austritt und beende alle Cluster-Hintergrundaufgaben."""
        await self.broadcast_announcement("SERVER_LEAVE")
        for task in self.tasks:
            task.cancel()
        await self.control.stop()
        self.discovery.close()
