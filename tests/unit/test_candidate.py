"""Synthetic trusted Git-store full inventory contracts; no worker execution."""

import hashlib
import subprocess
from dataclasses import replace

import pytest

from orchestrator.core.candidate import (
    CandidateError,
    TreeEntry,
    TreeSnapshot,
    compare_snapshots,
    measure_git_commit,
)


def git(repo, *args, data=None):
    result = subprocess.run(["git", "-C", str(repo), *args], input=data,
                            capture_output=True, check=True)
    return result.stdout.decode().strip()


@pytest.fixture
def store(tmp_path):
    repo = tmp_path / "repository"
    repo.mkdir()
    git(repo, "init", "--quiet")
    return repo


def commit(repo, files):
    """Build immutable objects directly; never invoke commit hooks or a worker."""
    rows = []
    for path, mode, content in files:
        oid = git(repo, "hash-object", "-w", "--stdin", data=content)
        rows.append(f"{mode} blob {oid}\t{path}\n")
    tree = git(repo, "mktree", data="".join(rows).encode())
    payload = (f"tree {tree}\nauthor Synthetic <fixture@example.invalid> 1 +0000\n"
               "committer Synthetic <fixture@example.invalid> 1 +0000\n\nfixture\n")
    return git(repo, "hash-object", "-t", "commit", "-w", "--stdin", data=payload.encode())


def snapshot(repo, sha, **kwargs):
    return measure_git_commit(repo / ".git", sha, "synthetic-repository", **kwargs)


def compare(base, candidate):
    return compare_snapshots(base, candidate, expected_base_digest=base.digest,
                             expected_candidate_digest=candidate.digest)


def test_complete_inventory_binds_delete_add_mode_and_content(store):
    base_sha = commit(store, [("deleted", "100644", b"delete"),
                              ("mode", "100644", b"same"),
                              ("modified", "100644", b"old"),
                              ("unchanged", "100644", b"unchanged")])
    candidate_sha = commit(store, [("added", "100644", b"add"),
                                   ("mode", "100755", b"same"),
                                   ("modified", "100644", b"new"),
                                   ("unchanged", "100644", b"unchanged")])
    base, candidate = snapshot(store, base_sha), snapshot(store, candidate_sha)
    assert compare(base, candidate).changed_paths == ("added", "deleted", "mode", "modified")
    assert base.digest != candidate.digest
    assert len(candidate.digest) == 64
    assert snapshot(store, candidate_sha) == candidate
    assert compare(candidate, candidate).changed_paths == ()
    assert compare(base, candidate).digest != compare(candidate, base).digest


def test_rename_is_canonical_delete_add(store):
    base = snapshot(store, commit(store, [("before", "100644", b"same")]))
    candidate = snapshot(store, commit(store, [("after", "100644", b"same")]))
    assert compare(base, candidate).changed_paths == ("after", "before")


def test_empty_tree_is_complete_and_deletion_is_bound(store):
    base = snapshot(store, commit(store, [("file", "100644", b"x")]))
    empty = snapshot(store, commit(store, []))
    assert empty.entries == ()
    assert compare(base, empty).changed_paths == ("file",)


@pytest.mark.parametrize("sha", ["unknown", "HEAD", "a" * 39, "G" * 40, "A" * 40, None])
def test_unknown_or_noncanonical_base_rejected(store, sha):
    with pytest.raises(CandidateError):
        snapshot(store, sha)


def test_missing_commit_and_noncommit_rejected(store):
    with pytest.raises(CandidateError):
        snapshot(store, "0" * 40)
    blob = git(store, "hash-object", "-w", "--stdin", data=b"not commit")
    with pytest.raises(CandidateError):
        snapshot(store, blob)


@pytest.mark.parametrize("mode", ["120000", "160000", "040000", "100664"])
def test_unsupported_modes_fail_closed(mode):
    with pytest.raises(CandidateError):
        TreeEntry("path", mode, "0" * 64)


def test_git_symlink_rejected(store):
    sha = commit(store, [("link", "120000", b"target")])
    with pytest.raises(CandidateError, match="Unsupported Git tree entry"):
        snapshot(store, sha)


@pytest.mark.parametrize("path", ["", "/absolute", "../escape", "a/../b", "a//b", "a/./b",
                                  ".git/config", "a/.GIT/hooks", "a\\b", "C:escape", "a\nb",
                                  "trailing.", "trailing ", "e\u0301"])
def test_noncanonical_paths_rejected(path):
    with pytest.raises(CandidateError):
        TreeEntry(path, "100644", "0" * 64)


@pytest.mark.parametrize("paths", [("a", "a"), ("A", "a"), ("a", "a/b"),
                                   ("A", "a/b"), ("z", "a")])
