"""Test-only G2 use-time transaction; no installed gate, runner, or real approval."""

import json
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from threading import Barrier, Event

import pytest
from test_signed_review_preview import _approval_tag, _bundle, _context_digest, _json

from orchestrator.core.signed_review_preview import preview_signed_review

_Subject = tuple[str, str, str, str]
_SUBJECT_FIELDS = ("repository_id", "task_id", "action", "target_ref")
# Independently retained controller vectors for the public, exact #61 fixture.
_SUBJECT: _Subject = (
    "agc-signed-review-fixture",
    "FIXTURE-101",
    "task_execution",
    "refs/heads/task/fixture-example",
)
_OTHER_SUBJECT: _Subject = (*_SUBJECT[:-1], "refs/heads/task/fixture-other")
_BINDING_FIELDS = ("context_digest", "review_digest", "registry_digest")
_BINDING = (
    "d69285aa015c2f42a7eb597596c41ba4aee4bf1632d5146ac7923f97e75f8bfc",
    "793158057ccc81e00d791581a4fde625449b7698c0ed4482070b4f5c607a5e2c",
    "e1963d17098a2f935ab1b22479e1d88db6da6ffcf3d661a70d16dedd39f2efcb",
)
_SCHEMA = """
CREATE TABLE fixture_observation (
    subject TEXT PRIMARY KEY NOT NULL,
    generation INTEGER NOT NULL CHECK (typeof(generation) = 'integer' AND generation > 0),
    context_digest TEXT NOT NULL,
    review_digest TEXT NOT NULL,
    registry_digest TEXT NOT NULL,
    now_at_use INTEGER NOT NULL CHECK (typeof(now_at_use) = 'integer' AND now_at_use >= 0),
    available INTEGER NOT NULL DEFAULT 1 CHECK (available IN (0, 1)),
    reviewer_active INTEGER NOT NULL DEFAULT 1 CHECK (reviewer_active IN (0, 1)),
    policy_denied INTEGER NOT NULL DEFAULT 0 CHECK (policy_denied IN (0, 1))
);
CREATE TRIGGER fixture_observation_advance
BEFORE UPDATE OF generation, context_digest, review_digest, registry_digest,
                 available, reviewer_active, policy_denied ON fixture_observation
WHEN NEW.generation <= OLD.generation
BEGIN SELECT RAISE(ABORT, 'fixture observation generation must advance'); END;
CREATE TABLE fixture_approval (
    token_id TEXT PRIMARY KEY NOT NULL,
    subject TEXT NOT NULL,
    enrolled_generation INTEGER NOT NULL,
    enrolled_tag TEXT NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0 CHECK (revoked IN (0, 1)),
    consumed INTEGER NOT NULL DEFAULT 0 CHECK (consumed IN (0, 1))
);
CREATE TABLE fixture_receipt (
    token_id TEXT PRIMARY KEY NOT NULL REFERENCES fixture_approval(token_id),
    subject TEXT NOT NULL,
    generation INTEGER NOT NULL,
    context_digest TEXT NOT NULL,
    review_digest TEXT NOT NULL,
    registry_digest TEXT NOT NULL
);
"""


