import re
from typing import List, Set
from app.core.exceptions import ExecutionError

# Keywords strictly forbidden in analysis queries (case-insensitive)
FORBIDDEN_KEYWORDS: Set[str] = {
    "ATTACH", "DETACH", "COPY", "INSTALL", "LOAD", "PRAGMA",
    "EXPORT", "IMPORT", "CALL", "EXEC", "EXECUTE", "SYSTEM",
    "DROP", "ALTER", "TRUNCATE", "INSERT", "UPDATE", "DELETE",
    "CREATE", "REPLACE", "GRANT", "REVOKE", "SHUTDOWN", "CHECKPOINT"
}

# Functions forbidden from execution to protect host isolation
FORBIDDEN_FUNCTIONS: Set[str] = {
    "READ_CSV", "READ_CSV_AUTO", "READ_PARQUET", "READ_JSON",
    "READ_JSON_AUTO", "READ_BLOB", "SCAN_PARQUET", "GLOB",
    "SYSTEM", "SHELL", "GETENV", "ENV"
}

class SQLSanitizer:
    @staticmethod
    def validate_sql(sql: str, allowed_aliases: List[str]) -> None:
        """
        Validates SQL against injection attacks, DDL/DML, and filesystem access.
        Enforces Master Plan Mode A/B safe execution constraints.
        """
        if not sql or not sql.strip():
            raise ExecutionError("Query is empty.")

        cleaned = sql.strip()

        # 1. Reject multiple statements (prevent SQL injection chaining via ;)
        if ";" in cleaned.rstrip(";"):
            raise ExecutionError(
                "Multiple statements detected in analytical query.",
                details={"violation": "SEMICOLON_NOT_ALLOWED"}
            )

        # 2. Must start with SELECT or WITH
        first_token = cleaned.split()[0].upper()
        if first_token not in ["SELECT", "WITH"]:
            raise ExecutionError(
                f"Invalid statement type '{first_token}'. Only read-only SELECT queries are permitted.",
                details={"violation": "INVALID_STATEMENT_TYPE"}
            )

        # 3. Check for forbidden keywords using regex word boundary
        upper_sql = cleaned.upper()
        for kw in FORBIDDEN_KEYWORDS:
            pattern = rf"\b{kw}\b"
            if re.search(pattern, upper_sql):
                raise ExecutionError(
                    f"Forbidden keyword '{kw}' detected in analytical query.",
                    details={"violation": "FORBIDDEN_KEYWORD", "keyword": kw}
                )

        # 4. Check for forbidden functions
        for fn in FORBIDDEN_FUNCTIONS:
            pattern = rf"\b{fn}\s*\("
            if re.search(pattern, upper_sql):
                raise ExecutionError(
                    f"Forbidden function '{fn}()' detected in analytical query.",
                    details={"violation": "FORBIDDEN_FUNCTION", "function": fn}
                )

        # 5. Check table references
        # Ensure that table aliases referenced in FROM / JOIN match the allowed dataset aliases
        from_join_pattern = r"(?:FROM|(?:LEFT|RIGHT|FULL|INNER|CROSS|OUTER)?\s*JOIN)\s+[\"']?([a-zA-Z0-9_]+)[\"']?"
        found_tables = re.findall(from_join_pattern, upper_sql)
        upper_allowed = {a.upper() for a in allowed_aliases}
        for tbl in found_tables:
            if tbl not in upper_allowed and tbl not in ["SELECT", "UNNEST", "GENERATE_SERIES"]:
                raise ExecutionError(
                    f"Unauthorized table reference '{tbl}' in query. Allowed datasets: {allowed_aliases}",
                    details={"violation": "UNAUTHORIZED_TABLE", "table": tbl}
                )
