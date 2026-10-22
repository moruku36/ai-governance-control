"""G1 full Git-tree inventory foundation; not an approval or handoff admission gate.

Only use an operator-owned, immutable Git object store. A worker-provided repository,
repository ID, snapshot or digest is not trusted merely because it validates here.
"""

import hashlib
import json
import os
import re
import subprocess
import threading
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from time import monotonic

CONTRACT_VERSION = "full-candidate/1"
_SHA1 = re.compile(r"[0-9a-f]{40}")
_SHA256 = re.compile(r"[0-9a-f]{64}")


class CandidateError(ValueError):
    """Missing, unsupported, over-budget or inconsistent full-tree evidence."""


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode("ascii")).hexdigest()


def _path(path: str) -> None:
    if (not isinstance(path, str) or not path or path.startswith("/")
            or "\\" in path or ":" in path or unicodedata.normalize("NFC", path) != path
            or any(ord(c) < 32 or ord(c) == 127 for c in path)):
        raise CandidateError("Noncanonical inventory path")
    parts = path.split("/")
    if any(p in {"", ".", ".."} or p.casefold() == ".git" or p.endswith((".", " "))
           for p in parts):
        raise CandidateError("Unsafe inventory path")


@dataclass(frozen=True)
class TreeEntry:
    path: str
    mode: str
    content_sha256: str

    def __post_init__(self):
        _path(self.path)
        if self.mode not in {"100644", "100755"}:
            raise CandidateError("Only regular Git blobs are supported; no links or submodules")
        if not isinstance(self.content_sha256, str) or not _SHA256.fullmatch(self.content_sha256):
            raise CandidateError("Invalid content digest")

    def record(self):
        return [self.path, self.mode, self.content_sha256]


@dataclass(frozen=True)
class TreeSnapshot:
    repository_id: str
    commit_sha: str
    entries: tuple[TreeEntry, ...]
    contract_version: str = CONTRACT_VERSION

    def __post_init__(self):
        if self.contract_version != CONTRACT_VERSION:
            raise CandidateError("Unsupported inventory contract")
        if (not isinstance(self.repository_id, str)
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", self.repository_id)):
            raise CandidateError("An operator-assigned repository ID is required")
        if not isinstance(self.commit_sha, str) or not _SHA1.fullmatch(self.commit_sha):
            raise CandidateError("A known full lowercase SHA-1 commit is required")
        if type(self.entries) is not tuple or any(type(e) is not TreeEntry for e in self.entries):
            raise CandidateError("An immutable complete entry inventory is required")
        paths = [e.path for e in self.entries]
        if paths != sorted(paths) or len({p.casefold() for p in paths}) != len(paths):
            raise CandidateError("Unsorted, duplicate or case-colliding inventory")
        seen = {p.casefold() for p in paths}
        if any("/".join(p.split("/")[:i]).casefold() in seen
               for p in paths for i in range(1, len(p.split("/")))):
            raise CandidateError("File/directory collision")

    @property
    def digest(self):
        return _digest({"version": self.contract_version, "repository": self.repository_id,
                        "commit": self.commit_sha, "entries": [e.record() for e in self.entries]})


@dataclass(frozen=True)
class CandidateDiff:
    base: TreeSnapshot
    candidate: TreeSnapshot
    changed_paths: tuple[str, ...]
    digest: str


def compare_snapshots(base: TreeSnapshot, candidate: TreeSnapshot, *,
                      expected_base_digest: str, expected_candidate_digest: str) -> CandidateDiff:
    """Compare full inventories against separately held controller measurements.

    Digests are integrity checks, not signatures. Never use worker-supplied expected
    digests to establish trust, completeness, approval or test success.
    """
    if type(base) is not TreeSnapshot or type(candidate) is not TreeSnapshot:
        raise CandidateError("Full snapshots required; partial artifact maps are unsupported")
    if base.repository_id != candidate.repository_id:
        raise CandidateError("Repository provenance mismatch")
    if base.digest != expected_base_digest or candidate.digest != expected_candidate_digest:
        raise CandidateError("Snapshot changed or trusted measurement is missing")
    before = {e.path: e for e in base.entries}
    after = {e.path: e for e in candidate.entries}
    changes = []
    for path in sorted(before.keys() | after.keys()):
        old, new = before.get(path), after.get(path)
        if old != new:
            changes.append([path, old.record() if old else None, new.record() if new else None])
    digest = _digest({"version": CONTRACT_VERSION, "base": base.digest,
                      "candidate": candidate.digest, "changes": changes})
    return CandidateDiff(base, candidate, tuple(c[0] for c in changes), digest)


def _git(git_dir: Path, args: list[str], limit: int, timeout: float) -> bytes:
    # No inherited Git configuration, replacement objects, lazy network fetching,
    # worktree discovery or candidate-controlled executable/configuration.
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("GIT_") and k in {"PATH", "SYSTEMROOT", "WINDIR"}}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
               GIT_NO_REPLACE_OBJECTS="1", GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0")
    argv = ["git", "--no-pager", f"--git-dir={git_dir}", *args]
    try:
        with subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, env=env, shell=False) as process:
            expired = threading.Event()

            def stop():
                expired.set()
                try:
                    process.kill()
                except OSError:
                    pass

            timer = threading.Timer(timeout, stop)
            timer.start()
            try:
                output = process.stdout.read(limit + 1)
                if len(output) > limit:
                    process.kill()
                code = process.wait()
            finally:
                timer.cancel()
                timer.join()
            if expired.is_set() or code or len(output) > limit:
                raise CandidateError("Git measurement failed, timed out or exceeded output limit")
            return output
    except OSError as exc:
        raise CandidateError("Git measurement unavailable") from exc


