from typing import Tuple, List, Any
from app.ai.planning.schemas import AnalysisPlan, Condition

def escape_identifier(name: str) -> str:
    # Wrap column/table identifiers in double quotes and escape internal quotes
    clean = name.replace('"', '""')
    return f'"{clean}"'

class QueryCompiler:
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
            if fn == "COUNT":
                col_expr = "*" if not agg.column or agg.column == "*" else escape_identifier(agg.column)
            elif fn == "MEDIAN":
                col_expr = escape_identifier(agg.column)
            else:
                col_expr = escape_identifier(agg.column)
                
            alias_name = agg.alias or f"{agg.function.lower()}_{agg.column or 'all'}"
            select_parts.append(f"{fn}({col_expr}) AS {escape_identifier(alias_name)}")

        # If no group_by and no aggregations, select *
        if not select_parts:
            select_parts.append("*")

        select_clause = ", ".join(select_parts)

        # 3. WHERE clause
        where_parts = []
        for cond in plan.filters:
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
            elif op == "in" and isinstance(cond.value, (list, tuple)):
                placeholders = ", ".join(["?"] * len(cond.value))
                where_parts.append(f"{col_id} IN ({placeholders})")
                params.extend(cond.value)
            elif op == "not_in" and isinstance(cond.value, (list, tuple)):
                placeholders = ", ".join(["?"] * len(cond.value))
                where_parts.append(f"{col_id} NOT IN ({placeholders})")
                params.extend(cond.value)
            elif op == "is_null":
                where_parts.append(f"{col_id} IS NULL")
            elif op == "is_not_null":
                where_parts.append(f"{col_id} IS NOT NULL")

        where_clause = ""
        if where_parts:
            where_clause = " WHERE " + " AND ".join(where_parts)

        # 4. GROUP BY clause
        group_clause = ""
        if plan.group_by:
            group_clause = " GROUP BY " + ", ".join([escape_identifier(c) for c in plan.group_by])

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

        sql = f"SELECT {select_clause} FROM {from_clause}{where_clause}{group_clause}{order_clause}{limit_clause}"
        return sql, params
