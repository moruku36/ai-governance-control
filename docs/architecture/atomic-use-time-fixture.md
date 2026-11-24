# Atomic use-time rehearsal: test fixtures only

This [SQLite rehearsal](../../tests/test_g2_atomic_use_fixture.py) builds on the
[signed review preview](signed-review-fixture-preview.md). It adds no installed
gate, provider, or CLI execution path. The project remains **MANUAL_ONLY**. All
inputs, identities, times, and databases are synthetic. A receipt is just a row
in a temporary test database.

The fixture controller selects a subject (repository ID, task, action, ref) and
retains the enrolled tag and generation. Independent observation rows contain
the current context, review and registry digests, reviewer and policy state,
and clock. The bundle can only be compared against that state: neither its
subject nor its digest fields select the source or replace an enrollment.

The rehearsal opens a write transaction before checking the bundle or reading
current state. It refuses a missing or disabled source, different target,
changed generation or binding, expired or revoked fixture, replay, or hard
denial. Controller observation changes advance the generation even when the
digests later return to their original values. The guarded consumption and
inert receipt commit together. The receipt records the enrolled token, subject,
observed generation, and the three checked digests. A refusal commits neither
update; a store error is unconfirmed, with no automatic retry.

The tests check that preview is inert, that state changes and outages after
preview cannot be ignored, that a new valid fixture tag cannot rebind an
enrollment, and that exactly one concurrent connection records a receipt. A
lock-ordering test holds a controller update open while use starts. Use refuses
a newly committed generation, an unchanged generation with a clock at the
exact expiry second, or a missing current source. An injected SQLite read
denial on the observation table refuses use despite an earlier good read,
without retrying. A failed receipt insert rolls back consumption. Uncertain
store results require a fresh read-back before any conclusion about the
fixture receipt.

SQLite protects only the rows participating in this transaction. This does not
prove a live source, establish authentication or true freshness, prevent a
privileged database restore, or reconcile external effects. The fixture
controller uses updates only for generations; deletion in a test represents an
unavailable source, not a supported way to reset the counter. A real control
plane still needs a protected source with a non-reused generation, independently
measured artifacts and reviewer/clock/policy state, a verified end-to-end
transaction or equivalent fencing, and a separately reviewed reservation and
reconciliation protocol. The signed preview, legacy approval manager, adapters,
and merge rules are unchanged.


## Smallest staging prerequisite (not implemented)

Select one controller-owned observation and receipt boundary. The controller,
not the incoming bundle, resolves the subject and obtains its current evidence,
reviewer and policy state, and an independent UTC time sample. Read these
after acquiring the admission fence, or revalidate an equivalent versioned
reservation before recording a receipt. A missing or unreadable source or clock
must halt; a previous preview or cached valid sample cannot replace it. Ordinary
forward clock movement need not change the artifact generation, but an
unreliable clock must not allow use of a stale sample.

Define which instant the expiry cutoff governs before staging. This fixture
compares a stored synthetic timestamp after taking a write lock; it does not
measure trusted wall time, the time spent waiting for the lock, or when a
transaction commits. If expiry must hold at commit, staging needs a guard
that covers that instant, or a bounded timing guarantee and fail-closed behavior
when that bound cannot be established. Keep staging inert until this behavior
and authority provenance can be verified independently.
