import os
import pytest
import duckdb
from app.ai.learning.continuous_runner import ContinuousLearningRunner
from app.ai.learning import continuous_runner


def _isolate_runner_outputs(monkeypatch, tmp_path):
    monkeypatch.setattr(continuous_runner, "CHECKPOINTS_ROOT", str(tmp_path / "checkpoints"))
    monkeypatch.setattr(continuous_runner, "REPORTS_ROOT", str(tmp_path / "reports"))


def test_runner_initialization(tmp_path, monkeypatch):
    _isolate_runner_outputs(monkeypatch, tmp_path)
    runner = ContinuousLearningRunner(
        duration_minutes=1.0,
        checkpoint_minutes=0.2,
        run_id="test_runner_run",
        test_mode=True
    )
    assert runner.duration_seconds == 60.0
    assert runner.interval_seconds == 12.0
    assert os.path.exists(runner.workspace_dir)

def test_runner_executes_cycle_and_promotes(tmp_path, monkeypatch):
    _isolate_runner_outputs(monkeypatch, tmp_path)
    from app.ai.learning.evaluation_service import evaluation_service
    monkeypatch.setattr(evaluation_service, "setup_database_context", lambda: duckdb.connect(":memory:"))
    monkeypatch.setattr(evaluation_service, "evaluate", lambda split="test": {
        "numerical_accuracy": 100.0,
        "execution_success_rate": 100.0,
        "latency_p50_ms": 1.0,
    })
    runner = ContinuousLearningRunner(
        duration_minutes=0.5,
        checkpoint_minutes=0.1,
        run_id="test_exec_run",
        test_mode=True
    )
    monkeypatch.setattr(runner, "_generate_candidate_problems", lambda cycle_num, con: [{
        "example_id": "candidate-test",
        "sql_query": "SELECT 1 AS metric",
    }])
    result = runner.run()
    assert result["run_id"] == "test_exec_run"
    assert result["baseline_accuracy"] == 100.0
    assert result["cycles_completed"] >= 1
    assert result["cycles"][0]["decision"] == "PROMOTED"
    assert result["total_candidates_promoted"] == 1
    assert runner.last_verified_checkpoint is not None
    assert runner.last_verified_checkpoint.startswith(str(tmp_path / "checkpoints"))
    assert os.path.exists(runner.last_verified_checkpoint)
    assert (tmp_path / "reports" / "learning_run_report.json").is_file()

def test_runner_rejects_on_simulated_regression(tmp_path, monkeypatch):
    _isolate_runner_outputs(monkeypatch, tmp_path)
    from app.ai.learning.evaluation_service import evaluation_service
    runner = ContinuousLearningRunner(
        duration_minutes=0.5,
        checkpoint_minutes=0.1,
        run_id="test_reject_run",
        test_mode=True
    )
    monkeypatch.setattr(evaluation_service, "setup_database_context", lambda: duckdb.connect(":memory:"))
    monkeypatch.setattr(runner, "_generate_candidate_problems", lambda cycle_num, con: [{
        "example_id": "candidate-test",
        "sql_query": "SELECT 1 AS metric",
    }])
    # Simulate a regression in evaluation
    monkeypatch.setattr(evaluation_service, "evaluate", lambda split="test": {
        "numerical_accuracy": 50.0,
        "execution_success_rate": 60.0,
        "latency_p50_ms": 1.0
    })

    cycle_res = runner.execute_cycle(cycle_num=99, baseline_acc=100.0)
    assert cycle_res["decision"] == "REJECTED"
    assert len(cycle_res["gate_reasons"]) > 0
    # No checkpoint should be created or promoted for a rejected cycle
    assert cycle_res["checkpoint_file"] is None
    assert runner.last_verified_checkpoint is None
