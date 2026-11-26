from typing import Tuple, List, Any
from app.ai.planning.schemas import AnalysisPlan, Condition

def escape_identifier(name: str) -> str:
    # Wrap column/table identifiers in double quotes and escape internal quotes
    clean = name.replace('"', '""')
    return f'"{clean}"'

class QueryCompiler:
    @staticmethod
    def compile_filters(filters: List[Condition]) -> Tuple[str, List[Any]]:
        params: List[Any] = []
        where_parts = []
        for cond in filters:
            col_id = escape_identifier(cond.column)
            op = cond.operator.lower()

            if op == "equals":
                where_parts.append(f"{col_id} = ?")
                params.append(cond.value)
            elif op == "not_equals":
                where_parts.append(f"{col_id} != ?")
                params.append(cond.value)
            elif op == "greater_than":
                where_parts.append(f"{col_id} > ?")
                params.append(cond.value)
            elif op == "less_than":
                where_parts.append(f"{col_id} < ?")
                params.append(cond.value)
            elif op == "greater_than_or_equal":
                where_parts.append(f"{col_id} >= ?")
                params.append(cond.value)
            elif op == "less_than_or_equal":
                where_parts.append(f"{col_id} <= ?")
                params.append(cond.value)
            elif op == "contains":
                where_parts.append(f"CAST({col_id} AS VARCHAR) ILIKE ?")
                params.append(f"%{cond.value}%")
            elif op == "not_contains":
                where_parts.append(f"CAST({col_id} AS VARCHAR) NOT ILIKE ?")
                params.append(f"%{cond.value}%")
            elif op in {"in", "not_in"} and isinstance(cond.value, (list, tuple)):
                if not cond.value:
                    raise ValueError(f"Filter '{op}' requires at least one value.")
                placeholders = ", ".join(["?"] * len(cond.value))
                keyword = "IN" if op == "in" else "NOT IN"
                where_parts.append(f"{col_id} {keyword} ({placeholders})")
                params.extend(cond.value)
            elif op == "is_null":
                where_parts.append(f"{col_id} IS NULL")
            elif op == "is_not_null":
                where_parts.append(f"{col_id} IS NOT NULL")
            elif op == "has_external_recipient":
                dom_str = f"@{str(cond.value).lstrip('@').lower()}" if cond.value else "@"
                where_parts.append(
                    f"({col_id} IS NOT NULL AND len(list_filter(str_split(CAST({col_id} AS VARCHAR), ?), x -> NOT (trim(LOWER(x)) LIKE ?))) > 0)"
                )
                params.extend([";", f"%{dom_str}"])
            else:
                raise ValueError(f"Unsupported filter operator: {cond.operator}")

        return (" WHERE " + " AND ".join(where_parts)) if where_parts else "", params

    @staticmethod
    def compile(plan: AnalysisPlan) -> Tuple[str, List[Any]]:
        params: List[Any] = []

        # 1. FROM & JOIN clauses
        if not plan.datasets:
            raise ValueError("No dataset specified.")
            
        primary = plan.datasets[0]
        from_clause = f'{escape_identifier(primary.alias)}'
        
        if plan.joins:
            for join in plan.joins:
                j_type = join.join_type.upper()
                from_clause += f' {j_type} JOIN {escape_identifier(join.right_dataset)} ON {escape_identifier(join.left_dataset)}.{escape_identifier(join.left_column)} = {escape_identifier(join.right_dataset)}.{escape_identifier(join.right_column)}'

        # 2. SELECT & AGGREGATE expressions
        select_parts = []
        
        # If group by columns present, select them
        for g_col in plan.group_by:
            select_parts.append(escape_identifier(g_col))

        # Add aggregations
        for agg in plan.aggregations:
            fn = agg.function.upper()
            if fn in ("COUNT_NONZERO", "COUNT_ENTRIES"):
                col_id = escape_identifier(agg.column or "*")
                alias_name = agg.alias or f"{agg.column or 'entries'}_entries"
                select_parts.append(f"COUNT(*) FILTER (WHERE {col_id} IS NOT NULL AND {col_id} <> 0) AS {escape_identifier(alias_name)}")
                continue

            is_distinct = agg.distinct or fn in ("COUNT_DISTINCT", "DISTINCT_COUNT")
            if fn in ("COUNT_DISTINCT", "DISTINCT_COUNT"):
                if not agg.column or agg.column == "*":
                    raise ValueError("count_distinct requires a column.")
                fn = "COUNT"

            if fn == "COUNT":
                if not agg.column or agg.column == "*":
                    col_expr = "*"
                elif is_distinct:
                    col_expr = f"DISTINCT {escape_identifier(agg.column)}"
                else:
                    col_expr = escape_identifier(agg.column)
            elif is_distinct:
                col_expr = f"DISTINCT {escape_identifier(agg.column)}"
            else:
                col_expr = escape_identifier(agg.column)
                
            alias_name = agg.alias or f"{agg.function.lower()}_{agg.column or 'all'}"

            filter_clause = ""
            if agg.filter_condition:
                cond_sql, cond_params = QueryCompiler.compile_filters([agg.filter_condition])
                if cond_sql.startswith(" WHERE "):
                    filter_clause = f" FILTER (WHERE {cond_sql[7:]})"
                    params.extend(cond_params)

            select_parts.append(f"{fn}({col_expr}){filter_clause} AS {escape_identifier(alias_name)}")

        # If no group_by and no aggregations, select *
        if not select_parts:
            select_parts.append("*")

        select_clause = ", ".join(select_parts)

        # 3. WHERE clause
        where_clause, filter_params = QueryCompiler.compile_filters(plan.filters)
        params = filter_params + params

        # 4. GROUP BY clause
        group_clause = ""
        if plan.group_by:
            group_clause = " GROUP BY " + ", ".join([escape_identifier(c) for c in plan.group_by])

        # 4b. HAVING clause
        having_clause = ""
        if plan.having:
            h_parts = []
            for cond in plan.having:
                col_id = escape_identifier(cond.column)
                op = cond.operator.lower()
                if op == "equals":
                    h_parts.append(f"{col_id} = ?")
                    params.append(cond.value)
                elif op == "not_equals":
                    h_parts.append(f"{col_id} != ?")
                    params.append(cond.value)
                elif op == "greater_than":
                    h_parts.append(f"{col_id} > ?")
                    params.append(cond.value)
                elif op == "less_than":
                    h_parts.append(f"{col_id} < ?")
                    params.append(cond.value)
                elif op == "greater_than_or_equal":
                    h_parts.append(f"{col_id} >= ?")
                    params.append(cond.value)
                elif op == "less_than_or_equal":
                    h_parts.append(f"{col_id} <= ?")
                    params.append(cond.value)
                elif op == "is_null":
                    h_parts.append(f"{col_id} IS NULL")
                elif op == "is_not_null":
                    h_parts.append(f"{col_id} IS NOT NULL")
                else:
                    raise ValueError(f"Unsupported having operator: {cond.operator}")
            if h_parts:
                having_clause = " HAVING " + " AND ".join(h_parts)

        # 5. ORDER BY clause
        order_clause = ""
        if plan.sort:
            order_items = []
            for s in plan.sort:
                direction = "ASC" if s.ascending else "DESC"
                order_items.append(f"{escape_identifier(s.column)} {direction}")
            order_clause = " ORDER BY " + ", ".join(order_items)
        elif plan.aggregations and plan.group_by:
            # Default sort by first aggregation descending
            first_agg_alias = plan.aggregations[0].alias or f"{plan.aggregations[0].function.lower()}_{plan.aggregations[0].column or 'all'}"
            order_clause = f" ORDER BY {escape_identifier(first_agg_alias)} DESC"

        # 6. LIMIT clause
        limit_clause = f" LIMIT {plan.limit}" if plan.limit else ""

        sql = f"SELECT {select_clause} FROM {from_clause}{where_clause}{group_clause}{having_clause}{order_clause}{limit_clause}"
        return sql, params
