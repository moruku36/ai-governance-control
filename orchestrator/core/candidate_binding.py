"""Offline controller-side committed-candidate sealing and test-evidence binding.

Not a worker-facing authority boundary: controller storage, resolver and independent
executor observations must already be trusted. No approval or state is changed.
"""

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from orchestrator.core.artifacts import PROTECTED_CONTROL_PATHS
from orchestrator.core.candidate import (
    CandidateError,
    TreeEntry,
    TreeSnapshot,
    compare_snapshots,
    measure_git_commit,
)
from orchestrator.core.verifier import IndependentVerifier

BINDING_VERSION = "committed-candidate-binding/1"
_HASH = re.compile(r"[0-9a-f]{64}")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


class CandidateBindingError(CandidateError):
    """Missing, stale or inconsistent controller/execution evidence."""


def _hash(value):
    if not isinstance(value, str) or not _HASH.fullmatch(value):
        raise CandidateBindingError("A full SHA-256 binding is required")


def _id(value):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise CandidateBindingError("Explicit opaque provenance ID required")


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode("ascii")).hexdigest()


@dataclass(frozen=True)
class BindingContext:
    task_id: str
    specification_digest: str
    policy_digest: str
    approved_suite_digest: str
    runner_profile_digest: str

    def __post_init__(self):
        if (not isinstance(self.task_id, str)
                or not re.fullmatch(r"[A-Z][A-Z0-9]{1,7}-[0-9]{3,6}", self.task_id)):
            raise CandidateBindingError("Task ID must match the existing task schema")
        for value in (self.specification_digest, self.policy_digest,
                      self.approved_suite_digest, self.runner_profile_digest):
            _hash(value)

    @property
    def digest(self):
        return _digest(asdict(self))


@dataclass(frozen=True)
class CandidateSeal:
    context: BindingContext
    base: TreeSnapshot
    candidate: TreeSnapshot
    approved_suite: TreeSnapshot
    allowed_paths: tuple[str, ...]
    prohibited_paths: tuple[str, ...]
    diff_digest: str
    version: str = BINDING_VERSION

    def __post_init__(self):
        if self.version != BINDING_VERSION or type(self.context) is not BindingContext:
            raise CandidateBindingError("Unsupported candidate seal")
        if any(type(s) is not TreeSnapshot for s in (self.base, self.candidate, self.approved_suite)):
            raise CandidateBindingError("Measured full snapshot context is required")
        if self.approved_suite.repository_id != self.candidate.repository_id:
            raise CandidateBindingError("Approved suite repository provenance mismatch")
        _scope(self.allowed_paths, required=True)
        _scope(self.prohibited_paths, required=False)
        diff = compare_snapshots(self.base, self.candidate,
                                 expected_base_digest=self.base.digest,
                                 expected_candidate_digest=self.candidate.digest)
        if diff.digest != self.diff_digest or self.approved_suite.digest != self.context.approved_suite_digest:
            raise CandidateBindingError("Diff or approved-suite binding mismatch")
        _changed_paths(diff.changed_paths, self.allowed_paths, self.prohibited_paths)

    @property
    def digest(self):
        return _digest(asdict(self))


def _scope(paths, required):
    if (type(paths) is not tuple or (required and not paths)
            or any(not isinstance(p, str) for p in paths)):
        raise CandidateBindingError("Explicit immutable path scope required")
    if len(set(paths)) != len(paths):
        raise CandidateBindingError("Duplicate path scope")
    for path in paths:
        # This tranche accepts literal path prefixes only, not glob interpretations.
        TreeEntry(path, "100644", "0" * 64)
        if any(c in path for c in "*?[]"):
            raise CandidateBindingError("Literal path prefixes required")


def _changed_paths(paths, allowed, prohibited):
    protected = {p.casefold() for p in PROTECTED_CONTROL_PATHS}
    for path in paths:
        if any(part.casefold() in protected or part.casefold().startswith(".git")
               for part in path.split("/")):
            raise CandidateBindingError("Protected control path changed")
        if any(path.casefold() == p.casefold()
               or path.casefold().startswith(p.casefold() + "/") for p in prohibited):
            raise CandidateBindingError("Prohibited path changed")
        if not any(path == p or path.startswith(p + "/") for p in allowed):
            raise CandidateBindingError("Changed path outside approved scope")


def _current(resolver):
    if not callable(resolver):
        raise CandidateBindingError("Trusted current-candidate resolver required")
    try:
        sha = resolver()
    except Exception as exc:
        raise CandidateBindingError("Current candidate could not be established") from exc
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise CandidateBindingError("Current candidate must be a known full commit")
    return sha


