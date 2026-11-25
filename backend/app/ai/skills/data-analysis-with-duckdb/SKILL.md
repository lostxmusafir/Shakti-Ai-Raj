---
name: data-analysis-with-duckdb
description: "High-performance analytical SQL query planning and deterministic execution on tabular datasets (CSV, Parquet, Excel) using DuckDB."
category: analytics
risk: safe
source: "https://mcpmarket.com/tools/skills/data-analysis-with-duckdb"
source_type: external
date_added: "2026-11-24"
tags: ["duckdb", "sql", "analytics", "parquet", "csv", "data-analysis", "tabular"]
tools: ["duckdb", "query-compiler", "validator", "verifier"]
---

# Data Analysis with DuckDB AI Skill Guide

## Overview & Engine Architecture
DuckDB is an embedded, columnar analytical SQL database engine optimized for fast, complex analytical queries (OLAP) directly on local tabular files (CSV, Parquet, and Excel). In the Universal AI Analyst system, the `data-analysis-with-duckdb` skill equips the query planner to formulate structured, safe, deterministic analytical execution plans for tabular data without copying large datasets into memory or bypassing core governance.

### Architectural Pipeline & Execution Lifecycle
The skill guides query formulation, ensuring all operations flow through the project's strict validation and verification pipeline:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Universal AI Analyst Pipeline                        │
│                                                                         │
│  1. User Question (Natural Language, Hindi, Hinglish, English)          │
│       │                                                                 │
│  2. Skill Selection & Routing (SkillRegistry.route)                     │
│       │  Activates 'data-analysis-with-duckdb' for tabular tasks        │
│       ▼                                                                 │
│  3. Structured AnalysisPlan Generation                                  │
│       │  Datasets, Filters, GroupBy, Aggregations, Having, Joins, Sort  │
│       ▼                                                                 │
│  4. Security & Schema Validation (PlanValidator + SQLSanitizer)        │
│       │  Rejects forbidden keywords (DROP/INSTALL/ATTACH), UDFs, path IO│
│       ▼                                                                 │
│  5. Query Compilation (QueryCompiler)                                   │
│       │  Translates structured plan to parameterized SQL                │
│       ▼                                                                 │
│  6. Isolated DuckDB Engine Execution (DuckDBEngine)                     │
│       │  In-memory (:memory:), memory_limit='512MB', threads=2          │
│       │  Locks down environment: SET enable_external_access = false    │
│       ▼                                                                 │
│  7. Multi-Gate Verification (ResultVerifier)                            │
│       │  V1_EXECUTION, V2_SANITY, V3_RECOMPUTE, V4_LINEAGE, V8_PRIVACY  │
│       ▼                                                                 │
│  8. Verified Response & Row Provenance                                  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Operational Capabilities & Planner Directives

1. **Direct Native Scanning over In-Memory Bloat**:
   - For CSV and Parquet files, leverage DuckDB's native columnar scanner (`read_csv_auto`, `read_parquet`) registered as dataset aliases (`ds_1`, `ds_2`).
   - Do NOT load multi-million row datasets into Python Pandas dataframes unnecessarily.

2. **Columnar Aggregation & Grouping**:
   - Standard analytical aggregations: `COUNT`, `SUM`, `AVG`, `MIN`, `MAX`, `MEDIAN`.
   - Distinct counts: `COUNT(DISTINCT column)` for unique entity counts.
   - Multi-column `GROUP BY` for segmented analysis (e.g. `Region`, `Department`, `ProductCategory`).
   - Group filtering via `HAVING` (e.g. `HAVING COUNT(*) >= 20`).

3. **Top-N and Ranking**:
   - Explicit ordering via `SortRule` descending by aggregate metric alias with bounded `limit` (e.g., Top 5, Top 10).
   - Window ranking functions (`DENSE_RANK()`, `ROW_NUMBER()`, `RANK()`) when comparing entity standings within cohorts.

4. **Multi-Dataset Joins & Anti-Joins**:
   - Standard relational joins (`INNER`, `LEFT`, `RIGHT`, `OUTER`).
   - Anti-joins for dataset reconciliation (e.g. finding employees in HR master but missing from payroll).

5. **Conditional Aggregation & CASE Expressions**:
   - Use SQL `FILTER (WHERE ...)` or `SUM(CASE WHEN ... THEN 1 ELSE 0 END)` for segmented count and ratio metrics without multiple full-table scans.

6. **Date Truncation & Temporal Analysis**:
   - Use `date_trunc('month', ts)`, `date_trunc('year', ts)`, or date extraction for trend analysis and monthly/quarterly comparisons.

---

## Complex Analytical Patterns (Hard Question Guide)