def _record_fixture_use(database: Path, selected_subject: _Subject, raw: bytes) -> str:
    """Compare and record one local receipt; selected_subject is controller-owned.

    No eligibility or execution result leaves this test helper. The write lock
    covers the observed state and receipt, not real artifacts or external effects.
    """
    subject = _json(selected_subject).decode("ascii")
    try:
        with closing(
            sqlite3.connect(f"{database.as_uri()}?mode=rw", uri=True, isolation_level=None)
        ) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("BEGIN IMMEDIATE")
            verdict = preview_signed_review(raw)
            if verdict.reason != "FIXTURE_SIGNED_REVIEW_MATCH":
                return verdict.reason

            # The strict preview accepted these exact immutable bytes. The
            # signed input is compared against, never used to select, the source.
            bundle = json.loads(raw)
            if tuple(bundle["context"][name] for name in _SUBJECT_FIELDS) != selected_subject:
                return "FIXTURE_SUBJECT_MISMATCH"
            enrollment = conn.execute(
                "SELECT * FROM fixture_approval WHERE token_id = ?",
                (bundle["approval"]["body"]["token_id"],),
            ).fetchone()
            if enrollment is None:
                return "FIXTURE_NOT_ENROLLED"
            if enrollment["subject"] != subject:
                return "FIXTURE_SUBJECT_MISMATCH"

            current = conn.execute(
                "SELECT * FROM fixture_observation WHERE subject = ?", (subject,)
            ).fetchone()
            if current is None or not current["available"]:
                return "FIXTURE_SOURCE_UNAVAILABLE"
            if current["policy_denied"]:
                return "FIXTURE_HARD_DENY"
            if enrollment["revoked"] or not current["reviewer_active"]:
                return "FIXTURE_REVOKED"
            if enrollment["consumed"]:
                return "FIXTURE_ALREADY_CONSUMED"
            envelope = bundle["approval"]
            if enrollment["enrolled_tag"] != envelope["tag"]:
                return "FIXTURE_ENROLLED_TAG_CHANGED"
            signed = envelope["body"]
            if any(current[field] != signed[field] for field in _BINDING_FIELDS):
                return "FIXTURE_CURRENT_BINDING_CHANGED"
            if current["generation"] != enrollment["enrolled_generation"]:
                return "FIXTURE_GENERATION_CHANGED"
            if not signed["issued_at"] <= current["now_at_use"] < signed["expires_at"]:
                return "FIXTURE_USE_TIME_EXPIRED"

            token_id = signed["token_id"]
            consumed = conn.execute(
                "UPDATE fixture_approval SET consumed = 1 WHERE token_id = ? AND consumed = 0",
                (token_id,),
            )
            if consumed.rowcount != 1:
                return "FIXTURE_ALREADY_CONSUMED"
            conn.execute(
                """INSERT INTO fixture_receipt(
                       token_id, subject, generation, context_digest, review_digest, registry_digest
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (token_id, subject, current["generation"], *(current[f] for f in _BINDING_FIELDS)),
            )
            conn.execute("COMMIT")
            return "FIXTURE_USE_RECORDED"
    except sqlite3.Error:
        # No claim about consumption and no retry. Closing rolls back an open
        # transaction; a fresh observer must check the receipt when uncertain.
        return "FIXTURE_STORE_UNCONFIRMED"


def _subject_key(subject: _Subject = _SUBJECT) -> str:
    return _json(subject).decode("ascii")


def _seed(database: Path, enrollment: dict) -> str:
    """Create controller state; no values are taken from a later use request."""
    envelope = enrollment["approval"]
    token_id = envelope["body"]["token_id"]
    with closing(sqlite3.connect(database, isolation_level=None)) as conn:
        conn.executescript(_SCHEMA)
        conn.execute(
            """INSERT INTO fixture_observation(
                   subject, generation, context_digest, review_digest, registry_digest, now_at_use
               ) VALUES (?, 1, ?, ?, ?, 1800000000)""",
            (_subject_key(), *_BINDING),
        )
        conn.execute(
            """INSERT INTO fixture_approval(
                   token_id, subject, enrolled_generation, enrolled_tag
               ) VALUES (?, ?, 1, ?)""",
            (token_id, _subject_key(), envelope["tag"]),
        )
    return token_id


def _controller_sql(database: Path, statement: str, parameters=()) -> None:
    with closing(sqlite3.connect(database, isolation_level=None)) as conn:
        conn.execute(statement, parameters)


def _advance(database, field, value):
    # These column names come from this file's static test cases, never a bundle.
    _controller_sql(
        database,
        f"UPDATE fixture_observation SET {field} = ?, generation = generation + 1 WHERE subject = ?",
        (value, _subject_key()),
    )


def _observed(database: Path) -> tuple[list, list]:
    with closing(sqlite3.connect(database)) as conn:
        return (
            conn.execute("SELECT token_id, consumed FROM fixture_approval").fetchall(),
            conn.execute("SELECT * FROM fixture_receipt").fetchall(),
        )


def _recorded(token_id):
    return ([(token_id, 1)], [(token_id, _subject_key(), 1, *_BINDING)])


@pytest.fixture
def enrolled(tmp_path):
    database = tmp_path / "synthetic-g2.sqlite"
    payload = _bundle()
    token_id = _seed(database, payload)
    return database, payload, token_id


def test_preview_is_inert_and_replay_after_reopen_does_not_repeat(enrolled):
    database, payload, token_id = enrolled
    raw = _json(payload)
    assert _observed(database) == ([(token_id, 0)], [])
    assert preview_signed_review(raw).summary() == {
        "reason": "FIXTURE_SIGNED_REVIEW_MATCH",
        "mode": "MANUAL_ONLY",
        "approval_verified": False,
        "execution_authorized": False,
        "token_consumed": False,
    }
    assert _observed(database) == ([(token_id, 0)], [])
    assert _record_fixture_use(database, _SUBJECT, raw) == "FIXTURE_USE_RECORDED"
    assert _record_fixture_use(database, _SUBJECT, json.dumps(payload, indent=2).encode()) == (
        "FIXTURE_ALREADY_CONSUMED"
    )
    assert _observed(database) == _recorded(token_id)


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("policy_denied", 1, "FIXTURE_HARD_DENY"),
        ("reviewer_active", 0, "FIXTURE_REVOKED"),
        ("available", 0, "FIXTURE_SOURCE_UNAVAILABLE"),
        ("context_digest", "0" * 64, "FIXTURE_CURRENT_BINDING_CHANGED"),
        ("review_digest", "0" * 64, "FIXTURE_CURRENT_BINDING_CHANGED"),
        ("registry_digest", "0" * 64, "FIXTURE_CURRENT_BINDING_CHANGED"),
    ],
)
def test_current_controller_state_wins_over_prior_matching_preview(enrolled, field, value, reason):
    database, payload, token_id = enrolled
    raw = _json(payload)
    assert preview_signed_review(raw).reason == "FIXTURE_SIGNED_REVIEW_MATCH"
    _advance(database, field, value)
    assert _record_fixture_use(database, _SUBJECT, raw) == reason
    assert _observed(database) == ([(token_id, 0)], [])


@pytest.mark.parametrize("now", [1_799_999_989, 1_800_000_010], ids=["before-issue", "at-expiry"])
def test_controller_clock_must_be_inside_closed_open_validity_window(enrolled, now):
    database, payload, token_id = enrolled
    _controller_sql(database, "UPDATE fixture_observation SET now_at_use = ?", (now,))
    assert _record_fixture_use(database, _SUBJECT, _json(payload)) == "FIXTURE_USE_TIME_EXPIRED"
    assert _observed(database) == ([(token_id, 0)], [])


def test_token_revocation_does_not_consume(enrolled):
    database, payload, token_id = enrolled
    _controller_sql(database, "UPDATE fixture_approval SET revoked = 1")
    assert _record_fixture_use(database, _SUBJECT, _json(payload)) == "FIXTURE_REVOKED"
    assert _observed(database) == ([(token_id, 0)], [])


def test_restoring_identical_digests_does_not_restore_the_enrolled_generation(enrolled):
    database, payload, token_id = enrolled
    raw = _json(payload)
    assert preview_signed_review(raw).reason == "FIXTURE_SIGNED_REVIEW_MATCH"
    _advance(database, "context_digest", "0" * 64)
    _advance(database, "context_digest", _BINDING[0])
    with closing(sqlite3.connect(database)) as controller:
        restored = controller.execute(
            "SELECT generation, context_digest, review_digest, registry_digest "
            "FROM fixture_observation WHERE subject = ?",
            (_subject_key(),),
        ).fetchone()
    assert restored == (3, *_BINDING)
    assert _record_fixture_use(database, _SUBJECT, raw) == "FIXTURE_GENERATION_CHANGED"
    assert _observed(database) == ([(token_id, 0)], [])


def test_outage_and_recovery_do_not_revive_old_generation(enrolled):
    database, payload, token_id = enrolled
    raw = _json(payload)
    _advance(database, "available", 0)
    assert _record_fixture_use(database, _SUBJECT, raw) == "FIXTURE_SOURCE_UNAVAILABLE"
    _advance(database, "available", 1)
    assert _record_fixture_use(database, _SUBJECT, raw) == "FIXTURE_GENERATION_CHANGED"
    assert _observed(database) == ([(token_id, 0)], [])


def test_controller_cannot_reuse_an_earlier_generation_through_update(enrolled):
    database, payload, token_id = enrolled
    _advance(database, "reviewer_active", 0)
    with pytest.raises(sqlite3.IntegrityError, match="generation must advance"):
        _controller_sql(
            database,
            "UPDATE fixture_observation SET generation = 1, reviewer_active = 1",
        )
    assert _record_fixture_use(database, _SUBJECT, _json(payload)) == "FIXTURE_REVOKED"
    assert _observed(database) == ([(token_id, 0)], [])


def test_bundle_cannot_choose_source_or_rebind_the_enrolled_subject(enrolled):
    database, payload, token_id = enrolled
    # Create an alternate source that really does match a valid signed bundle,
    # to distinguish subject selection/enrollment from a generic digest failure.
    payload["context"]["target_ref"] = _OTHER_SUBJECT[-1]
    other_digest = _context_digest(payload["context"])
    payload["approval"]["body"]["context_digest"] = other_digest
    _approval_tag(payload)
    raw = _json(payload)
    assert preview_signed_review(raw).reason == "FIXTURE_SIGNED_REVIEW_MATCH"
    _controller_sql(
        database,
        """INSERT INTO fixture_observation
           SELECT ?, generation, ?, review_digest, registry_digest, now_at_use,
                  available, reviewer_active, policy_denied FROM fixture_observation
           WHERE subject = ?""",
        (_subject_key(_OTHER_SUBJECT), other_digest, _subject_key()),
    )
    assert _record_fixture_use(database, _SUBJECT, raw) == "FIXTURE_SUBJECT_MISMATCH"
    assert _record_fixture_use(database, _OTHER_SUBJECT, raw) == "FIXTURE_SUBJECT_MISMATCH"
    assert _observed(database) == ([(token_id, 0)], [])


def test_registered_subject_without_observation_fails_closed(enrolled):
    database, payload, token_id = enrolled
    # Simulate a missing source in the test DB, not a supported controller update.
    _controller_sql(
        database, "DELETE FROM fixture_observation WHERE subject = ?", (_subject_key(),)
    )
    assert _record_fixture_use(database, _SUBJECT, _json(payload)) == "FIXTURE_SOURCE_UNAVAILABLE"
    assert _observed(database) == ([(token_id, 0)], [])


def test_enrolled_token_cannot_be_rebound_by_a_new_valid_fixture_tag(enrolled):
    database, payload, token_id = enrolled
    payload["context"]["candidate_sha"] = "7" * 40
    new_digest = _context_digest(payload["context"])
    payload["approval"]["body"]["context_digest"] = new_digest
    _approval_tag(payload)
    raw = _json(payload)
    assert preview_signed_review(raw).reason == "FIXTURE_SIGNED_REVIEW_MATCH"
    _advance(database, "context_digest", new_digest)
    assert _record_fixture_use(database, _SUBJECT, raw) == "FIXTURE_ENROLLED_TAG_CHANGED"
    assert _observed(database) == ([(token_id, 0)], [])


def test_invalid_tag_and_unenrolled_token_do_not_consume(enrolled):
    database, payload, token_id = enrolled
    payload["approval"]["body"]["token_id"] = "fixture:approval:unknown"
    assert _record_fixture_use(database, _SUBJECT, _json(payload)) == "APPROVAL_TAG_MISMATCH"
    _approval_tag(payload)
    assert _record_fixture_use(database, _SUBJECT, _json(payload)) == "FIXTURE_NOT_ENROLLED"
    assert _observed(database) == ([(token_id, 0)], [])


def test_racing_connections_record_exactly_one_receipt(enrolled):
    database, payload, token_id = enrolled
    raw = _json(payload)
    callers = 6
    barrier = Barrier(callers)

    def race():
        barrier.wait(timeout=5)
        return _record_fixture_use(database, _SUBJECT, raw)

    with ThreadPoolExecutor(max_workers=callers) as workers:
        outcomes = [workers.submit(race) for _ in range(callers)]
        results = [outcome.result(timeout=10) for outcome in outcomes]
    assert sorted(results) == ["FIXTURE_ALREADY_CONSUMED"] * (callers - 1) + [
        "FIXTURE_USE_RECORDED"
    ]
    assert _observed(database) == _recorded(token_id)


def test_receipt_failure_does_not_leave_a_burned_token_or_untracked_success(enrolled):
    database, payload, token_id = enrolled
    _controller_sql(
        database,
        """CREATE TRIGGER fixture_receipt_abort BEFORE INSERT ON fixture_receipt
             BEGIN SELECT RAISE(ABORT, 'synthetic receipt failure'); END""",
    )
    assert _record_fixture_use(database, _SUBJECT, _json(payload)) == "FIXTURE_STORE_UNCONFIRMED"
    assert _observed(database) == ([(token_id, 0)], [])


def test_a_missing_store_fails_closed_without_creating_state(tmp_path):
    database = tmp_path / "missing.sqlite"
    assert _record_fixture_use(database, _SUBJECT, _json(_bundle())) == "FIXTURE_STORE_UNCONFIRMED"
    assert not database.exists()


def test_controller_cannot_interleave_a_writer_once_use_time_check_starts(enrolled, monkeypatch):
    database, payload, token_id = enrolled
    real_preview = preview_signed_review

    def check_write_lock(raw):
        with closing(sqlite3.connect(database, timeout=0, isolation_level=None)) as controller:
            with pytest.raises(sqlite3.OperationalError) as exc:
                controller.execute("BEGIN IMMEDIATE")
            assert exc.value.sqlite_errorcode == sqlite3.SQLITE_BUSY
        return real_preview(raw)

    monkeypatch.setattr(sys.modules[__name__], "preview_signed_review", check_write_lock)
    assert _record_fixture_use(database, _SUBJECT, _json(payload)) == "FIXTURE_USE_RECORDED"
    assert _observed(database) == _recorded(token_id)


@pytest.mark.parametrize(
    "change,reason",
    [
        (
            "UPDATE fixture_observation SET generation = generation + 1 WHERE subject = ?",
            "FIXTURE_GENERATION_CHANGED",
        ),
        (
            "UPDATE fixture_observation SET now_at_use = 1800000010 WHERE subject = ?",
            "FIXTURE_USE_TIME_EXPIRED",
        ),
        (
            "DELETE FROM fixture_observation WHERE subject = ?",
            "FIXTURE_SOURCE_UNAVAILABLE",
        ),
    ],
    ids=["new-generation", "at-expiry", "missing-current-source"],
)
def test_use_observes_the_controller_change_before_recording(enrolled, monkeypatch, change, reason):
    database, payload, token_id = enrolled
    raw = _json(payload)
    assert preview_signed_review(raw).reason == "FIXTURE_SIGNED_REVIEW_MATCH"
    real_connect = sqlite3.connect
    begin_attempted = Event()

    def traced_connect(*args, **kwargs):
        connection = real_connect(*args, **kwargs)

        def signal_begin(statement):
            if statement == "BEGIN IMMEDIATE":
                begin_attempted.set()

        connection.set_trace_callback(signal_begin)
        return connection

    with (
        closing(real_connect(database, isolation_level=None)) as controller,
        ThreadPoolExecutor(max_workers=1) as worker,
    ):
        # This earlier good observation cannot suffice once use begins.
        previous = controller.execute(
            "SELECT available, generation, now_at_use FROM fixture_observation WHERE subject = ?",
            (_subject_key(),),
        ).fetchone()
        assert previous == (1, 1, 1_800_000_000)
        assert payload["approval"]["body"]["expires_at"] == 1_800_000_010

        controller.execute("BEGIN IMMEDIATE")
        try:
            # No new candidate bytes are supplied. Expiry also does not require a new generation.
            # Deletion simulates unavailable authority, not a supported controller write.
            controller.execute(change, (_subject_key(),))
            monkeypatch.setattr(sqlite3, "connect", traced_connect)
            outcome = worker.submit(_record_fixture_use, database, _SUBJECT, raw)
            assert begin_attempted.wait(timeout=5)
            assert not outcome.done()
            controller.execute("COMMIT")
        finally:
            if controller.in_transaction:
                controller.execute("ROLLBACK")
        assert outcome.result(timeout=10) == reason
    assert _observed(database) == ([(token_id, 0)], [])


def test_observation_read_error_fails_closed_without_retry_or_cached_use(enrolled, monkeypatch):
    database, payload, token_id = enrolled
    raw = _json(payload)
    assert preview_signed_review(raw).reason == "FIXTURE_SIGNED_REVIEW_MATCH"
    real_connect = sqlite3.connect
    with closing(real_connect(database)) as controller:
        previous = controller.execute(
            """SELECT context_digest, review_digest, registry_digest
                 FROM fixture_observation WHERE subject = ? AND available = 1""",
            (_subject_key(),),
        ).fetchone()
    assert previous == _BINDING

    opened = []
    read_refused = []

    def deny_current_read(action, table, column, _schema, _cause):
        if action == sqlite3.SQLITE_READ and table == "fixture_observation":
            read_refused.append(column)
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    def connection_with_unreadable_observation(*args, **kwargs):
        opened.append(1)
        connection = real_connect(*args, **kwargs)
        connection.set_authorizer(deny_current_read)
        return connection

    with monkeypatch.context() as context:
        context.setattr(sqlite3, "connect", connection_with_unreadable_observation)
        assert _record_fixture_use(database, _SUBJECT, raw) == "FIXTURE_STORE_UNCONFIRMED"

    assert len(read_refused) == 1
    assert len(opened) == 1
    assert _observed(database) == ([(token_id, 0)], [])
