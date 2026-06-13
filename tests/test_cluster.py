"""Tests fuer Ringbildung, LCR-Wahl und Zustandsreplikation."""

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quizbattle.cluster import ClusterManager
from quizbattle.game import initial_state
from quizbattle.settings import ServerConfig


UUID_10 = "00000000-0000-0000-0000-000000000010"
UUID_20 = "00000000-0000-0000-0000-000000000020"
UUID_30 = "00000000-0000-0000-0000-000000000030"


def config(server_uuid=UUID_20):
    """Erzeuge eine kleine Serverkonfiguration fuer isolierte Clustertests."""
    return ServerConfig(
        server_uuid=server_uuid,
        host="192.168.1.20",
        bind_host="0.0.0.0",
        ws_port=5000,
        control_port=6000,
        discovery_port=5972,
        broadcast_ip="192.168.1.255",
    )


def cluster(server_uuid=UUID_20):
    """Erzeuge einen ClusterManager ohne echte Netzwerkverbindungen."""
    state = initial_state()
    return ClusterManager(
        config(server_uuid),
        get_state=lambda: state,
        set_state=lambda _state: None,
        became_leader=lambda: None,
    )


class ClusterTests(unittest.IsolatedAsyncioTestCase):
    """Pruefe zentrale Regeln des Serverclusters."""

    def test_ring_is_sorted_and_wraps(self):
        """Der Ring muss sortiert sein und nach der groessten UUID umbrechen."""
        manager = cluster(UUID_30)
        manager.peers = {
            UUID_20: {"host": "x", "control_port": 1},
            UUID_10: {"host": "x", "control_port": 1},
        }
        self.assertEqual(manager.ring(), [UUID_10, UUID_20, UUID_30])
        self.assertEqual(manager.successor(), UUID_10)

    def test_stale_gossip_cannot_revive_failed_server(self):
        """Indirekte alte Daten duerfen einen ausgefallenen Peer nicht reaktivieren."""
        manager = cluster()
        manager.dead_peers.add(UUID_30)
        changed = manager.register_peer(
            {
                "server_uuid": UUID_30,
                "host": "192.168.1.30",
                "ws_port": 5000,
                "control_port": 6000,
            },
            directly_seen=False,
        )
        self.assertFalse(changed)
        self.assertNotIn(UUID_30, manager.peers)

    async def test_lcr_replaces_smaller_candidate_with_own_uuid(self):
        """LCR ersetzt eine kleinere Kandidaten-UUID durch die eigene UUID."""
        manager = cluster(UUID_20)
        manager.peers = {
            UUID_30: {"host": "x", "control_port": 1},
            UUID_10: {"host": "x", "control_port": 1},
        }
        sent = []

        async def capture(message, server_uuid, retries=3):
            """Zeichne den simulierten Kontrollversand fuer die Pruefung auf."""
            sent.append((message, server_uuid))
            return {"type": "CONTROL_ACK"}

        manager.send_control = capture
        await manager.handle_election({"candidate": UUID_10})
        self.assertEqual(sent[0][0]["candidate"], UUID_20)
        self.assertEqual(sent[0][1], UUID_30)

    async def test_returning_own_uuid_elects_server_as_leader(self):
        """Eine vollständig umlaufene eigene UUID gewinnt die LCR-Wahl."""
        manager = cluster(UUID_30)
        manager.peers = {
            UUID_10: {"host": "x", "control_port": 1},
            UUID_20: {"host": "x", "control_port": 1},
        }
        announcements = []
        became_leader = []

        async def capture(message, server_uuid, retries=3):
            """Zeichne die Leader-Bekanntgabe an den Nachfolger auf."""
            announcements.append((message, server_uuid))
            return {"type": "CONTROL_ACK"}

        async def mark_leader():
            """Merke den Aufruf des anwendungsspezifischen Leader-Callbacks."""
            became_leader.append(True)

        manager.send_control = capture
        manager.became_leader = mark_leader
        await manager.handle_election({"candidate": UUID_30})

        self.assertEqual(manager.leader_uuid, UUID_30)
        self.assertEqual(announcements[0][0]["leader_uuid"], UUID_30)
        self.assertEqual(announcements[0][1], UUID_10)
        self.assertEqual(became_leader, [True])

    async def test_replication_requires_matching_version_ack(self):
        """Nur ein ACK derselben Version gilt als erfolgreiche Replikation."""
        state = initial_state()
        state["version"] = 7
        manager = ClusterManager(
            config(UUID_30),
            get_state=lambda: state,
            set_state=lambda _state: None,
            became_leader=lambda: None,
        )
        manager.leader_uuid = UUID_30
        manager.peers = {
            UUID_10: {"host": "x", "control_port": 1},
            UUID_20: {"host": "x", "control_port": 1},
        }

        async def acknowledge(_message, server_uuid, retries=3):
            """Simuliere ein aktuelles und ein veraltetes Backup-ACK."""
            version = 7 if server_uuid == UUID_10 else 6
            return {"state_version": version}

        manager.send_control = acknowledge
        with self.assertLogs(level="WARNING"):
            self.assertEqual(await manager.replicate_state(), {UUID_10})


if __name__ == "__main__":
    unittest.main()
