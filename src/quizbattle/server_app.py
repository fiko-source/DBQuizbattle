"""Verknuepfung von WebSocket-Clients, Spiellogik und Servercluster."""

import asyncio
import json
import logging
import time

import websockets

from .cluster import ClusterManager
from .game import QuizGame
from .settings import CLIENT_RETRY_INTERVAL, MIN_PLAYERS


class QuizServer:
    """Betreibe den aktiven Spielserver und seine Clientverbindungen."""

    def __init__(self, config):
        """Erzeuge Spiel und Cluster mit gemeinsamen Callback-Funktionen."""
        self.config = config
        self.connections = {}
        self.client_acks = {}
        self.client_last_send = {}
        self.game_task = None
        self.retry_task = None
        self.ws_server = None

        self.game = QuizGame(
            connected_tokens=lambda: set(self.connections),
            emit_event=self.emit_event,
            replicate_state=self.replicate_state,
        )
        self.cluster = ClusterManager(
            config=config,
            get_state=lambda: self.game.state,
            set_state=self.game.replace_state,
            became_leader=self.on_became_leader,
        )

    async def start(self):
        """Starte WebSocket und Cluster und halte den Serverprozess am Leben."""
        self.ws_server = await websockets.serve(
            self.handle_client,
            self.config.bind_host,
            self.config.ws_port,
        )
        await self.cluster.start()
        self.retry_task = asyncio.create_task(self.client_retry_loop())
        logging.info(
            "Server %s: ws://%s:%s, control TCP %s, discovery UDP %s",
            self.config.server_id,
            self.config.host,
            self.config.ws_port,
            self.config.control_port,
            self.config.discovery_port,
        )
        # Ein nie abgeschlossener Future haelt den Haupttask aktiv. Beendet wird
        # der Prozess durch Abbruch, worauf main() stop() aufruft.
        await asyncio.Future()

    async def on_became_leader(self):
        """Starte den Spielablauf genau einmal, sobald dieser Server Leader wird."""
        if self.game_task and not self.game_task.done():
            return
        self.game_task = asyncio.create_task(
            self.game.run(lambda: self.cluster.is_leader)
        )

    async def replicate_state(self):
        """Delegiere die Zustandsreplikation an den ClusterManager."""
        return await self.cluster.replicate_state()

    async def emit_event(self, event_type, **data):
        """Erzeuge ein geordnetes Spielereignis, repliziere und verteile es."""
        # Der Leader ist der Sequencer: Nur hier wird die globale Nummer erhoeht.
        self.game.state["sequence"] += 1
        self.game.mark_changed()
        event = {
            "type": event_type,
            "seq": self.game.state["sequence"],
            "time": time.time(),
            **data,
        }
        self.game.state["events"].append(event)

        # Primary-backup: backups confirm the event before clients see it.
        await self.replicate_state()
        await self.broadcast_clients(event)
        return event

    async def broadcast_clients(self, event):
        """Sende ein Ereignis an alle verbundenen Clients."""
        payload = json.dumps(event, ensure_ascii=False)
        dead = []
        for token, websocket in list(self.connections.items()):
            try:
                await websocket.send(payload)
                self.client_last_send[token] = time.monotonic()
            except websockets.ConnectionClosed:
                dead.append(token)
        for token in dead:
            self.remove_connection(token)

    async def client_retry_loop(self):
        """Wiederhole das naechste unbestaetigte Ereignis fuer jeden Client."""
        while True:
            await asyncio.sleep(0.5)
            now = time.monotonic()
            for token, websocket in list(self.connections.items()):
                if (
                    now - self.client_last_send.get(token, 0)
                    < CLIENT_RETRY_INTERVAL
                ):
                    continue
                # ACK n bedeutet: Bis einschliesslich n wurde alles geordnet
                # verarbeitet. Daher ist n + 1 das naechste fehlende Ereignis.
                next_seq = self.client_acks.get(token, 0) + 1
                event = self.event_by_sequence(next_seq)
                if event:
                    try:
                        await websocket.send(
                            json.dumps(event, ensure_ascii=False)
                        )
                        self.client_last_send[token] = now
                    except websockets.ConnectionClosed:
                        self.remove_connection(token)

    def event_by_sequence(self, sequence):
        """Suche ein gespeichertes Ereignis anhand seiner Sequenznummer."""
        for event in self.game.state["events"]:
            if event["seq"] == sequence:
                return event
        return None

    async def send_event_range(self, websocket, start, end=None):
        """Sende einen zusammenhaengenden Bereich alter Ereignisse erneut."""
        for event in self.game.state["events"]:
            if event["seq"] >= start and (end is None or event["seq"] <= end):
                await websocket.send(json.dumps(event, ensure_ascii=False))

    async def handle_client(self, websocket):
        """Registriere einen Client und bearbeite seine WebSocket-Sitzung."""
        if not self.cluster.is_leader:
            # Backups akzeptieren keine Spielsitzungen. Der Client startet nach
            # NOT_LEADER automatisch eine neue Discovery.
            await websocket.send(json.dumps({"type": "NOT_LEADER"}))
            await websocket.close()
            return

        token = None
        try:
            raw = await asyncio.wait_for(websocket.recv(), timeout=5)
            hello = json.loads(raw)
            if hello.get("type") != "JOIN":
                return

            # Ein vorhandener Token setzt dieselbe Identitaet samt Punktestand
            # nach Reconnect oder Leaderwechsel fort.
            token = await self.game.add_or_resume_player(
                hello.get("token"), hello.get("name")
            )
            self.connections[token] = websocket
            last_seq = int(hello.get("last_seq", 0))
            self.client_acks[token] = last_seq
            self.client_last_send[token] = time.monotonic()
            player = self.game.state["players"][token]
            logging.info(
                "Client verbunden: %s (Spieler-ID %s), Spieler %s/%s",
                player["name"],
                player["player_id"],
                len(self.connections),
                MIN_PLAYERS,
            )

            await websocket.send(
                json.dumps(
                    {
                        "type": "WELCOME",
                        "token": token,
                        "player_id": player["player_id"],
                        "name": player["name"],
                        "score": self.game.state["scores"].get(token, 0),
                    },
                    ensure_ascii=False,
                )
            )
            # Vor neuen Live-Ereignissen erhaelt der Client alles, was ihm seit
            # seiner letzten bestaetigten Sequenznummer fehlt.
            await self.send_event_range(websocket, last_seq + 1)
            await self.emit_event(
                "PLAYER_COUNT",
                count=len(self.connections),
                minimum=MIN_PLAYERS,
            )

            async for raw in websocket:
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                await self.handle_client_message(token, websocket, message)
        except (asyncio.TimeoutError, websockets.ConnectionClosed):
            pass
        finally:
            if token and self.connections.get(token) is websocket:
                self.remove_connection(token)

    async def handle_client_message(self, token, websocket, message):
        """Verarbeite ACKs, Nachforderungen und Aktionen eines Clients."""
        message_type = message.get("type")
        if message_type == "ACK":
            self.client_acks[token] = max(
                int(message.get("seq", 0)), self.client_acks.get(token, 0)
            )
            return
        if message_type == "RESEND_REQUEST":
            await self.send_event_range(
                websocket,
                int(message.get("from_seq", 1)),
                int(message.get("to_seq", self.game.state["sequence"])),
            )
            return

        status = await self.game.handle_action(token, message)
        if status:
            await websocket.send(
                json.dumps(
                    {
                        "type": "ACTION_STATUS",
                        "request_id": message.get("request_id"),
                        "message": status,
                    }
                )
            )

    def remove_connection(self, token):
        """Entferne eine WebSocket-Verbindung, behalte aber den Spielerzustand."""
        self.connections.pop(token, None)
        self.client_last_send.pop(token, None)
        player = self.game.state["players"].get(token)
        if player:
            logging.info(
                "Client getrennt: %s (Spieler-ID %s), noch %s verbunden",
                player["name"],
                player["player_id"],
                len(self.connections),
            )

    async def stop(self):
        """Beende Hintergrundtasks, Listener und Clusterverbindungen."""
        if self.retry_task:
            self.retry_task.cancel()
        if self.game_task:
            self.game_task.cancel()
        if self.ws_server:
            self.ws_server.close()
            await self.ws_server.wait_closed()
        await self.cluster.stop()
