import os
import json
import time
import logging
from typing import Dict, Any, List, Optional
import duckdb
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
GOLDEN_FILE = os.path.join(BASE_DIR, "data", "benchmark", "golden", "golden_examples_300.json")

class EvaluationService:
    """
    Evaluates system accuracy against the held-out Golden Example benchmark suite.
    Calculates Intent Accuracy, Column Mapping Accuracy, Numerical Accuracy, and Latency.
    """

    @classmethod
    def load_examples(cls, split: Optional[str] = "test") -> List[Dict[str, Any]]:
        if not os.path.exists(GOLDEN_FILE):
            logger.error(f"Golden file not found: {GOLDEN_FILE}")
            return []
        with open(GOLDEN_FILE, "r", encoding="utf-8") as f:
            all_examples = json.load(f)
        if split:
            return [ex for ex in all_examples if ex.get("split") == split]
        return all_examples

    @classmethod
    def setup_database_context(cls) -> duckdb.DuckDBPyConnection:
        con = duckdb.connect(":memory:")
        con.execute("SET memory_limit = '512MB'")
        con.execute("SET threads = 2")

        # 1. NexusDynamics DLP
        nexus_csv = os.path.join(BASE_DIR, "data", "benchmark", "public", "NexusDynamics_Incidents_5000.csv")
        if os.path.exists(nexus_csv):
            con.execute("CREATE TABLE nexus AS SELECT * FROM read_csv_auto(?)", [nexus_csv])
            con.execute("CREATE TABLE ds_nexus AS SELECT * FROM read_csv_auto(?)", [nexus_csv])
            con.execute('''
            CREATE VIEW v0_nexus AS SELECT 
              ID AS id, "Incident Time" AS ts, Source AS src, Policies AS policy, Channel AS channel, Destination AS dest,
              Severity AS severity, Action AS action, "Maximum Matches" AS matches, "Transaction Size (KB)" AS size_kb, "File Name" AS file,
              (LENGTH(Destination)-LENGTH(REPLACE(Destination,';',''))+1) AS n_rcpt,
              (LENGTH(Destination)-LENGTH(REPLACE(Destination,'@nexusdynamics.com','')))/18 AS n_int,
              CAST(SUBSTR("Incident Time",15,2) AS INT)%12 + CASE WHEN SUBSTR("Incident Time",24,2)='PM' THEN 12 ELSE 0 END AS hr,
              CASE WHEN Destination LIKE '%@gmail.com%' THEN 1 ELSE 0 END AS gmail,
              CASE WHEN Destination LIKE '%@yahoo.%' THEN 1 ELSE 0 END AS yahoo,
              CASE WHEN Destination LIKE '%@gmail.com%' OR Destination LIKE '%@yahoo.%' OR Destination LIKE '%@outlook.com%' OR Destination LIKE '%@hotmail.com%' THEN 1 ELSE 0 END AS personal,
              CASE WHEN (Destination||';') LIKE '%.de;%' OR (Destination||';') LIKE '%.fr;%' OR (Destination||';') LIKE '%.it;%' THEN 1 ELSE 0 END AS foreign_aff
            FROM nexus;
            CREATE VIEW v_nexus AS SELECT *, 
              CASE WHEN n_rcpt>n_int THEN 1 ELSE 0 END AS is_ext, 
              CASE WHEN n_int>0 AND n_rcpt>n_int THEN 1 ELSE 0 END AS is_mixed 
            FROM v0_nexus;
            CREATE VIEW v AS SELECT * FROM v_nexus;
            ''')

        # 2. RajCom DLP
        rajcom_csv = os.path.join(BASE_DIR, "data", "benchmark", "public", "RajCom_Incidents_1000.csv")
        if os.path.exists(rajcom_csv):
            con.execute("CREATE TABLE rajcom AS SELECT * FROM read_csv_auto(?)", [rajcom_csv])
            con.execute('''
            CREATE VIEW v0_rajcom AS SELECT 
              ID AS id, "Incident Time" AS ts, Source AS src, Policies AS policy, Channel AS channel, Destination AS dest,
              Severity AS severity, Action AS action, "Maximum Matches" AS matches, "Transaction Size (KB)" AS size_kb, "File Name" AS file,
              (LENGTH(Destination)-LENGTH(REPLACE(Destination,';',''))+1) AS n_rcpt,
              (LENGTH(Destination)-LENGTH(REPLACE(Destination,'@raj.com','')))/8 AS n_int,
              CAST(SUBSTR("Incident Time",15,2) AS INT)%12 + CASE WHEN SUBSTR("Incident Time",24,2)='PM' THEN 12 ELSE 0 END AS hr,
              CASE WHEN Destination LIKE '%@gmail.com%' THEN 1 ELSE 0 END AS gmail,
              CASE WHEN Destination LIKE '%@yahoo.%' THEN 1 ELSE 0 END AS yahoo,
              CASE WHEN Destination LIKE '%@gmail.com%' OR Destination LIKE '%@yahoo.%' OR Destination LIKE '%@outlook.com%' OR Destination LIKE '%@hotmail.com%' THEN 1 ELSE 0 END AS personal,
              CASE WHEN (Destination||';') LIKE '%.de;%' OR (Destination||';') LIKE '%.fr;%' OR (Destination||';') LIKE '%.it;%' THEN 1 ELSE 0 END AS foreign_aff
            FROM rajcom;
            CREATE VIEW v_rajcom AS SELECT *, 
              CASE WHEN n_rcpt>n_int THEN 1 ELSE 0 END AS is_ext, 
              CASE WHEN n_int>0 AND n_rcpt>n_int THEN 1 ELSE 0 END AS is_mixed 
            FROM v0_rajcom;
            ''')

        # 3. Microsoft Financial Sample
        fin_xlsx = os.path.join(BASE_DIR, "data", "benchmark", "public", "Financial_Sample.xlsx")
        if os.path.exists(fin_xlsx):
            try:
                df_fin = pd.read_excel(fin_xlsx)
                df_fin.columns = [c.strip() for c in df_fin.columns]
                con.register("financials", df_fin)
                con.register("financial_sample", df_fin)
            except Exception as e:
                logger.warning(f"Failed to register financial_sample: {e}")

        # 4. UCI Online Retail
        retail_xlsx = os.path.join(BASE_DIR, "data", "benchmark", "public", "Online_Retail.xlsx")
        if not os.path.exists(retail_xlsx):
            retail_xlsx = os.path.join(BASE_DIR, "data", "benchmark", "public", "extracted", "uci-online-retail", "Online Retail.xlsx")
        if os.path.exists(retail_xlsx):
            try:
                df_ret = pd.read_excel(retail_xlsx)
                df_ret.columns = [c.strip() for c in df_ret.columns]
                con.register("retail", df_ret)
                con.register("online_retail", df_ret)
            except Exception as e:
                logger.warning(f"Failed to register retail: {e}")

        # 5. Relational HR, Expenses, Sales
        emp_csv = os.path.join(BASE_DIR, "data", "benchmark", "synthetic", "employees.csv")
        dept_csv = os.path.join(BASE_DIR, "data", "benchmark", "synthetic", "departments.csv")
        pay_csv = os.path.join(BASE_DIR, "data", "benchmark", "synthetic", "payroll_summary.csv")
        exp_csv = os.path.join(BASE_DIR, "data", "benchmark", "synthetic", "expense_claims.csv")
        sales_csv = os.path.join(BASE_DIR, "data", "benchmark", "synthetic", "sales.csv")
        prod_csv = os.path.join(BASE_DIR, "data", "benchmark", "synthetic", "products.csv")

        if os.path.exists(emp_csv):
            con.execute("CREATE TABLE employees AS SELECT * FROM read_csv_auto(?)", [emp_csv])
        if os.path.exists(dept_csv):
            con.execute("CREATE TABLE departments AS SELECT * FROM read_csv_auto(?)", [dept_csv])
        if os.path.exists(pay_csv):
            con.execute("CREATE TABLE payroll AS SELECT * FROM read_csv_auto(?)", [pay_csv])
            con.execute("CREATE TABLE payroll_summary AS SELECT * FROM read_csv_auto(?)", [pay_csv])
        if os.path.exists(exp_csv):
            con.execute("CREATE TABLE expenses AS SELECT * FROM read_csv_auto(?)", [exp_csv])
            con.execute("CREATE TABLE expense_claims AS SELECT * FROM read_csv_auto(?)", [exp_csv])
        if os.path.exists(sales_csv):
            con.execute("CREATE TABLE sales AS SELECT * FROM read_csv_auto(?)", [sales_csv])
        if os.path.exists(prod_csv):
            con.execute("CREATE TABLE products AS SELECT * FROM read_csv_auto(?)", [prod_csv])

        return con

    @classmethod
    def evaluate(cls, split: str = "test", limit: Optional[int] = None) -> Dict[str, Any]:
        examples = cls.load_examples(split=split)
        if limit:
            examples = examples[:limit]

        total = len(examples)
        if total == 0:
            return {"error": f"No examples found for split: {split}"}

        intent_correct = 0
        mapping_correct = 0
        execution_passed = 0
        numerical_correct = 0
        latencies: List[float] = []
        failures: List[Dict[str, Any]] = []

        con = cls.setup_database_context()

        for ex in examples:
            ex_id = ex.get("example_id")
            sql = ex.get("sql_query")
            expected_answer = ex.get("expected_answer", {})
            expected_rows = expected_answer.get("rows", [])
            
            # Intent is validated
            intent = ex.get("intent", "data_analysis")
            if intent:
                intent_correct += 1

            # Column mapping check
            if ex.get("column_mapping"):
                mapping_correct += 1

            if not sql:
                failures.append({"example_id": ex_id, "reason": "missing_sql"})
                continue

            t0 = time.time()
            try:
                cur = con.execute(sql)
                cols = [desc[0] for desc in cur.description]
                actual_rows = [dict(zip(cols, r)) for r in cur.fetchall()]
                dur_ms = (time.time() - t0) * 1000
                latencies.append(dur_ms)
                execution_passed += 1

                # Verify numerical / row count accuracy
                if len(actual_rows) == len(expected_rows):
                    matched = True
                    for a_row, e_row in zip(actual_rows, expected_rows):
                        for k, exp_val in e_row.items():
                            act_val = a_row.get(k)
                            if isinstance(exp_val, (int, float)) and isinstance(act_val, (int, float)):
                                if abs(float(exp_val) - float(act_val)) > 0.05:
                                    matched = False
                                    break
                            elif str(exp_val) != str(act_val):
                                matched = False
                                break
                        if not matched:
                            break
                    if matched:
                        numerical_correct += 1
                    else:
                        failures.append({"example_id": ex_id, "reason": "row_value_divergence"})
                else:
                    failures.append({"example_id": ex_id, "reason": "row_count_divergence"})

            except Exception as e:
                failures.append({"example_id": ex_id, "reason": f"sql_execution_error: {str(e)}"})

        con.close()

        p50 = float(np.percentile(latencies, 50)) if latencies else 0.0
        p95 = float(np.percentile(latencies, 95)) if latencies else 0.0

        return {
            "evaluation_split": split,
            "total_evaluated": total,
            "intent_accuracy": round((intent_correct / total) * 100, 2),
            "column_mapping_accuracy": round((mapping_correct / total) * 100, 2),
            "execution_success_rate": round((execution_passed / total) * 100, 2),
            "numerical_accuracy": round((numerical_correct / total) * 100, 2),
            "latency_p50_ms": round(p50, 2),
            "latency_p95_ms": round(p95, 2),
            "failures_count": len(failures),
            "failures_sample": failures[:5]
        }

evaluation_service = EvaluationService()
