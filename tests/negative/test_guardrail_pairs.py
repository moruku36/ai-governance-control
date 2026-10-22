"""R3/R4/R5 regression pairs: each denial has a related permitted control.

No dangerous command is executed: policy cases inspect structured inputs only.
Hook integration cases launch this Python interpreter on synthetic local data.
"""

import subprocess
import sys
from unittest.mock import patch

import pytest

from orchestrator.core.hooks import (
    HookEngine,
    HookEvent,
    HookExecutionError,
    run_command_hook,
)

# One row owns both outcomes; missing either half fails this table's shape check.
GIT_PAIRS = [
    ("protected-short", ("main", "push", False), ("task/example", "push", False)),
    ("protected-full-ref", ("refs/heads/main", "push", False),
     ("refs/heads/task/example", "push", False)),
    ("protected-force", ("master", "push", True), ("task/example", "push", True)),
    ("missing-branch", ("", "push", False), ("task/example", "push", False)),
    ("unresolved-head", ("HEAD", "push", False), ("task/example", "push", False)),
    ("wrong-ref-kind", ("refs/tags/main", "push", False),
     ("refs/heads/task/example", "push", False)),
    ("unknown-operation", ("task/example", "", False),
     ("task/example", "direct_commit", False)),
    ("unknown-force", ("task/example", "push", None), ("task/example", "push", False)),
    ("newline-branch", ("main\n", "push", False), ("task/example", "push", False)),
    ("missing-branch-type", (None, "push", False), ("task/example", "push", False)),
]
COMMAND_PAIRS = [
    ("empty", "", "pytest"),
    ("whitespace", " \t", "ruff"),
    ("unregistered", "curl", "git"),
    ("raw-command", "pytest tests", "pytest"),
    ("chained-line", "git\npush", "git"),
    ("nested-command", "python -c print(1)", "python"),
    ("wrong-type", None, "node"),
]


@pytest.mark.parametrize("case,denied,allowed", GIT_PAIRS, ids=[r[0] for r in GIT_PAIRS])
def test_git_guard_pairs(case, denied, allowed, tmp_path, monkeypatch):
    from orchestrator.core.policy import (
        BranchProtectionError,
        HardDenyViolationError,
        PolicyEngine,
    )

    # No repository discovery from cwd: an unrelated directory gives the same verdict.
    monkeypatch.chdir(tmp_path)
    policy = PolicyEngine()
    with pytest.raises((BranchProtectionError, HardDenyViolationError)) as error:
        policy.evaluate_git_operation(*denied)
    assert str(error.value)  # Auditable diagnostic, never a silent pass.
    policy.evaluate_git_operation(*allowed)


@pytest.mark.parametrize("case,denied,allowed", COMMAND_PAIRS, ids=[r[0] for r in COMMAND_PAIRS])
def test_command_id_pairs(case, denied, allowed):
    from orchestrator.core.policy import CommandNotAllowedError, PolicyEngine

    policy = PolicyEngine()
    with pytest.raises(CommandNotAllowedError):
        policy.evaluate_command_id(denied)
    policy.evaluate_command_id(allowed)


@pytest.mark.parametrize("bad_cwd", [None, "", ".", "missing", "nul\0path"])
def test_hook_cwd_pairs(bad_cwd, tmp_path):
    argv = [sys.executable, "-c", "print('synthetic-hook')"]
    with patch("orchestrator.core.hooks.subprocess.run") as launch:
        refused = run_command_hook(argv, bad_cwd)
        assert refused["status"] == "ERROR"
        assert "DENIED" in refused["reason"]
        launch.assert_not_called()
    assert run_command_hook(argv, str(tmp_path))["status"] == "PASS"


def test_hook_missing_and_file_directory_pairs(tmp_path):
    file_path = tmp_path / "synthetic.txt"
    file_path.write_text("synthetic", encoding="utf-8")
    argv = [sys.executable, "-c", "print('ok')"]
    for invalid in (tmp_path / "absent", file_path):
        with patch("orchestrator.core.hooks.subprocess.run") as launch:
            result = run_command_hook(argv, str(invalid))
            assert result["status"] == "ERROR"
            assert "DENIED" in result["reason"]
            launch.assert_not_called()
    assert run_command_hook(argv, str(tmp_path))["status"] == "PASS"


