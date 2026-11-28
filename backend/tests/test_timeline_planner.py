import csv
import asyncio

from app.ai.planning.timeline_planner import TimelinePlanner
from app.ai.planning.validator import PlanValidator
from app.analysis.execution.duckdb_engine import DuckDBEngine
from app.models.file import StoredFile
from app.ai.orchestration.orchestrator import AnalysisOrchestrator
from app.ai.orchestration.intent import IntentClassifier
from app.ai.orchestration.ambiguity import AmbiguityDetector


def _profile(columns, rows=3):
    return {
        "row_count": rows,
        "columns": [
            {"name": name, "role": role, "inferred_type": kind, "sample_values": []}
            for name, role, kind in columns
        ],
    }


def _run_csv_plan(tmp_path, headers, rows, profile, question):
    path = tmp_path / "timeline.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)
    file_id = "timeline-file"
    stored = StoredFile(
        id=file_id, owner_user_id="user-1", unit_id="unit-1", original_name="timeline.csv",
        content_type="text/csv", size_bytes=path.stat().st_size, storage_key=str(path), schema_profile=profile,
    )
    files_map = {file_id: stored}
    plan = TimelinePlanner.build_if_applicable(question, file_id, profile)
    assert plan is not None
    plan = PlanValidator.validate_plan(plan, files_map)
    return plan, DuckDBEngine.execute(plan, files_map, {file_id: str(path)})


def test_point_event_plan_calculates_span_and_same_time_location_conflicts(tmp_path):
    profile = _profile([
        ("employee_id", "identifier", "string"),
        ("event_timestamp", "timestamp", "datetime"),
        ("location", "dimension", "string"),
    ])
    plan, result = _run_csv_plan(
        tmp_path,
        ["employee_id", "event_timestamp", "location"],
        [
            ["Asha", "2026-03-01T08:00:00Z", "Pune"],
            ["Asha", "2026-03-01T08:00:00Z", "Mumbai"],
            ["Asha", "2026-03-01T16:00:00Z", "Pune"],
        ],
        profile,
        "Asha ne kitna ghanta travel kiya aur same time do jagah toh nahi thi?",
    )
    assert plan.intent == "timeline_consistency"
    assert result["rows"][0]["elapsed_span_hours"] == 8.0
    assert result["rows"][0]["active_hours"] is None
    assert result["rows"][0]["simultaneous_location_conflict_count"] == 1
    assert result["rows"][0]["total_people"] == 1


def test_interval_plan_unions_overlapping_time_and_flags_location_conflict(tmp_path):
    profile = _profile([
        ("person", "dimension", "string"),
        ("start_time", "timestamp", "datetime"),
        ("end_time", "timestamp", "datetime"),
        ("place", "dimension", "string"),
    ])
    _, result = _run_csv_plan(
        tmp_path,
        ["person", "start_time", "end_time", "place"],
        [
            ["Asha", "2026-03-01T08:00:00Z", "2026-03-01T12:00:00Z", "Pune"],
            ["Asha", "2026-03-01T10:00:00Z", "2026-03-01T14:00:00Z", "Mumbai"],
            ["Asha", "2026-03-01T15:00:00Z", "2026-03-01T17:00:00Z", "Pune"],
        ],
        profile,
        "Kitne ghante person alag-alag locations par tha aur overlap hua?",
    )
    assert result["rows"][0]["elapsed_span_hours"] == 9.0
    assert result["rows"][0]["active_hours"] == 8.0
    assert result["rows"][0]["overlapping_location_conflict"] is True


def test_coordinate_travel_rate_is_only_flagged_against_requested_threshold(tmp_path):
    profile = _profile([
        ("person", "dimension", "string"),
        ("event_time", "timestamp", "datetime"),
        ("latitude", "measure", "float"),
        ("longitude", "measure", "float"),
    ], rows=2)
    _, result = _run_csv_plan(
        tmp_path,
        ["person", "event_time", "latitude", "longitude"],
        [
            ["Asha", "2026-03-01T08:00:00Z", 18.5204, 73.8567],
            ["Asha", "2026-03-01T08:30:00Z", 19.0760, 72.8777],
        ],
        profile,
        "Check impossible travel; flag speeds over 80 km/h.",
    )
    assert result["rows"][0]["max_required_travel_speed_kmh"] > 100
    assert result["rows"][0]["travel_legs_over_threshold"] == 1


def test_coordinate_travel_does_not_make_unrequested_feasibility_claim(tmp_path):
    profile = _profile([
        ("person", "dimension", "string"),
        ("event_time", "timestamp", "datetime"),
        ("latitude", "measure", "float"),
        ("longitude", "measure", "float"),
    ], rows=2)
    _, result = _run_csv_plan(
        tmp_path,
        ["person", "event_time", "latitude", "longitude"],
        [
            ["Asha", "2026-03-01T08:00:00Z", 18.5204, 73.8567],
            ["Asha", "2026-03-01T08:30:00Z", 19.0760, 72.8777],
        ],
        profile,
        "How many hours did this person travel?",
    )
    row = result["rows"][0]
    assert row["max_required_travel_speed_kmh"] > 100
    assert row["travel_legs_over_threshold"] is None