def test_duplicate_case_prefix_or_order_collisions_rejected(paths):
    with pytest.raises(CandidateError):
        TreeSnapshot("synthetic", "1" * 40,
                     tuple(TreeEntry(p, "100644", "0" * 64) for p in paths))


def test_mutation_and_wrong_repository_rejected(store):
    base = snapshot(store, commit(store, [("file", "100644", b"original")]))
    changed = replace(base, entries=(TreeEntry("file", "100644", "0" * 64),))
    with pytest.raises(CandidateError, match="changed"):
        compare_snapshots(base, changed, expected_base_digest=base.digest,
                          expected_candidate_digest=base.digest)
    with pytest.raises(CandidateError, match="provenance"):
        compare(base, replace(base, repository_id="other"))
    with pytest.raises(CandidateError, match="partial"):
        compare_snapshots({}, base, expected_base_digest=base.digest,
                          expected_candidate_digest=base.digest)
    with pytest.raises(CandidateError, match="contract"):
        replace(base, contract_version="unknown")
    with pytest.raises(CandidateError, match="immutable"):
        replace(base, entries=list(base.entries))


@pytest.mark.parametrize("limits", [{"max_files": 1}, {"max_file_bytes": 1},
                                    {"max_total_bytes": 3}])
def test_measurement_budgets_reject_complete_run(store, limits):
    sha = commit(store, [("a", "100644", b"aa"), ("b", "100644", b"bb")])
    with pytest.raises(CandidateError):
        snapshot(store, sha, **limits)


@pytest.mark.parametrize("value", [0, -1, True, "1"])
def test_invalid_budget_rejected(store, value):
    with pytest.raises(CandidateError, match="limits"):
        snapshot(store, "0" * 40, max_files=value)


def test_worktree_is_not_candidate_and_inherited_git_env_is_ignored(store, monkeypatch):
    sha = commit(store, [("approved", "100644", b"committed")])
    (store / "approved").write_text("dirty")
    (store / "untracked").write_text("not in commit")
    monkeypatch.setenv("GIT_DIR", "/missing")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "alias.ls-tree")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "!exit 99")
    result = snapshot(store, sha)
    assert [e.path for e in result.entries] == ["approved"]
    assert result.entries[0].content_sha256 == hashlib.sha256(b"committed").hexdigest()


def test_relative_or_missing_git_store_rejected(tmp_path):
    for path in (".", tmp_path / "absent"):
        with pytest.raises(CandidateError, match="absolute"):
            measure_git_commit(path, "0" * 40, "synthetic")


def test_cumulative_deadline_not_reset_for_each_git_call(store, monkeypatch):
    import orchestrator.core.candidate as module

    sha = commit(store, [("file", "100644", b"content")])
    ticks = iter([0, 0.6, 1.2])
    monkeypatch.setattr(module, "monotonic", lambda: next(ticks))
    with pytest.raises(CandidateError, match="Cumulative"):
        snapshot(store, sha, timeout_seconds=1)


def test_git_output_limit_rejects_oversize(store):
    from orchestrator.core.candidate import _git

    oid = git(store, "hash-object", "-w", "--stdin", data=b"too many bytes")
    with pytest.raises(CandidateError, match="output limit"):
        _git(store / ".git", ["cat-file", "blob", oid], 1, 1)


def test_git_timeout_kills_owned_process(store, monkeypatch):
    import sys

    import orchestrator.core.candidate as module

    original = subprocess.Popen

    def sleeping_process(argv, **kwargs):
        return original([sys.executable, "-c", "import time; time.sleep(10)"], **kwargs)

    monkeypatch.setattr(module.subprocess, "Popen", sleeping_process)
    with pytest.raises(CandidateError, match="timed out"):
        module._git(store / ".git", ["cat-file", "-t", "0" * 40], 32, 0.05)


def test_handoff_complete_diff_refusal_is_unchanged():
    from orchestrator.core.handoff import HandoffError, validate_manifest

    # Only pre-gate fields are needed: full-tree inventory does not upgrade receipts.
    manifest = {
        "schema_version": "0.1", "run_id": "synthetic", "attempt_id": "one",
        "purpose": "fixture", "producer": "fixture", "next_step": "review",
        "parent_run_id": None, "request_sha256": "0" * 64,
        "declared_status": "EXECUTED", "acceptance_criteria": ["fixture"],
        "source": {"repository": "synthetic", "commit_sha": "1" * 40,
                   "snapshot_sha256": "0" * 64, "dirty": False,
                   "complete_diff_required": True, "base_sha": "2" * 40},
    }
    with pytest.raises(HandoffError, match="complete diff verification is unsupported"):
        validate_manifest(manifest)
