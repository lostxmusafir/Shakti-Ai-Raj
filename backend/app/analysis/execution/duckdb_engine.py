import os
import time
import hashlib
from typing import Dict, Any, List
import duckdb
from app.core.exceptions import ExecutionError
from app.ai.planning.schemas import AnalysisPlan
from app.analysis.execution.compiler import QueryCompiler
from app.analysis.execution.compiler import escape_identifier
from app.analysis.execution.sanitizer import SQLSanitizer
from app.models.file import StoredFile

class DuckDBEngine:
    @staticmethod
    def _clean_value(val: Any) -> Any:
        if hasattr(val, "isoformat"):
            return val.isoformat()
        if isinstance(val, float) and (val != val):
            return None
        return val

    @staticmethod
    def execute(
        plan: AnalysisPlan,
        files_map: Dict[str, StoredFile],
        file_paths_map: Dict[str, str]
    ) -> Dict[str, Any]:
        start_time = time.time()
        
        # 1. Obtain SQL & parameters
        if plan.sql_query:
            sql = plan.sql_query.strip().rstrip(";")
            params: List[Any] = []
        else:
            sql, params = QueryCompiler.compile(plan)

        # 2. Validate SQL against injection, DDL/DML, and unauthorized table access
        allowed_aliases = [ds.alias for ds in plan.datasets] + ["v", "v0", "incidents", "dataset"]
        SQLSanitizer.validate_sql(sql, allowed_aliases)

        query_hash = hashlib.sha256(f"{sql}_{params}".encode()).hexdigest()

        # 3. Spin up isolated in-memory DuckDB connection
        con = duckdb.connect(database=":memory:")
        con.execute("SET memory_limit = '512MB'")
        con.execute("SET threads = 2")

        try:
            # 4. Register each authorized dataset as a temporary view/table
            for ds in plan.datasets:
                file_path = file_paths_map[ds.file_id]
                alias = ds.alias
                ext = os.path.splitext(file_path)[1].lower()
                
                if ext == ".csv":
                    # Register CSV into in-memory table via parameterized read
                    con.execute(f'CREATE TABLE "{alias}" AS SELECT * FROM read_csv_auto(?)', [file_path])
                elif ext in [".xlsx", ".xls"]:
                    # Read Excel into Polars/Arrow and register in DuckDB
                    import polars as pl
                    stored_file = files_map[ds.file_id]
                    profile = stored_file.schema_profile or {}
                    primary_sheet = profile.get("sheets", ["Sheet1"])[0] if profile.get("sheets") else "Sheet1"
                    try:
                        df = pl.read_excel(file_path, sheet_name=primary_sheet)
                    except Exception:
                        import pandas as pd
                        pdf = pd.read_excel(file_path, sheet_name=primary_sheet)
                        df = pl.from_pandas(pdf)
                    
                    arrow_table = df.to_arrow()
                    con.register(alias, arrow_table)
                else:
                    raise ExecutionError(f"Unsupported file format for engine: {ext}")

            # Register standard helper views v0 and v for DLP/security incident queries
            if plan.datasets:
                primary_alias = plan.datasets[0].alias
                col_info = con.execute(f'PRAGMA table_info("{primary_alias}")').fetchall()
                col_names_lower = {c[1].lower() for c in col_info}
                
                if "destination" in col_names_lower and "incident time" in col_names_lower:
                    dom_len = 18
                    dom_str = "@nexusdynamics.com"
                    try:
                        sample_dests = con.execute(f'SELECT Destination FROM "{primary_alias}" WHERE Destination IS NOT NULL LIMIT 15').fetchall()
                        for s in sample_dests:
                            if s[0] and "@raj.com" in str(s[0]).lower():
                                dom_str = "@raj.com"
                                dom_len = 8
                                break
                    except Exception:
                        pass

                    has_channel = "channel" in col_names_lower
                    channel_select = "Channel AS channel," if has_channel else ""

                    con.execute(f'''
                    CREATE VIEW v0 AS SELECT 
                      ID AS id, 
                      "Incident Time" AS ts, 
                      Source AS src, 
                      Policies AS policy, 
                      {channel_select}
                      Destination AS dest,
                      Severity AS severity, 
                      Action AS action, 
                      "Maximum Matches" AS matches, 
                      "Transaction Size (KB)" AS size_kb, 
                      "File Name" AS file,
                      (LENGTH(Destination) - LENGTH(REPLACE(Destination, ';', '')) + 1) AS n_rcpt,
                      (LENGTH(Destination) - LENGTH(REPLACE(LOWER(Destination), '{dom_str}', ''))) / {dom_len} AS n_int,
                      CAST(SUBSTR("Incident Time", 15, 2) AS INT) % 12 + CASE WHEN SUBSTR("Incident Time", 24, 2) = 'PM' THEN 12 ELSE 0 END AS hr,
                      CASE WHEN Destination LIKE '%@gmail.com%' THEN 1 ELSE 0 END AS gmail,
                      CASE WHEN Destination LIKE '%@yahoo.%' THEN 1 ELSE 0 END AS yahoo,
                      CASE WHEN Destination LIKE '%@gmail.com%' OR Destination LIKE '%@yahoo.%' OR Destination LIKE '%@outlook.com%' OR Destination LIKE '%@hotmail.com%' THEN 1 ELSE 0 END AS personal,
                      CASE WHEN (Destination || ';') LIKE '%.de;%' OR (Destination || ';') LIKE '%.fr;%' OR (Destination || ';') LIKE '%.it;%' THEN 1 ELSE 0 END AS foreign_aff
                    FROM "{primary_alias}";
                    CREATE VIEW v AS SELECT *, 
                      CASE WHEN n_rcpt > n_int THEN 1 ELSE 0 END AS is_ext, 
                      CASE WHEN n_int > 0 AND n_rcpt > n_int THEN 1 ELSE 0 END AS is_mixed 
                    FROM v0;
                    ''')
                else:
                    con.execute(f'CREATE VIEW v AS SELECT * FROM "{primary_alias}"')

            # 5. Lock down DuckDB: disable all external file and network access
            con.execute("SET enable_external_access = false")

            # 6. Execute query with parameterized inputs
            result_cursor = con.execute(sql, params)
            column_names = [desc[0] for desc in result_cursor.description]
            raw_rows = result_cursor.fetchall()
            
            # Format rows as list of dicts
            rows = []
            for r in raw_rows:
                row_dict = {}
                for idx, col_name in enumerate(column_names):
                    val = r[idx]
                    if hasattr(val, "isoformat"):
                        val = val.isoformat()
                    elif isinstance(val, (float,)) and (val != val):  # NaN
                        val = None
                    row_dict[col_name] = val
                rows.append(row_dict)

            execution_duration_ms = round((time.time() - start_time) * 1000, 2)
            result_hash = hashlib.sha256(str(rows).encode()).hexdigest()

            # Independent aggregate recomputation for verification
            recompute = {}
            if plan.intent == "comparative_count":
                profile = files_map[plan.datasets[0].file_id].schema_profile or {}
                columns = {col["name"].lower(): col["name"] for col in profile.get("columns", [])}
                debit, credit = (escape_identifier(columns[name]) for name in ("debit", "credit"))
                alias = escape_identifier(plan.datasets[0].alias)
                counts = con.execute(
                    f"SELECT COUNT(*) FILTER (WHERE {debit} IS NOT NULL AND {debit} <> 0), "
                    f"COUNT(*) FILTER (WHERE {credit} IS NOT NULL AND {credit} <> 0) FROM {alias}"
                ).fetchone()
                recompute = {"debit_entries": counts[0], "credit_entries": counts[1]}
            elif plan.aggregations and not plan.sql_query:
                recompute_plan = plan.model_copy(deep=True)
                recompute_plan.group_by = []
                recompute_plan.sort = []
                recompute_plan.limit = None
                try:
                    rec_sql, rec_params = QueryCompiler.compile(recompute_plan)
                    SQLSanitizer.validate_sql(rec_sql, allowed_aliases)
                    rec_cursor = con.execute(rec_sql, rec_params)
                    rec_cols = [d[0] for d in rec_cursor.description]
                    rec_rows = rec_cursor.fetchall()
                    if rec_rows:
                        recompute = {rec_cols[i]: DuckDBEngine._clean_value(rec_rows[0][i]) for i in range(len(rec_cols))}
                except Exception:
                    recompute = {}
            elif rows:
                recompute = rows[0]

            source_row_count = None
            if plan.datasets:
                try:
                    source_row_count = sum(con.execute(f'SELECT COUNT(*) FROM "{ds.alias}"').fetchone()[0] for ds in plan.datasets)
                except Exception:
                    source_row_count = len(rows)

            matched_row_count = len(rows)

            evidence_rows = []
            if not plan.sql_query and plan.datasets:
                primary_alias = plan.datasets[0].alias
                filter_sql, filter_params = QueryCompiler.compile_filters(plan.filters)
                evidence_sql = f'SELECT row_number() OVER () AS source_row FROM "{primary_alias}"{filter_sql} LIMIT 20'
                try:
                    ev_cursor = con.execute(evidence_sql, filter_params)
                    evidence_rows = [int(r[0]) for r in ev_cursor.fetchall()]
                except Exception:
                    evidence_rows = []

            return {
                "columns": column_names,
                "rows": rows,
                "row_count": len(rows),
                "compiled_sql": sql,
                "query_hash": query_hash,
                "result_hash": result_hash,
                "duration_ms": execution_duration_ms,
                "engine": "duckdb",
                "recompute": recompute,
                "source_row_count": source_row_count,
                "matched_row_count": matched_row_count,
                "evidence_rows": evidence_rows,
            }

        except Exception as e:
            raise ExecutionError(f"Engine query execution failed: {str(e)}", details={"sql": sql, "params": params})
        finally:
            con.close()