### 1. Cohort Aggregation with Threshold Filtering
*Question*: *"Among airlines with at least 20 bookings, which one has the highest cancellation rate?"*
*Plan Pattern*:
- Group by `airline`.
- Aggregations: `COUNT(*) AS total_bookings`, `SUM(CASE WHEN status = 'Cancelled' THEN 1 ELSE 0 END) AS cancelled_bookings`.
- Having condition: `total_bookings >= 20`.
- Sort: `cancelled_bookings * 1.0 / total_bookings DESC` Limit 1.

### 2. Segmented Burden & Averages with Overdue Filters
*Question*: *"Which city has the highest average EMI burden among customers with overdue loans?"*
*Plan Pattern*:
- Filter: `loan_status = 'Overdue'`.
- Group by: `city`.
- Aggregate: `AVG(emi_amount) AS avg_emi`.
- Sort: `avg_emi DESC` Limit 1.

### 3. Temporal Period Comparison (Q1 vs Q2 Percentage Change)
*Question*: *"Compare Q1 vs Q2 revenue and show percentage change."*
*Plan Pattern*:
- Conditional aggregation over date quarters:
  - `SUM(CASE WHEN quarter = 'Q1' THEN revenue ELSE 0 END) AS q1_rev`
  - `SUM(CASE WHEN quarter = 'Q2' THEN revenue ELSE 0 END) AS q2_rev`
- Calculated difference and percentage ratio.

### 4. Cross-Dataset Anti-Join Reconciliation
*Question*: *"Find employees present in payroll but missing from HR master."*
*Plan Pattern*:
- Datasets: `payroll` (`ds_1`) and `hr_master` (`ds_2`).
- Relational Join: `ds_1 ANTI JOIN ds_2 ON ds_1.employee_id = ds_2.employee_id` (or `LEFT JOIN` with `WHERE ds_2.employee_id IS NULL`).
- Output: List of missing employees.

---

## Security Boundaries & Safety Guarantees

1. **Strictly Read-Only Execution**:
   - No DDL or DML statements (`CREATE`, `DROP`, `INSERT`, `UPDATE`, `DELETE`, `ALTER`, `TRUNCATE`).
   - Only `SELECT` and `WITH` statements are permitted.
2. **Locked Down External Access**:
   - DuckDB connection executes `SET enable_external_access = false` immediately after authorized dataset registration.
   - No arbitrary filesystem reads/writes (`ATTACH`, `DETACH`, `COPY`, `EXPORT`, `IMPORT`, `READ_BLOB`, `GLOB`).
3. **No Dynamic Extension Loading**:
   - Runtime `INSTALL` and `LOAD` are strictly prohibited.
4. **Hard Resource Limits**:
   - In-memory execution (`:memory:`) with `memory_limit = '512MB'` and `threads = 2`.
   - Results bounded by default limit (max 10,000 rows).
5. **Tenant & Lineage Isolation**:
   - Only files authorized in the caller's unit context are registered.
   - Result lineage and file hashes are audited.

---

## Interoperability with Other Skills

- **`microsoft-excel`**: For Excel workbooks (`.xlsx`), the Excel skill handles multi-sheet inspection, formula discovery, and metadata profiling. Tabular queries then execute deterministically through DuckDB.
- **`data-quality-audit`**: Pre-audit checks null counts, duplicate records, and type anomalies before running complex analytical calculations.
- **`time-series-analysis`**: Directs date grouping and temporal windowing for period-over-period comparisons.
- **`metric-reconciliation`**: Validates independent aggregate totals against reported numbers (Verification Gate V3).

---

## Technical Troubleshooting Matrix

| Issue & Failure Signature | Root Cause Analysis | Diagnostic & Resolution Pathway |
| :--- | :--- | :--- |
| **`UNAUTHORIZED_TABLE`** | Query references table alias outside registered datasets (`ds_1`, `ds_2`). | Check dataset aliases in AnalysisPlan; ensure aliases match registered files. |
| **`FORBIDDEN_KEYWORD`** | Query contains administrative, DDL, or extension keyword (`ATTACH`, `INSTALL`, etc.). | Remove forbidden keyword. Rely strictly on read-only SELECT expressions. |
| **`Grouped values do not reconcile`** | Sum of grouped aggregates diverges from overall total. | Normal for `COUNT(DISTINCT)` or limit-truncated queries; flagged as not applicable in V3. |
| **`Out of Memory (512MB limit)`** | Query attempts massive cross-join without filter pushdown. | Add join conditions (`ON left.id = right.id`) and filter conditions to prune rows early. |

---

## Agent Operational Directive
> **MANDATORY**: Always formulate analytical requests as structured `AnalysisPlan` objects. Never emit raw SQL snippets that bypass `PlanValidator` or `SQLSanitizer`. Leverage DuckDB's native columnar engine for deterministic computation, and verify every numeric aggregate against source data.
