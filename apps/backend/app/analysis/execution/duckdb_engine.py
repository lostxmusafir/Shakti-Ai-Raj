import os
import time
import hashlib
from typing import Dict, Any, List
import duckdb
from app.core.exceptions import ExecutionError
from app.ai.planning.schemas import AnalysisPlan
from app.analysis.execution.compiler import QueryCompiler
from app.models.file import StoredFile

class DuckDBEngine:
    @staticmethod
    def execute(
        plan: AnalysisPlan,
        files_map: Dict[str, StoredFile],
        file_paths_map: Dict[str, str]
    ) -> Dict[str, Any]:
        start_time = time.time()
        
        # 1. Compile plan to SQL & params
        sql, params = QueryCompiler.compile(plan)
        query_hash = hashlib.sha256(f"{sql}_{params}".encode()).hexdigest()

        # 2. Spin up isolated in-memory DuckDB connection
        con = duckdb.connect(database=":memory:")
        con.execute("SET memory_limit = '512MB'")
        con.execute("SET threads = 2")

        try:
            # 3. Register each dataset as a temporary view/table
            for ds in plan.datasets:
                file_path = file_paths_map[ds.file_id]
                alias = ds.alias
                ext = os.path.splitext(file_path)[1].lower()
                
                if ext == ".csv":
                    # Register CSV view
                    con.execute(f"CREATE VIEW \"{alias}\" AS SELECT * FROM read_csv_auto('{file_path}')")
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

            # 4. Execute query with parameterized inputs
            result_cursor = con.execute(sql, params)
            column_names = [desc[0] for desc in result_cursor.description]
            raw_rows = result_cursor.fetchall()
            
            # Format rows as list of dicts
            rows = []
            for r in raw_rows:
                row_dict = {}
                for idx, col_name in enumerate(column_names):
                    val = r[idx]
                    # Ensure clean JSON serializability
                    if hasattr(val, "isoformat"):
                        val = val.isoformat()
                    elif isinstance(val, (float,)) and (val != val):  # NaN
                        val = None
                    row_dict[col_name] = val
                rows.append(row_dict)

            execution_duration_ms = round((time.time() - start_time) * 1000, 2)
            result_hash = hashlib.sha256(str(rows).encode()).hexdigest()

            return {
                "columns": column_names,
                "rows": rows,
                "row_count": len(rows),
                "compiled_sql": sql,
                "query_hash": query_hash,
                "result_hash": result_hash,
                "duration_ms": execution_duration_ms,
                "engine": "duckdb"
            }

        except Exception as e:
            raise ExecutionError(f"Engine query execution failed: {str(e)}", details={"sql": sql, "params": params})
        finally:
            con.close()
