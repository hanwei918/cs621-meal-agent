"""C10: source-code revision metadata stays valid outside a Git checkout (offline)."""
from __future__ import annotations

import json
import subprocess

from eval import harness
from eval.harness import load_cases, run_eval
from meal.runner import AgentUsage


class OfflineAgent:
    def run(self, env):
        env.call("get_profile")
        return AgentUsage()


def test_fingerprint_is_stable_for_identical_source_files(tmp_path, monkeypatch):
    (tmp_path / "meal").mkdir()
    (tmp_path / "eval").mkdir()
    (tmp_path / "meal" / "a.py").write_text("x=1\n")
    (tmp_path / "eval" / "b.py").write_text("y=2\n")
    (tmp_path / "run.py").write_text("run=True\n")
    monkeypatch.setattr(harness, "ROOT", tmp_path)
    first = harness._source_code_sha256()
    assert len(first) == 64
    assert first == harness._source_code_sha256()
    (tmp_path / "eval" / "b.py").write_text("y=3\n")
    assert first != harness._source_code_sha256()


def test_fingerprint_does_not_change_from_test_artifacts(tmp_path, monkeypatch):
    (tmp_path / "meal").mkdir()
    (tmp_path / "meal" / "agent.py").write_text("pass\n")
    monkeypatch.setattr(harness, "ROOT", tmp_path)
    first = harness._source_code_sha256()
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_dummy.py").write_text("pass\n")
    (tmp_path / "meal" / "__pycache__").mkdir()
    (tmp_path / "meal" / "__pycache__" / "agent.pyc").write_bytes(b"junk")
    assert first == harness._source_code_sha256()


def test_missing_git_revision_is_replaced_by_source_fingerprint(monkeypatch):
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, returncode=128, stdout="", stderr="not a git repository")
    monkeypatch.setattr(subprocess, "run", fake_run)
    sha = harness._source_code_sha256()
    assert harness._code_revision(sha) == f"sha256:{sha[:12]}"


def test_nonzero_git_status_never_becomes_revision(monkeypatch):
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, returncode=128, stdout="stale-output", stderr="error")
    monkeypatch.setattr(subprocess, "run", fake_run)
    sha = harness._source_code_sha256()
    assert harness._code_revision(sha) == f"sha256:{sha[:12]}"


def test_missing_git_binary_uses_fingerprint(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise FileNotFoundError("git missing")
    monkeypatch.setattr(subprocess, "run", fake_run)
    sha = harness._source_code_sha256()
    assert harness._code_revision(sha) == f"sha256:{sha[:12]}"


def test_valid_git_revision_is_preserved(monkeypatch):
    def fake_run(cmd, **kwargs):
        if "rev-parse" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="a1b2c3d\n")
        return subprocess.CompletedProcess(cmd, 0, stdout="")
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert harness._code_revision("f" * 64) == "a1b2c3d"


def test_dirty_git_revision_is_preserved(monkeypatch):
    def fake_run(cmd, **kwargs):
        if "rev-parse" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="a1b2c3d\n")
        return subprocess.CompletedProcess(cmd, 0, stdout=" M meal/agent.py\n")
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert harness._code_revision("f" * 64) == "a1b2c3d-dirty"


def test_new_eval_summary_has_version_and_keeps_original_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(harness, "RUNS", tmp_path)
    case = load_cases(["c01"])[0]
    rep = run_eval(lambda c: OfflineAgent(), [case], n_runs=1, write=True, model="-", name="offline-c10")
    meta = json.loads((rep.run_dir / "summary.json").read_text(encoding="utf-8"))["meta"]
    sha = harness._source_code_sha256()
    assert meta["code_sha256"] == sha
    assert meta["code"] and meta["eval_sha256"] and meta["case_set"] == "v1"
    assert len(meta["eval_sha256"]) == 64
    assert (rep.run_dir / "results.jsonl").exists()


def test_fingerprint_distinguishes_run_py_and_meal_submodule(tmp_path, monkeypatch):
    (tmp_path / "meal").mkdir()
    (tmp_path / "eval").mkdir()
    (tmp_path / "meal" / "agent.py").write_text("a=1\n")
    (tmp_path / "run.py").write_text("x=1\n")
    monkeypatch.setattr(harness, "ROOT", tmp_path)
    original = harness._source_code_sha256()
    (tmp_path / "run.py").write_text("x=2\n")
    with_run_change = harness._source_code_sha256()
    assert with_run_change != original
    (tmp_path / "meal" / "agent.py").write_text("a=2\n")
    assert harness._source_code_sha256() != with_run_change
