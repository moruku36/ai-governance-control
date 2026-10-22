"""Offline committed candidate seals and trusted synthetic test observations."""

import subprocess
from dataclasses import FrozenInstanceError, replace

import pytest

from orchestrator.core.candidate import measure_git_commit
from orchestrator.core.candidate_binding import (
    BindingContext,
    CandidateBindingError,
    bind_test_evidence,
    seal_committed_candidate,
)
from orchestrator.core.candidate_binding import (
    TestObservation as Observation,
)


def git(repo, *args, data=None):
    return subprocess.run(["git", "-C", str(repo), *args], input=data,
                          capture_output=True, check=True).stdout.decode().strip()


def commit(repo, files):
    rows = []
    for path, mode, content in files:
        oid = git(repo, "hash-object", "-w", "--stdin", data=content)
        rows.append(f"{mode} blob {oid}\t{path}\n")
    tree = git(repo, "mktree", data="".join(rows).encode())
    payload = (f"tree {tree}\nauthor Fixture <test@example.invalid> 1 +0000\n"
               "committer Fixture <test@example.invalid> 1 +0000\n\nsynthetic\n")
    return git(repo, "hash-object", "-w", "-t", "commit", "--stdin", data=payload.encode())


@pytest.fixture
def case(tmp_path):
    git(tmp_path, "init", "--quiet")
    base = commit(tmp_path, [("app.py", "100644", b"old")])
    candidate = commit(tmp_path, [("app.py", "100644", b"new")])
    suite = commit(tmp_path, [("test_app.py", "100644", b"independent synthetic oracle")])
    root = tmp_path / ".git"
    measured_suite = measure_git_commit(root, suite, "synthetic")
    context = BindingContext("TEST-001", "1" * 64, "2" * 64, measured_suite.digest, "3" * 64)
    seal = seal_committed_candidate(root, "synthetic", base, suite, context,
                                    lambda: candidate, allowed_paths=("app.py",))
    observation = Observation("execution-1", "independent-fixture", seal.digest, context.digest,
                              seal.candidate.digest, seal.approved_suite.digest,
                              context.runner_profile_digest, 0,
                              '<testsuite tests="1"><testcase name="independent"/></testsuite>')
    return root, seal, observation


def accept(case, **kwargs):
    root, seal, observation = case
    arguments = {"expected_seal_digest": seal.digest, "current_context": seal.context,
                 "current_candidate": lambda: seal.candidate.commit_sha, "observation": observation}
    arguments.update(kwargs)
    return bind_test_evidence(root, seal, **arguments)


def test_bound_receipt_measures_candidate_and_keeps_distinct_status(case):
    _, seal, observation = case
    evidence = accept(case)
    assert evidence.status == "BOUND_TEST_EVIDENCE"
    assert evidence.tests == 1 and evidence.skipped == 0
    assert evidence.seal_digest == seal.digest
    assert evidence.execution_id == observation.execution_id
    assert len(evidence.report_digest) == 64
    with pytest.raises(FrozenInstanceError):
        evidence.status = "COMPLETED"
    with pytest.raises(FrozenInstanceError):
        seal.context.policy_digest = "4" * 64


@pytest.mark.parametrize("field", ["task_id", "specification_digest", "policy_digest",
                                   "approved_suite_digest", "runner_profile_digest"])
def test_changed_current_context_rejected(case, field):
    _, seal, _ = case
    changed = replace(seal.context, **{field: "TEST-002" if field == "task_id" else "f" * 64})
    with pytest.raises(CandidateBindingError, match="context changed"):
        accept(case, current_context=changed)


@pytest.mark.parametrize("field", ["seal_digest", "context_digest", "candidate_snapshot_digest",
                                   "suite_snapshot_digest", "runner_profile_digest"])
def test_execution_binding_changes_rejected(case, field):
    _, _, observed = case
    with pytest.raises(CandidateBindingError, match="not bound"):
        accept(case, observation=replace(observed, **{field: "f" * 64}))


def test_wrong_or_tampered_seal_rejected(case):
    with pytest.raises(CandidateBindingError, match="Seal"):
        accept(case, expected_seal_digest="0" * 64)
    root, seal, obs = case
    changed = replace(seal, allowed_paths=("app.py", "extra"))
    with pytest.raises(CandidateBindingError, match="Seal"):
        bind_test_evidence(root, changed, expected_seal_digest=seal.digest,
                           current_context=seal.context,
                           current_candidate=lambda: seal.candidate.commit_sha, observation=obs)


@pytest.mark.parametrize("xml", ["", "not XML", '<testsuite tests="0"/>',
                                 '<testsuite tests="1"><testcase><skipped/></testcase></testsuite>',
                                 '<testsuite tests="1"><testcase><failure/></testcase></testsuite>',
                                 '<testsuite tests="1"><testcase><error/></testcase></testsuite>'])
def test_invalid_failed_or_all_skipped_report_rejected(case, xml):
    with pytest.raises(CandidateBindingError, match="report"):
        accept(case, observation=replace(case[2], junit_xml=xml))


def test_nonzero_exit_cannot_be_hidden_by_passing_report(case):
    with pytest.raises(CandidateBindingError, match="executor failed"):
        accept(case, observation=replace(case[2], exit_code=1))


def test_moved_head_before_and_during_validation_rejected(case):
    _, seal, _ = case
    with pytest.raises(CandidateBindingError, match="Stale"):
        accept(case, current_candidate=lambda: seal.base.commit_sha)
    heads = iter([seal.candidate.commit_sha, seal.base.commit_sha])
    with pytest.raises(CandidateBindingError, match="moved during"):
        accept(case, current_candidate=lambda: next(heads))