def test_hook_uses_explicit_cwd_and_literal_argv(tmp_path, monkeypatch):
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "marker.txt").write_text("synthetic-marker", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    # Mentioned text is data. No shell parser or nested execution is introduced.
    mentioned = "git push --force main\neval $(example); > .env"
    argv = [sys.executable, "-c",
            ("from pathlib import Path; import sys; "
             "print(Path('marker.txt').read_text()); print(sys.argv[1])"), mentioned]
    result = run_command_hook(argv, str(repository))
    assert result["status"] == "PASS"
    assert "synthetic-marker" in result["output"]
    assert mentioned in result["output"]


@pytest.mark.parametrize("bad_argv", [None, "python", [], [""], [1], ["nul\0exe"]])
def test_hook_typed_argv_pairs(bad_argv, tmp_path):
    with patch("orchestrator.core.hooks.subprocess.run") as launch:
        result = run_command_hook(bad_argv, str(tmp_path))
        assert result["status"] == "ERROR"
        assert "DENIED" in result["reason"]
        launch.assert_not_called()
    assert run_command_hook([sys.executable, "-c", "print('ok')"], str(tmp_path))["status"] == "PASS"


def test_hook_engine_propagates_context_denial(tmp_path):
    engine = HookEngine()
    engine.register_hook(HookEvent.BEFORE_PUSH,
                         lambda ctx: run_command_hook([sys.executable, "-c", "print('ok')"],
                                                      ctx["cwd"]))
    with pytest.raises(HookExecutionError, match="absolute cwd.*DENIED"):
        engine.execute_hook(HookEvent.BEFORE_PUSH, {"cwd": None}, required=True)
    assert engine.execute_hook(HookEvent.BEFORE_PUSH, {"cwd": str(tmp_path)}, required=True)


def test_hook_launch_failure_pair(tmp_path):
    argv = [sys.executable, "-c", "print('ok')"]
    with patch("orchestrator.core.hooks.subprocess.run", side_effect=OSError("unavailable")):
        assert run_command_hook(argv, str(tmp_path))["status"] == "ERROR"
    assert run_command_hook(argv, str(tmp_path))["status"] == "PASS"


def test_hook_nonzero_pair(tmp_path):
    assert run_command_hook([sys.executable, "-c", "raise SystemExit(1)"],
                            str(tmp_path))["status"] == "FAIL"
    assert run_command_hook([sys.executable, "-c", "print('ok')"],
                            str(tmp_path))["status"] == "PASS"


def test_pair_tables_are_complete():
    for table in (GIT_PAIRS, COMMAND_PAIRS):
        assert table
        assert len({row[0] for row in table}) == len(table)
        assert all(len(row) == 3 and row[1] != row[2] for row in table)


def test_hook_pass_explicitly_disables_shell(tmp_path):
    with patch("orchestrator.core.hooks.subprocess.run",
               return_value=subprocess.CompletedProcess([], 0, "ok", "")) as launch:
        assert run_command_hook([sys.executable], str(tmp_path))["status"] == "PASS"
        assert launch.call_args.kwargs["shell"] is False


@pytest.mark.parametrize("configured", ["main", "refs/heads/main"])
@pytest.mark.parametrize("requested", ["main", "refs/heads/main"])
def test_custom_protected_branch_forms_are_equivalent(configured, requested):
    from orchestrator.core.policy import HardDenyViolationError, PolicyEngine

    data = dict(PolicyEngine().policy_data)
    data["protected_branches"] = [configured]
    policy = PolicyEngine(data)
    with pytest.raises(HardDenyViolationError):
        policy.evaluate_git_operation(requested, "push")
    policy.evaluate_git_operation("task/example", "push")
