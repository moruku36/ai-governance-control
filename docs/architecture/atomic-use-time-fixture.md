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
separate lock test holds a controller update open while use starts and checks
that use refuses the newly committed generation. A failed receipt insert rolls
back consumption. Uncertain store results require a fresh read-back before any
conclusion about the fixture receipt.

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
