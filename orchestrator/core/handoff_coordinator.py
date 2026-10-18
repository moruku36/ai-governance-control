"""Local, explicit-DB receipt reservation for offline handoff collection.

The caller supplies an independently trusted pin record and private receipt
directory. This is not a delivery, authentication, or acceptance service.
"""

import hashlib
import hmac
import json
import secrets
import stat
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from orchestrator.core.handoff import HandoffError, collect_receipt, load_json
from orchestrator.core.sqlite_util import connect_wal
from orchestrator.handoff import publish_receipt


def _record_bytes(trust):
    if not isinstance(trust, dict):
        raise HandoffError("Invalid trusted record")
    for name in ("run_id", "attempt_id"):
        value = trust.get(name)
        if not isinstance(value, str) or not value.strip() or len(value) > 256:
            raise HandoffError(f"Invalid trusted {name}")
    digest = trust.get("manifest_sha256")
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise HandoffError("Invalid trusted manifest hash")
    if not isinstance(trust.get("output_versions"), dict):
        raise HandoffError("Invalid trusted output versions")
    try:
        return json.dumps(trust, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise HandoffError("Invalid trusted record") from exc


def _receipt_mac(receipt, token):
    body = json.dumps(receipt, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    return hmac.new(bytes.fromhex(token), body, hashlib.sha256).hexdigest()


def _validate_receipt(receipt, trust):
    if not isinstance(receipt, dict):
        raise HandoffError("Receipt must be a JSON object")
    if any(receipt.get(k) != v for k, v in (
        ("schema_version", "0.1"),
        ("status", "COLLECTED"),
        ("run_id", trust["run_id"]),
        ("attempt_id", trust["attempt_id"]),
        ("manifest_sha256", trust["manifest_sha256"]),
    )):
        raise HandoffError("Receipt differs from reservation metadata")
    outputs = receipt.get("outputs")
    if not isinstance(outputs, list):
        raise HandoffError("Invalid receipt outputs")
    missing_optional = receipt.get("missing_optional")
    if not isinstance(missing_optional, list):
        raise HandoffError("Invalid receipt missing_optional")
    expected_versions = trust.get("output_versions")
    if not isinstance(expected_versions, dict):
        raise HandoffError("Invalid trusted output versions")

    received_paths = set()
    for item in outputs:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise HandoffError("Invalid receipt output item")
        path = item["path"]
        if path in received_paths:
            raise HandoffError("Duplicate output in receipt")
        if path not in expected_versions:
            raise HandoffError("Extra output path in receipt")
        version = item.get("version")
        if not isinstance(version, str) or version != expected_versions[path]:
            raise HandoffError("Receipt output version differs from trusted pins")
        received_paths.add(path)

    missing_paths = set()
    for path in missing_optional:
        if not isinstance(path, str):
            raise HandoffError("Invalid missing_optional item")
        if path in missing_paths:
            raise HandoffError("Duplicate missing_optional path")
        if path in received_paths:
            raise HandoffError("Path appears in both outputs and missing_optional")
        if path not in expected_versions:
            raise HandoffError("Unexpected missing_optional path not in trusted inventory")
        missing_paths.add(path)

    if (received_paths | missing_paths) != set(expected_versions):
        raise HandoffError("Receipt inventory does not match trusted output versions")


class ReceiptCoordinator:
    """Reserve one canonical receipt path per (run_id, attempt_id) in SQLite."""

    def __init__(self, db_path, receipt_dir):
        self.db_path = Path(db_path).resolve()
        self.receipt_dir = Path(receipt_dir).resolve(strict=True)
        if not self.receipt_dir.is_dir():
            raise HandoffError("Receipt directory must exist")
        if not self.db_path.parent.is_dir():
            raise HandoffError("SQLite parent directory must exist")
        with closing(connect_wal(self.db_path)) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS handoff_receipt_reservations (
                run_id TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                receipt_path TEXT NOT NULL UNIQUE,
                trust_sha256 TEXT NOT NULL,
                reservation_token TEXT NOT NULL,
                state TEXT NOT NULL CHECK (state IN ('RESERVED', 'COLLECTED')),
                PRIMARY KEY (run_id, attempt_id)
            )""")

    def _path(self, run_id, attempt_id):
        key = json.dumps([run_id, attempt_id], ensure_ascii=True, separators=(",", ":"))
        return self.receipt_dir / (hashlib.sha256(key.encode("ascii")).hexdigest() + ".json")

    def reserve(self, trust):
        """Atomically fix the path and pins; a changed pin needs a new attempt."""
        trust_hash = hashlib.sha256(_record_bytes(trust)).hexdigest()
        run_id, attempt_id = trust["run_id"], trust["attempt_id"]
        path = self._path(run_id, attempt_id)
        with closing(connect_wal(self.db_path)) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT receipt_path, trust_sha256, reservation_token, state "
                "FROM handoff_receipt_reservations WHERE run_id=? AND attempt_id=?",
                (run_id, attempt_id),
            ).fetchone()
            if row is None:
                token = secrets.token_hex(32)
                conn.execute(
                    "INSERT INTO handoff_receipt_reservations "
                    "(run_id, attempt_id, receipt_path, trust_sha256, reservation_token, state) "
                    "VALUES (?, ?, ?, ?, ?, 'RESERVED')",
                    (run_id, attempt_id, str(path), trust_hash, token),
                )
                state = "RESERVED"
            else:
                saved_path, saved_hash, token, state = row
                if (saved_path, saved_hash) != (str(path), trust_hash):
                    raise HandoffError("Attempt already reserved with different path or trusted pins")
            conn.commit()
        return path, token, state

    @staticmethod
    def _existing(path, trust, token):
        try:
            info = path.lstat()
            if (not stat.S_ISREG(info.st_mode) or
                    getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
                raise HandoffError("Existing receipt is not a regular file")
            with path.open("rb") as stream:
                raw = stream.read(1024 * 1024 + 1)
            receipt = load_json(raw)
        except (OSError, UnicodeError, ValueError) as exc:
            if isinstance(exc, HandoffError):
                raise
            raise HandoffError("Cannot verify existing receipt") from exc
        if not isinstance(receipt, dict):
            raise HandoffError("Existing receipt differs from reservation")
        mac = receipt.pop("coordinator_mac", None)
        if (not isinstance(mac, str) or len(mac) != 64 or
                any(char not in "0123456789abcdef" for char in mac) or
                not hmac.compare_digest(mac, _receipt_mac(receipt, token))):
            raise HandoffError("Existing receipt integrity check failed")
        _validate_receipt(receipt, trust)
        receipt["coordinator_mac"] = mac
        return receipt

    def collect(self, packet_dir, trust):
        """Validate pinned bytes and publish once; reconcile a published receipt."""
        packet = Path(packet_dir).resolve()
        if self.receipt_dir.is_relative_to(packet) or self.db_path.is_relative_to(packet):
            raise HandoffError("Coordinator state must be outside received packet")
        path, token, state = self.reserve(trust)
        if path.exists() or path.is_symlink():
            receipt = self._existing(path, trust, token)
        else:
            if state == "COLLECTED":
                raise HandoffError("Collected receipt is missing; manual reconciliation required")
            receipt = collect_receipt(packet_dir, trust)
            if "coordinator_mac" in receipt:
                raise HandoffError("Receipt already contains coordinator_mac")
            receipt["received_at"] = datetime.now(UTC).isoformat()
            _validate_receipt(receipt, trust)
            receipt["coordinator_mac"] = _receipt_mac(receipt, token)
            try:
                publish_receipt(path, receipt)
            except FileExistsError:
                receipt = self._existing(path, trust, token)
        with closing(connect_wal(self.db_path)) as conn:
            conn.execute("BEGIN IMMEDIATE")
            updated = conn.execute(
                "UPDATE handoff_receipt_reservations SET state='COLLECTED' "
                "WHERE run_id=? AND attempt_id=? AND reservation_token=?",
                (trust["run_id"], trust["attempt_id"], token),
            )
            if updated.rowcount != 1:
                raise HandoffError("Reservation disappeared during collection")
            conn.commit()
        return path, receipt