def seal_committed_candidate(git_dir: Path | str, repository_id: str, base_sha: str,
                             approved_suite_sha: str, context: BindingContext,
                             current_candidate: Callable[[], str], *,
                             allowed_paths: tuple[str, ...],
                             prohibited_paths: tuple[str, ...] = ()) -> CandidateSeal:
    """Capture immutable objects; never commit or freeze an arbitrary dirty worktree.

    The approved suite is a separate commit in this trusted repository's object
    store. Its digest must already be approved and recorded by the controller.
    """
    if type(context) is not BindingContext:
        raise CandidateBindingError("Explicit controller binding context required")
    _scope(allowed_paths, required=True)
    _scope(prohibited_paths, required=False)
    head = _current(current_candidate)
    base = measure_git_commit(git_dir, base_sha, repository_id)
    candidate = measure_git_commit(git_dir, head, repository_id)
    suite = measure_git_commit(git_dir, approved_suite_sha, repository_id)
    diff = compare_snapshots(base, candidate, expected_base_digest=base.digest,
                             expected_candidate_digest=candidate.digest)
    seal = CandidateSeal(context, base, candidate, suite, allowed_paths,
                         prohibited_paths, diff.digest)
    if _current(current_candidate) != head:
        raise CandidateBindingError("Candidate moved while sealing")
    return seal


@dataclass(frozen=True)
class TestObservation:
    """A trusted executor's observation, NOT an authenticated worker message."""

    execution_id: str
    executor_id: str
    seal_digest: str
    context_digest: str
    candidate_snapshot_digest: str
    suite_snapshot_digest: str
    runner_profile_digest: str
    exit_code: int
    junit_xml: str

    def __post_init__(self):
        _id(self.execution_id)
        _id(self.executor_id)
        for value in (self.seal_digest, self.context_digest, self.candidate_snapshot_digest,
                      self.suite_snapshot_digest, self.runner_profile_digest):
            _hash(value)
        if type(self.exit_code) is not int or not isinstance(self.junit_xml, str):
            raise CandidateBindingError("Measured exit code and structured report required")


@dataclass(frozen=True)
class BoundTestEvidence:
    seal_digest: str
    execution_id: str
    executor_id: str
    report_digest: str
    tests: int
    skipped: int
    status: str = "BOUND_TEST_EVIDENCE"


def bind_test_evidence(git_dir: Path | str, seal: CandidateSeal, *,
                       expected_seal_digest: str, current_context: BindingContext,
                       current_candidate: Callable[[], str],
                       observation: TestObservation) -> BoundTestEvidence:
    """Recheck current candidate and all bindings before returning bound evidence.

    The controller must serialize/CAS any later state update against this seal;
    this function does not claim to prevent a change after it returns.
    """
    if type(seal) is not CandidateSeal or type(observation) is not TestObservation:
        raise CandidateBindingError("Controller seal and independent observation required")
    _hash(expected_seal_digest)
    if seal.digest != expected_seal_digest or current_context != seal.context:
        raise CandidateBindingError("Seal or current task/spec/policy/suite/runner context changed")
    if (observation.seal_digest != seal.digest
            or observation.context_digest != seal.context.digest
            or observation.candidate_snapshot_digest != seal.candidate.digest
            or observation.suite_snapshot_digest != seal.approved_suite.digest
            or observation.runner_profile_digest != seal.context.runner_profile_digest):
        raise CandidateBindingError("Execution is not bound to the sealed candidate and approved suite")
    head = _current(current_candidate)
    if head != seal.candidate.commit_sha:
        raise CandidateBindingError("Stale candidate before evidence acceptance")
    measured = measure_git_commit(git_dir, head, seal.candidate.repository_id)
    if measured != seal.candidate:
        raise CandidateBindingError("Current measured candidate does not match seal")
    if observation.exit_code != 0:
        raise CandidateBindingError("Independent executor failed")
    passed, _, counts = IndependentVerifier.parse_junit_xml(observation.junit_xml)
    if not passed:
        raise CandidateBindingError("Independent structured test report did not pass")
    if _current(current_candidate) != head:
        raise CandidateBindingError("Candidate moved during evidence acceptance")
    return BoundTestEvidence(seal.digest, observation.execution_id, observation.executor_id,
                             hashlib.sha256(observation.junit_xml.encode()).hexdigest(),
                             counts["tests"], counts["skipped"])
