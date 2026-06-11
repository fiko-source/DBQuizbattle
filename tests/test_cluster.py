"""Tests fuer Ringbildung, LCR-Wahl und Zustandsreplikation."""

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quizbattle.cluster import ClusterManager
from quizbattle.game import initial_state
from quizbattle.settings import ServerConfig


def config(server_id=20):
    """Erzeuge eine kleine Serverkonfiguration fuer isolierte Clustertests."""
    return ServerConfig(
        server_id=server_id,
        host=f"192.168.1.{server_id}",
        bind_host="0.0.0.0",
        ws_port=5000,
        control_port=6000,
        discovery_port=5972,
        broadcast_ip="192.168.1.255",
    )


def cluster(server_id=20):
    """Erzeuge einen ClusterManager ohne echte Netzwerkverbindungen."""
    state = initial_state()
    return ClusterManager(
        config(server_id),
        get_state=lambda: state,
        set_state=lambda _state: None,
        became_leader=lambda: None,
    )


class ClusterTests(unittest.IsolatedAsyncioTestCase):
    """Pruefe zentrale Regeln des Serverclusters."""

    def test_ring_is_sorted_and_wraps(self):
        """Der Ring muss sortiert sein und nach der groessten ID umbrechen."""
        manager = cluster(30)
        manager.peers = {
            20: {"host": "x", "control_port": 1},
            10: {"host": "x", "control_port": 1},
        }
        self.assertEqual(manager.ring(), [10, 20, 30])
        self.assertEqual(manager.successor(), 10)

    def test_stale_gossip_cannot_revive_failed_server(self):
        """Indirekte alte Daten duerfen einen ausgefallenen Peer nicht reaktivieren."""
        manager = cluster()
        manager.dead_peers.add(30)
        changed = manager.register_peer(
            {
                "server_id": 30,
                "host": "192.168.1.30",
                "ws_port": 5000,
                "control_port": 6000,
            },
            directly_seen=False,
        )
        self.assertFalse(changed)
        self.assertNotIn(30, manager.peers)

    async def test_lcr_replaces_smaller_candidate_with_own_id(self):
        """LCR ersetzt eine kleinere Kandidaten-ID durch die eigene ID."""
        manager = cluster(20)
        manager.peers = {
            30: {"host": "x", "control_port": 1},
            10: {"host": "x", "control_port": 1},
        }
        sent = []

        async def capture(message, server_id, retries=3):
            """Zeichne den simulierten Kontrollversand fuer die Pruefung auf."""
            sent.append((message, server_id))
            return {"type": "CONTROL_ACK"}

        manager.send_control = capture
        await manager.handle_election({"candidate": 10})
        self.assertEqual(sent[0][0]["candidate"], 20)
        self.assertEqual(sent[0][1], 30)

    async def test_replication_requires_matching_version_ack(self):
        """Nur ein ACK derselben Version gilt als erfolgreiche Replikation."""
        state = initial_state()
        state["version"] = 7
        manager = ClusterManager(
            config(30),
            get_state=lambda: state,
            set_state=lambda _state: None,
            became_leader=lambda: None,
        )
        manager.leader_id = 30
        manager.peers = {
            10: {"host": "x", "control_port": 1},
            20: {"host": "x", "control_port": 1},
        }

        async def acknowledge(_message, server_id, retries=3):
            """Simuliere ein aktuelles und ein veraltetes Backup-ACK."""
            version = 7 if server_id == 10 else 6
            return {"state_version": version}

        manager.send_control = acknowledge
        with self.assertLogs(level="WARNING"):
            self.assertEqual(await manager.replicate_state(), {10})


if __name__ == "__main__":
    unittest.main()