def measure_git_commit(git_dir: Path | str, commit_sha: str, repository_id: str, *,
                       max_files: int = 10000, max_file_bytes: int = 1024 * 1024,
                       max_total_bytes: int = 10 * 1024 * 1024,
                       timeout_seconds: int = 10) -> TreeSnapshot:
    """Measure every tracked regular blob in an explicit commit of a trusted store.

    Untracked/dirty worktree files are NOT this candidate. Callers must first freeze
    the intended candidate into a trusted commit; no worktree is read or executed.
    No authentication, policy decision or receipt upgrade occurs here.
    """
    TreeSnapshot(repository_id, commit_sha, ())  # Validate provenance before invoking Git.
    for value in (max_files, max_file_bytes, max_total_bytes, timeout_seconds):
        if type(value) is not int or value <= 0:
            raise CandidateError("Positive integer measurement limits required")
    try:
        location = Path(git_dir)
        if not location.is_absolute() or not location.is_dir() or location.is_symlink():
            raise CandidateError("Explicit trusted absolute Git directory required")
        location = location.resolve(strict=True)
    except (TypeError, OSError, RuntimeError) as exc:
        raise CandidateError("Trusted Git directory cannot be resolved") from exc
    deadline = monotonic() + timeout_seconds

    def read(args, limit):
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise CandidateError("Cumulative measurement deadline exceeded")
        return _git(location, args, limit, remaining)

    if read(["cat-file", "-t", commit_sha], 32) != b"commit\n":
        raise CandidateError("Commit SHA must resolve to a commit, not a tree or tag")
    raw = read(["ls-tree", "-r", "-z", "--full-tree", commit_sha], max_files * 4096)
    if raw and not raw.endswith(b"\0"):
        raise CandidateError("Truncated tree inventory")
    records = raw[:-1].split(b"\0") if raw else []
    if len(records) > max_files:
        raise CandidateError("Too many tree entries")
    entries = []
    total = 0
    for record in records:
        try:
            header, path_bytes = record.split(b"\t", 1)
            mode, kind, oid = header.decode("ascii").split(" ")
            path = path_bytes.decode("utf-8", errors="strict")
        except (ValueError, UnicodeError) as exc:
            raise CandidateError("Malformed or unsupported tree inventory") from exc
        _path(path)
        if mode not in {"100644", "100755"} or kind != "blob" or not _SHA1.fullmatch(oid):
            raise CandidateError("Unsupported Git tree entry")
        size_raw = read(["cat-file", "-s", oid], 32)
        if not re.fullmatch(rb"[0-9]+\n", size_raw):
            raise CandidateError("Invalid blob size")
        size = int(size_raw)
        if size > max_file_bytes or total + size > max_total_bytes:
            raise CandidateError("Blob inventory exceeds byte budget")
        content = read(["cat-file", "blob", oid], size)
        if len(content) != size:
            raise CandidateError("Blob size changed during measurement")
        total += size
        entries.append(TreeEntry(path, mode, hashlib.sha256(content).hexdigest()))
    result = TreeSnapshot(repository_id, commit_sha, tuple(sorted(entries, key=lambda e: e.path)))
    if monotonic() >= deadline:
        raise CandidateError("Cumulative measurement deadline exceeded")
    return result
