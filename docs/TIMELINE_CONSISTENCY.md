# Person timeline consistency checks

## What the analyst does

With one person identifier and either one event timestamp or a named start/end pair, timeline questions use a deterministic DuckDB plan. The plan groups by person and returns observed start/end, elapsed span, and supported location checks. It is read-only and uses only the authorized uploaded file.

- **One timestamp per row:** report first-to-last elapsed span. Do not call that active time or time spent moving.
- **Start and end columns:** merge overlapping intervals before summing active time, so overlaps are not double-counted.
- **One timestamp plus a location/coordinate:** flag distinct locations recorded at the same instant. This is a possible data conflict, not proof of misconduct.
- **Coordinates:** report observed required travel speed between consecutive events. Only compare it to a feasibility limit when the user supplied a speed threshold (for example, `80 km/h`).
- **Several possible timestamp columns:** ask the user which one defines the timeline. Conventional start/end pairs are recognized by their names.
- **Missing location or person/time fields:** do not claim the location conflict check passed. Let the standard planner respond or clarify.

Timezone-naive timestamps follow the DuckDB session timezone and the answer says so. Users should verify the source timezone. The current travel-speed check is for point events; it is not route planning and does not identify the mode of transport.

## Examples

- “For each employee, how many hours passed between first and last location event?”
- “Same person two locations par same timestamp par hai kya?”
- “Find location conflicts and flag travel rates above 80 km/h.”
- “Total active hours between start_time and end_time, without double-counting overlaps.”

Conceptual questions such as “What if someone used a time machine?” remain general chat even with a spreadsheet attached, unless the question anchors itself to sheet timestamps, locations, rows, or records.
