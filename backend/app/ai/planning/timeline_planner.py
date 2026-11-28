"""Build deterministic, schema-grounded person timeline audits."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from app.ai.planning.schemas import AnalysisPlan, DatasetRef
from app.analysis.execution.compiler import escape_identifier


TIMELINE_TERMS = (
    "timeline", "travel", "traveled", "travelled", "movement", "fira", "ghuma",
    "ghante", "ghanta", "hours spent", "kitna time", "kitni der", "duration",
    "same time", "same timestamp", "simultaneous", "two places", "two locations",
    "different locations", "do jagah", "ek hi waqt", "ek hi time", "impossible travel",
    "overlap", "location conflict",
)


def _quoted(name: str) -> str:
    return escape_identifier(name)


def _timestamp_columns(profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        column for column in profile.get("columns", [])
        if column.get("role") == "timestamp"
        or column.get("inferred_type") in {"datetime", "date"}
        or re.search(r"\b(date|time|timestamp|datetime|checkin|checkout)\b", str(column.get("name", "")).lower())
    ]


def _ranked_column(columns: List[Dict[str, Any]], patterns: List[Tuple[int, str]]) -> Optional[str]:
    ranked = []
    for column in columns:
        name = str(column.get("name", ""))
        lowered = name.lower().replace("_", " ").replace("-", " ")
        score = max((weight for weight, pattern in patterns if re.search(pattern, lowered)), default=0)
        if score:
            ranked.append((score, name))
    if not ranked:
        return None
    best = max(score for score, _ in ranked)
    winners = [name for score, name in ranked if score == best]
    return winners[0] if len(winners) == 1 else None


class TimelinePlanner:
    """Recognize timeline questions only when their columns resolve safely."""

    PERSON_PATTERNS = [
        (110, r"\b(person|employee|worker|staff|driver|user|agent) (id|key|code)\b"),
        (100, r"\b(person|individual|insan|traveler|traveller)\b"),
        (90, r"\b(employee|worker|staff|driver|user|agent)\b"),
        (80, r"\b(person|employee|worker|staff|driver|user|agent) name\b"),
    ]
    LOCATION_PATTERNS = [
        (100, r"\b(location|place|site|city|address)\b"),
    ]

    @classmethod
    def build_if_applicable(
        cls, question: str, file_id: str, profile: Dict[str, Any], *, max_people: int = 1000
    ) -> Optional[AnalysisPlan]:
        lowered = question.lower()
        if not any(term in lowered for term in TIMELINE_TERMS):
            return None

        columns = profile.get("columns", [])
        identity_columns = [
            column for column in columns
            if column.get("role") in {"identifier", "dimension", "text"}
            or column.get("inferred_type") == "string"
        ]
        person = _ranked_column(identity_columns, cls.PERSON_PATTERNS)
        if not person:
            return None

        timestamps = _timestamp_columns(profile)
        start = _ranked_column(timestamps, [(110, r"\b(start|begin|check ?in|clock ?in|from)\b")])
        end = _ranked_column(timestamps, [(110, r"\b(end|finish|check ?out|clock ?out|to)\b")])
        if start or end:
            if not (start and end) or start == end:
                return None
            mode = "interval"
            selected_time_cols = (start, end)
        else:
            explicit_times = [
                str(column["name"]) for column in timestamps
                if str(column["name"]).lower() in lowered
                or str(column["name"]).lower().replace("_", " ") in lowered
            ]
            selected_time = explicit_times[0] if len(explicit_times) == 1 else None
            if selected_time:
                mode = "events"
                selected_time_cols = (selected_time,)
            elif len(timestamps) == 1:
                mode = "events"
                selected_time_cols = (str(timestamps[0]["name"]),)
            else:
                # Two unnamed timestamp columns could mean event times or interval bounds.
                return None

        location = _ranked_column(columns, cls.LOCATION_PATTERNS)
        if not location:
            location = None
        latitude = _ranked_column(columns, [(120, r"^(latitude|lat)$")])
        longitude = _ranked_column(columns, [(120, r"^(longitude|lon|lng)$")])
        has_location_signal = any(
            re.search(pattern, str(column.get("name", "")).lower().replace("_", " ").replace("-", " "))
            for column in columns for _, pattern in cls.LOCATION_PATTERNS
        )
        if has_location_signal and not location and not (latitude and longitude):
            return None
        fields = [person, *selected_time_cols]
        if location:
            fields.append(location)
        if latitude and longitude:
            fields.extend([latitude, longitude])
        fields = list(dict.fromkeys(fields))
        if len(file_id) == 0:
            return None

        dataset = DatasetRef(file_id=file_id, alias="ds_1")
        p_expr = f"CAST(src.{_quoted(person)} AS VARCHAR)"
        time_exprs = [f"TRY_CAST(CAST(src.{_quoted(name)} AS VARCHAR) AS TIMESTAMPTZ)" for name in selected_time_cols]
        valid_person = f"src.{_quoted(person)} IS NOT NULL AND trim(CAST(src.{_quoted(person)} AS VARCHAR)) <> ''"
        location_expr = f"lower(trim(CAST(src.{_quoted(location)} AS VARCHAR)))" if location else None
        if not location_expr and latitude and longitude:
            location_expr = (
                f"concat(round(TRY_CAST(src.{_quoted(latitude)} AS DOUBLE), 5)::VARCHAR, ',', "
                f"round(TRY_CAST(src.{_quoted(longitude)} AS DOUBLE), 5)::VARCHAR)"
            )

        if mode == "events":
            event_time = time_exprs[0]
            valid_rows = f"{valid_person} AND {event_time} IS NOT NULL"
            conflict_count = "0"
            if location_expr:
                conflict_time = f"TRY_CAST(CAST(c.{_quoted(selected_time_cols[0])} AS VARCHAR) AS TIMESTAMPTZ)"
                conflict_location = (
                    f"lower(trim(CAST(c.{_quoted(location)} AS VARCHAR)))" if location else
                    f"concat(round(TRY_CAST(c.{_quoted(latitude)} AS DOUBLE), 5)::VARCHAR, ',', round(TRY_CAST(c.{_quoted(longitude)} AS DOUBLE), 5)::VARCHAR)"
                )
                conflict_count = (
                    f"(SELECT count(*) FROM (SELECT {conflict_time} AS conflict_time "
                    f"FROM \"ds_1\" AS c WHERE CAST(c.{_quoted(person)} AS VARCHAR) = {p_expr} "
                    f"AND {conflict_time} IS NOT NULL AND {'c.' + _quoted(location) + ' IS NOT NULL' if location else 'c.' + _quoted(latitude) + ' IS NOT NULL AND c.' + _quoted(longitude) + ' IS NOT NULL'} "
                    f"GROUP BY {conflict_time} HAVING count(DISTINCT {conflict_location}) > 1) AS conflicts)"
                )
            speed_threshold = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:km\s*/\s*h|kmph|kph)\b", lowered)
            speed_threshold_kmh = float(speed_threshold.group(1)) if speed_threshold else None
            max_speed = "NULL::DOUBLE"
            over_threshold = "NULL::BIGINT"
            if latitude and longitude:
                lat = f"TRY_CAST(g.{_quoted(latitude)} AS DOUBLE)"
                lon = f"TRY_CAST(g.{_quoted(longitude)} AS DOUBLE)"
                t = f"TRY_CAST(CAST(g.{_quoted(selected_time_cols[0])} AS VARCHAR) AS TIMESTAMPTZ)"
                legs = (
                    f"SELECT {t} AS event_time, {lat} AS lat, {lon} AS lon, "
                    f"lag({t}) OVER (ORDER BY {t}) AS previous_time, "
                    f"lag({lat}) OVER (ORDER BY {t}) AS previous_lat, "
                    f"lag({lon}) OVER (ORDER BY {t}) AS previous_lon "
                    f"FROM \"ds_1\" AS g WHERE CAST(g.{_quoted(person)} AS VARCHAR) = {p_expr} "
                    f"AND {t} IS NOT NULL AND {lat} BETWEEN -90 AND 90 AND {lon} BETWEEN -180 AND 180"
                )
                delta = (
                    "6371.0088 * 2 * asin(sqrt("
                    "power(sin(radians(lat - previous_lat) / 2), 2) + "
                    "cos(radians(previous_lat)) * cos(radians(lat)) * "
                    "power(sin(radians(lon - previous_lon) / 2), 2)))"
                )
                speed = f"({delta}) / (date_diff('microseconds', previous_time, event_time) / 3600000000.0)"
                speed_rows = f"SELECT {speed} AS required_speed_kmh FROM ({legs}) AS ordered_legs WHERE previous_time IS NOT NULL AND event_time > previous_time"
                max_speed = f"(SELECT max(required_speed_kmh) FROM ({speed_rows}) AS speed_legs)"
                if speed_threshold_kmh is not None:
                    over_threshold = f"(SELECT count(*) FROM ({speed_rows}) AS speed_legs WHERE required_speed_kmh > {speed_threshold_kmh})"
            sql = (
                f"SELECT {p_expr} AS person, count(*) AS event_count, "
                f"min({event_time}) AS first_observed, max({event_time}) AS last_observed, "
                f"round(date_diff('microseconds', min({event_time}), max({event_time})) / 3600000000.0, 3) AS elapsed_span_hours, "
                f"NULL::DOUBLE AS active_hours, "
                f"'elapsed span only: point events do not establish active or travel time' AS duration_semantics, "
                f"{conflict_count} AS simultaneous_location_conflict_count, "
                f"{max_speed} AS max_required_travel_speed_kmh, {over_threshold} AS travel_legs_over_threshold, "
                f"count(DISTINCT {p_expr}) OVER () AS total_people "
                f"FROM \"ds_1\" AS src WHERE {valid_rows} GROUP BY src.{_quoted(person)} "
                f"ORDER BY person LIMIT {max_people}"
            )
        else:
            start_expr, end_expr = time_exprs
            valid_rows = f"{valid_person} AND {start_expr} IS NOT NULL AND {end_expr} IS NOT NULL AND {end_expr} >= {start_expr}"
            if location:
                loc_a = f"lower(trim(CAST(a.{_quoted(location)} AS VARCHAR)))"
                loc_b = f"lower(trim(CAST(b.{_quoted(location)} AS VARCHAR)))"
                loc_diff = f"{loc_a} <> {loc_b}"
            elif latitude and longitude:
                loc_a = f"concat(round(TRY_CAST(a.{_quoted(latitude)} AS DOUBLE), 5)::VARCHAR, ',', round(TRY_CAST(a.{_quoted(longitude)} AS DOUBLE), 5)::VARCHAR)"
                loc_b = f"concat(round(TRY_CAST(b.{_quoted(latitude)} AS DOUBLE), 5)::VARCHAR, ',', round(TRY_CAST(b.{_quoted(longitude)} AS DOUBLE), 5)::VARCHAR)"
                loc_diff = f"{loc_a} <> {loc_b}"
            else:
                loc_diff = "FALSE"
            overlap_conflict = (
                f"EXISTS (SELECT 1 FROM \"ds_1\" AS a JOIN \"ds_1\" AS b "
                f"ON CAST(a.{_quoted(person)} AS VARCHAR) = CAST(b.{_quoted(person)} AS VARCHAR) "
                f"AND CAST(a.{_quoted(person)} AS VARCHAR) = {p_expr} "
                f"AND TRY_CAST(CAST(a.{_quoted(start)} AS VARCHAR) AS TIMESTAMPTZ) < TRY_CAST(CAST(b.{_quoted(end)} AS VARCHAR) AS TIMESTAMPTZ) "
                f"AND TRY_CAST(CAST(b.{_quoted(start)} AS VARCHAR) AS TIMESTAMPTZ) < TRY_CAST(CAST(a.{_quoted(end)} AS VARCHAR) AS TIMESTAMPTZ) "
                f"AND {loc_diff})"
            )
            normalized_start = f"TRY_CAST(CAST({_quoted(start)} AS VARCHAR) AS TIMESTAMPTZ)"
            normalized_end = f"TRY_CAST(CAST({_quoted(end)} AS VARCHAR) AS TIMESTAMPTZ)"
            active_hours = (
                f"(SELECT round(sum(date_diff('microseconds', merged_start, merged_end)) / 3600000000.0, 3) FROM ("
                f"SELECT person_key, min(interval_start) AS merged_start, max(interval_end) AS merged_end FROM ("
                f"SELECT person_key, interval_start, interval_end, sum(CASE WHEN prior_end IS NULL OR interval_start > prior_end THEN 1 ELSE 0 END) "
                f"OVER (PARTITION BY person_key ORDER BY interval_start, interval_end ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS island_id FROM ("
                f"SELECT CAST({_quoted(person)} AS VARCHAR) AS person_key, {normalized_start} AS interval_start, {normalized_end} AS interval_end, "
                f"max({normalized_end}) OVER (PARTITION BY CAST({_quoted(person)} AS VARCHAR) ORDER BY {normalized_start}, {normalized_end} "
                f"ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS prior_end FROM \"ds_1\" WHERE {valid_person} "
                f"AND {normalized_start} IS NOT NULL AND {normalized_end} IS NOT NULL AND {normalized_end} >= {normalized_start}) AS sorted_intervals) AS marked_intervals "
                f"GROUP BY person_key, island_id) AS merged_intervals WHERE person_key = {p_expr})"
            )
            sql = (
                f"SELECT {p_expr} AS person, count(*) AS interval_count, min({start_expr}) AS first_observed, "
                f"max({end_expr}) AS last_observed, round(date_diff('microseconds', min({start_expr}), max({end_expr})) / 3600000000.0, 3) AS elapsed_span_hours, "
                f"{active_hours} AS active_hours, 'union of explicit start/end intervals' AS duration_semantics, "
                f"{overlap_conflict} AS overlapping_location_conflict, count(DISTINCT {p_expr}) OVER () AS total_people "
                f"FROM \"ds_1\" AS src WHERE {valid_rows} GROUP BY src.{_quoted(person)} ORDER BY person LIMIT {max_people}"
            )

        return AnalysisPlan(
            intent="timeline_consistency",
            result_shape="timeline",
            question=question,
            datasets=[dataset],
            requested_concepts=fields,
            limit=max_people,
            sql_query=sql,
            skills=[
                "person_timeline", f"timeline_mode:{mode}",
                f"timeline_has_location:{str(bool(location)).lower()}",
                f"timeline_has_coordinates:{str(bool(latitude and longitude)).lower()}",
                f"timeline_speed_threshold_kmh:{speed_threshold_kmh if mode == 'events' and latitude and longitude and speed_threshold else ''}",
            ],
        )