@pytest.mark.parametrize("resolver", [None, lambda: "unknown", lambda: None])
def test_unresolved_candidate_never_passes(case, resolver):
    with pytest.raises(CandidateBindingError):
        accept(case, current_candidate=resolver)


def test_resolver_failure_never_passes(case):
    def unavailable():
        raise RuntimeError("synthetic unavailable")
    with pytest.raises(CandidateBindingError, match="could not be established"):
        accept(case, current_candidate=unavailable)


@pytest.mark.parametrize("allowed", [(), [], ("*",), (None,), ("app.py", "app.py")])
def test_missing_or_ambiguous_scope_rejected(case, allowed):
    root, seal, _ = case
    with pytest.raises(ValueError):
        seal_committed_candidate(root, "synthetic", seal.base.commit_sha,
                                 seal.approved_suite.commit_sha, seal.context,
                                 lambda: seal.candidate.commit_sha, allowed_paths=allowed)


def test_denied_or_out_of_scope_changes_rejected(case):
    root, seal, _ = case
    for allowed, prohibited in [(("elsewhere",), ()), (("app.py",), ("app.py",)),
                                 (("app.py",), ("APP.PY",))]:
        with pytest.raises(CandidateBindingError):
            seal_committed_candidate(root, "synthetic", seal.base.commit_sha,
                                     seal.approved_suite.commit_sha, seal.context,
                                     lambda: seal.candidate.commit_sha,
                                     allowed_paths=allowed, prohibited_paths=prohibited)


def test_deletion_and_mode_changes_cannot_evade_scope(case):
    root, seal, _ = case
    deleted = commit(root.parent, [])
    mode = commit(root.parent, [("app.py", "100755", b"old")])
    for sha in (deleted, mode):
        with pytest.raises(CandidateBindingError, match="outside"):
            seal_committed_candidate(root, "synthetic", seal.base.commit_sha,
                                     seal.approved_suite.commit_sha, seal.context,
                                     lambda sha=sha: sha, allowed_paths=("elsewhere",))


def test_protected_control_change_denied_even_if_allowlisted(case):
    root, seal, _ = case
    sha = commit(root.parent, [("app.py", "100644", b"old"), (".env", "100644", b"fake")])
    with pytest.raises(CandidateBindingError, match="Protected"):
        seal_committed_candidate(root, "synthetic", seal.base.commit_sha,
                                 seal.approved_suite.commit_sha, seal.context,
                                 lambda: sha, allowed_paths=("app.py", ".env"))


def test_suite_must_match_separately_approved_digest(case):
    root, seal, _ = case
    with pytest.raises(CandidateBindingError, match="approved-suite"):
        seal_committed_candidate(root, "synthetic", seal.base.commit_sha,
                                 seal.candidate.commit_sha, seal.context,
                                 lambda: seal.candidate.commit_sha, allowed_paths=("app.py",))


def test_candidate_moves_during_seal_rejected(case):
    root, seal, _ = case
    heads = iter([seal.candidate.commit_sha, seal.base.commit_sha])
    with pytest.raises(CandidateBindingError, match="while sealing"):
        seal_committed_candidate(root, "synthetic", seal.base.commit_sha,
                                 seal.approved_suite.commit_sha, seal.context,
                                 lambda: next(heads), allowed_paths=("app.py",))


def test_remeasurement_failure_does_not_accept_old_hash(case, monkeypatch):
    import orchestrator.core.candidate_binding as module

    monkeypatch.setattr(module, "measure_git_commit", lambda *a, **k: case[1].base)
    with pytest.raises(CandidateBindingError, match="measured candidate"):
        accept(case)


def test_case_variant_prohibited_deletion_rejected(case):
    root, seal, _ = case
    deleted = commit(root.parent, [])
    with pytest.raises(CandidateBindingError, match="Prohibited"):
        seal_committed_candidate(root, "synthetic", seal.base.commit_sha,
                                 seal.approved_suite.commit_sha, seal.context,
                                 lambda: deleted, allowed_paths=("app.py",),
                                 prohibited_paths=("APP.PY",))


def test_malformed_scope_and_cross_repository_suite_rejected(case):
    _, seal, _ = case
    with pytest.raises(CandidateBindingError, match="scope"):
        replace(seal, allowed_paths=(["mutable"],))
    with pytest.raises(CandidateBindingError, match="repository provenance"):
        replace(seal, approved_suite=replace(seal.approved_suite, repository_id="other"))


@pytest.mark.parametrize("task_id", ["task", "test-001", "A-001", "TEST-01", "TEST-1234567",
                                     "TOOLONGID-001", "TEST-001\n", "", None, 1])
def test_task_id_matches_existing_schema(task_id):
    with pytest.raises(CandidateBindingError, match="task schema"):
        BindingContext(task_id, "1" * 64, "2" * 64, "3" * 64, "4" * 64)


@pytest.mark.parametrize("field", ["specification_digest", "policy_digest",
                                   "approved_suite_digest", "runner_profile_digest"])
@pytest.mark.parametrize("invalid", [None, "", "a" * 63, "A" * 64, "g" * 64, 1])
def test_context_rejects_malformed_digest(field, invalid):
    valid = BindingContext("TEST-001", "1" * 64, "2" * 64, "3" * 64, "4" * 64)
    with pytest.raises(CandidateBindingError, match="SHA-256"):
        replace(valid, **{field: invalid})
