"""Offline coordinator checks with synthetic packet and real hard-link publication."""

import copy
import hashlib
import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from orchestrator.coordinate_handoff import main as cli_main
from orchestrator.core.handoff import HandoffError
from orchestrator.core.handoff_coordinator import ReceiptCoordinator
from orchestrator.handoff import publish_receipt
from tests.unit.test_handoff import fixture_manifest


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.packet = self.root / "packet"
        self.packet.mkdir()
        self.receipts = self.root / "receipts"
        self.receipts.mkdir()
        self.db = self.root / "ledger.sqlite"
        self.manifest, self.outputs = fixture_manifest()
        self.trust = self.write_packet()
        self.coordinator = ReceiptCoordinator(self.db, self.receipts)

    def write_packet(self):
        raw = json.dumps(self.manifest, sort_keys=True).encode("utf-8")
        (self.packet / "manifest.json").write_bytes(raw)
        for name, content in self.outputs.items():
            (self.packet / name).write_bytes(content)
        return {"manifest_sha256": digest(raw), "run_id": self.manifest["run_id"],
                "attempt_id": self.manifest["attempt_id"],
                "output_versions": {item["path"]: item["storage"]["version"]
                                    for item in self.manifest["outputs"]}}

    def test_fixed_path_pins_and_existing_task_table(self):
        existing_db = self.root / "existing-ledger.sqlite"
        with closing(sqlite3.connect(existing_db)) as conn:
            conn.execute("CREATE TABLE task_states (task_id TEXT PRIMARY KEY)")
            conn.execute("INSERT INTO task_states VALUES ('existing')")
            conn.commit()
        coordinator = ReceiptCoordinator(existing_db, self.receipts)
        path, token, state = coordinator.reserve(self.trust)
        self.assertEqual(state, "RESERVED")
        self.assertEqual((path, token, state), coordinator.reserve(self.trust))
        changed = copy.deepcopy(self.trust)
        changed["manifest_sha256"] = "a" * 64
        with self.assertRaisesRegex(HandoffError, "different path or trusted pins"):
            coordinator.reserve(changed)
        with closing(sqlite3.connect(existing_db)) as conn:
            self.assertEqual(conn.execute("SELECT task_id FROM task_states").fetchone()[0], "existing")

    def test_hash_failure_then_same_attempt_retry_and_distinct_attempt(self):
        original = self.outputs["clarification.txt"]
        (self.packet / "clarification.txt").write_bytes(b"X" + original[1:])
        with self.assertRaisesRegex(HandoffError, "hash differs"):
            self.coordinator.collect(self.packet, self.trust)
        path, _, state = self.coordinator.reserve(self.trust)
        self.assertEqual(state, "RESERVED")
        self.assertFalse(path.exists())
        (self.packet / "clarification.txt").write_bytes(self.outputs["clarification.txt"])
        got, receipt = self.coordinator.collect(self.packet, self.trust)
        self.assertEqual((got, receipt["status"]), (path, "COLLECTED"))
        self.assertEqual(self.coordinator.collect(self.packet, self.trust)[0], path)
        self.manifest["attempt_id"] = "attempt-2"
        next_trust = self.write_packet()
        next_path, _ = self.coordinator.collect(self.packet, next_trust)
        self.assertNotEqual(next_path, path)

    def test_interruption_after_reservation_and_after_publication(self):
        path, _, _ = self.coordinator.reserve(self.trust)
        self.assertFalse(path.exists())
        def publish_then_interrupt(target, receipt):
            publish_receipt(target, receipt)
            raise KeyboardInterrupt()
        with (
            patch("orchestrator.core.handoff_coordinator.publish_receipt", publish_then_interrupt),
            self.assertRaises(KeyboardInterrupt),
        ):
            self.coordinator.collect(self.packet, self.trust)
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(conn.execute(
                "SELECT state FROM handoff_receipt_reservations").fetchone()[0], "RESERVED")
        self.assertEqual(self.coordinator.collect(self.packet, self.trust)[0], path)
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(conn.execute(
                "SELECT state FROM handoff_receipt_reservations").fetchone()[0], "COLLECTED")
        data = json.loads(path.read_bytes())
        data["outputs"] = []
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(HandoffError, "integrity check failed"):
            self.coordinator.collect(self.packet, self.trust)

    def test_concurrent_same_attempt_has_one_receipt(self):
        barrier = threading.Barrier(2)
        results = []
        failures = []
        def publish(target, receipt):
            barrier.wait(timeout=5)
            publish_receipt(target, receipt)
        def worker():
            try:
                results.append(self.coordinator.collect(self.packet, self.trust)[0])
            except (HandoffError, OSError) as exc:
                failures.append(exc)
        with patch("orchestrator.core.handoff_coordinator.publish_receipt", publish):
            threads = [threading.Thread(target=worker) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)
        self.assertFalse(failures, failures)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0], results[1])
        self.assertEqual(len(list(self.receipts.glob("*.json"))), 1)

    def test_changed_directory_preexisting_file_and_missing_collected_fail_closed(self):
        alternate = self.root / "other-receipts"
        alternate.mkdir()
        self.coordinator.reserve(self.trust)
        with self.assertRaisesRegex(HandoffError, "different path"):
            ReceiptCoordinator(self.db, alternate).reserve(self.trust)
        path, _, _ = self.coordinator.reserve(self.trust)
        path.write_text('{"status":"COLLECTED"}', encoding="utf-8")
        with self.assertRaisesRegex(HandoffError, "integrity check failed"):
            self.coordinator.collect(self.packet, self.trust)
        path.unlink()
        self.coordinator.collect(self.packet, self.trust)
        path.unlink()
        with self.assertRaisesRegex(HandoffError, "missing"):
            self.coordinator.collect(self.packet, self.trust)

    def test_publication_denial_keeps_reservation_without_success(self):
        def denied(path, receipt):
            raise PermissionError("hard link refused")
        with (
            patch("orchestrator.core.handoff_coordinator.publish_receipt", denied),
            self.assertRaisesRegex(PermissionError, "hard link refused"),
        ):
            self.coordinator.collect(self.packet, self.trust)
        path, _, state = self.coordinator.reserve(self.trust)
        self.assertEqual(state, "RESERVED")
        self.assertFalse(path.exists())

    def test_cli_coordinate_handoff_lifecycle(self):
        trust_file = self.root / "trust.json"
        trust_file.write_text(json.dumps(self.trust), encoding="utf-8")
        args = ["--packet", str(self.packet), "--trust", str(trust_file),
                "--db", str(self.db), "--receipt-dir", str(self.receipts)]
        with patch("sys.stdout"), patch("sys.stderr"):
            self.assertEqual(cli_main(args), 0)
            # Replaying via CLI reconciles existing receipt without error
            self.assertEqual(cli_main(args), 0)

    def test_existing_mac_rejection_and_version_validation(self):
        def return_pre_maced(packet_dir, trust):
            return {"schema_version": "0.1", "status": "COLLECTED",
                    "run_id": trust["run_id"], "attempt_id": trust["attempt_id"],
                    "manifest_sha256": trust["manifest_sha256"],
                    "outputs": [], "missing_optional": [], "next_step": "",
                    "verification": "", "coordinator_mac": "x" * 64}
        with (
            patch("orchestrator.core.handoff_coordinator.collect_receipt", return_pre_maced),
            self.assertRaisesRegex(HandoffError, "already contains coordinator_mac"),
        ):
            self.coordinator.collect(self.packet, self.trust)

        def return_wrong_version(packet_dir, trust):
            return {"schema_version": "0.1", "status": "COLLECTED",
                    "run_id": trust["run_id"], "attempt_id": trust["attempt_id"],
                    "manifest_sha256": trust["manifest_sha256"],
                    "outputs": [{"path": "clarification.txt", "size_bytes": 10,
                                 "sha256": "a" * 64, "version": "999"}],
                    "missing_optional": [], "next_step": "", "verification": ""}
        with (
            patch("orchestrator.core.handoff_coordinator.collect_receipt", return_wrong_version),
            self.assertRaisesRegex(HandoffError, "output version differs from trusted pins"),
        ):
            self.coordinator.collect(self.packet, self.trust)

    def test_optional_missing_output_coordinator_lifecycle(self):
        self.manifest["outputs"][0]["required"] = False
        self.trust = self.write_packet()
        (self.packet / "clarification.txt").unlink()
        (self.packet / "unlisted-raw-log.txt").write_text("not allowlisted")

        path, receipt = self.coordinator.collect(self.packet, self.trust)
        self.assertEqual(receipt["missing_optional"], ["clarification.txt"])
        self.assertEqual([item["path"] for item in receipt["outputs"]], ["report.xml"])
        self.assertEqual(receipt["status"], "COLLECTED")
        self.assertTrue(path.exists())

        reconciled_path, reconciled_receipt = self.coordinator.collect(self.packet, self.trust)
        self.assertEqual(reconciled_path, path)
        self.assertEqual(reconciled_receipt["missing_optional"], ["clarification.txt"])
        self.assertEqual([item["path"] for item in reconciled_receipt["outputs"]], ["report.xml"])
        self.assertEqual(reconciled_receipt["coordinator_mac"], receipt["coordinator_mac"])


if __name__ == "__main__":
    unittest.main()