def test_simultaneous_distinct_coordinates_are_flagged_as_conflicting_locations(tmp_path):
    profile = _profile([
        ("person", "dimension", "string"),
        ("event_time", "timestamp", "datetime"),
        ("latitude", "measure", "float"),
        ("longitude", "measure", "float"),
    ], rows=2)
    _, result = _run_csv_plan(
        tmp_path,
        ["person", "event_time", "latitude", "longitude"],
        [
            ["Asha", "2026-03-01T08:00:00Z", 18.5204, 73.8567],
            ["Asha", "2026-03-01T08:00:00Z", 19.0760, 72.8777],
        ],
        profile,
        "Was one person at two locations at the same timestamp?",
    )
    assert result["rows"][0]["simultaneous_location_conflict_count"] == 1


def test_planner_refuses_to_guess_between_multiple_unnamed_timestamps():
    profile = _profile([
        ("person_id", "identifier", "string"),
        ("timestamp_a", "timestamp", "datetime"),
        ("timestamp_b", "timestamp", "datetime"),
        ("location", "dimension", "string"),
    ])
    assert TimelinePlanner.build_if_applicable("how many hours did this person travel?", "f1", profile) is None


def test_regular_data_question_is_not_captured_by_timeline_planner():
    profile = _profile([
        ("employee_id", "identifier", "string"),
        ("event_timestamp", "timestamp", "datetime"),
        ("location", "dimension", "string"),
        ("sales", "measure", "float"),
    ])
    assert TimelinePlanner.build_if_applicable("total sales by employee", "f1", profile) is None


def test_orchestrator_routes_resolved_timeline_question_to_deterministic_plan():
    profile = _profile([
        ("employee_id", "identifier", "string"),
        ("event_timestamp", "timestamp", "datetime"),
        ("location", "dimension", "string"),
    ])
    file_id = "timeline-file"
    stored = StoredFile(
        id=file_id, owner_user_id="user-1", original_name="timeline.csv", content_type="text/csv",
        size_bytes=1, storage_key="timeline.csv", schema_profile=profile,
    )
    service = AnalysisOrchestrator.__new__(AnalysisOrchestrator)
    plan = asyncio.run(service._plan_with_ai(
        "Asha ne kitna ghanta travel kiya aur same time do jagah toh nahi thi?",
        [file_id], {file_id: stored}, "DATA_ANALYSIS", ai_tier="low",
    ))
    assert plan.intent == "timeline_consistency"
    assert "timeline_mode:events" in plan.skills


def test_timeline_formatter_does_not_use_ai_and_explains_the_limits():
    from app.ai.planning.schemas import AnalysisPlan, DatasetRef

    plan = AnalysisPlan(
        intent="timeline_consistency", result_shape="timeline", question="kitna ghanta travel?",
        datasets=[DatasetRef(file_id="f1", alias="ds_1")],
        skills=["person_timeline", "timeline_mode:events", "timeline_has_location:true", "timeline_has_coordinates:false", "timeline_speed_threshold_kmh:"],
    )
    result = {
        "row_count": 1, "duration_ms": 5, "source_row_count": 2,
        "rows": [{
            "person": "Asha", "first_observed": "2026-03-01T08:00:00+00:00",
            "last_observed": "2026-03-01T16:00:00+00:00", "elapsed_span_hours": 8.0,
            "active_hours": None, "simultaneous_location_conflict_count": 1,
        }],
    }
    service = AnalysisOrchestrator.__new__(AnalysisOrchestrator)
    answer = asyncio.run(service._format_executive_answer("kitna ghanta travel?", plan, result, {}, ai_tier="low"))
    assert "8 hours" in answer
    assert "active/travel time cannot be inferred" in answer
    assert "simultaneous-location conflict" in answer
    assert "not proof of misconduct" in answer


def test_conceptual_time_travel_stays_general_chat_even_with_dataset_attached():
    assert IntentClassifier.classify(
        "What if I use a time machine and prevent my grandparents from meeting?",
        ["an-attached-dataset"],
    ) == "GENERAL_CHAT"


def test_sheet_timestamp_location_question_uses_data_analysis_route():
    assert IntentClassifier.classify(
        "In this sheet, did the same employee appear at two locations at one timestamp?",
        ["an-attached-dataset"],
    ) == "DATA_ANALYSIS"


def test_multiple_event_timestamps_ask_user_instead_of_guessing():
    profile = _profile([
        ("person_id", "identifier", "string"),
        ("office_timestamp", "timestamp", "datetime"),
        ("vehicle_timestamp", "timestamp", "datetime"),
        ("location", "dimension", "string"),
    ])
    stored = StoredFile(
        id="timeline-file", owner_user_id="user-1", original_name="timeline.csv", content_type="text/csv",
        size_bytes=1, storage_key="timeline.csv", schema_profile=profile,
    )
    prompt = "For each person, how many hours passed and was one person at two locations at the same timestamp?"
    payload = AmbiguityDetector.detect(prompt, {"timeline-file": stored})
    assert payload["reason"] == "AMBIGUOUS_TIMESTAMP_COLUMN"
    assert {option["value"] for option in payload["options"]} == {"office_timestamp", "vehicle_timestamp"}
    binding = AmbiguityDetector.validate_resume_response(payload, {"selected": "office_timestamp"})
    enriched = AmbiguityDetector.apply_bindings_to_question(prompt, [binding])
    plan = TimelinePlanner.build_if_applicable(enriched, "timeline-file", profile)
    assert plan is not None
    assert '"office_timestamp"' in plan.sql_query
    assert '"vehicle_timestamp"' not in plan.sql_query
