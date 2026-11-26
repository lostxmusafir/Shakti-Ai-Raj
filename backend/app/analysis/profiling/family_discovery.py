import re
from typing import Dict, Any, List, Optional, Set
import polars as pl

class RowFamilyDiscovery:
    """
    Generic discovery and profiling of logical record families within mixed enterprise datasets.
    Identifies explicit discriminator columns or infers families from mutually exclusive
    column-population (null/non-null) patterns.
    """

    DISCRIMINATOR_PATTERNS = [
        r"^record[_\s]?type$",
        r"^row[_\s]?type$",
        r"^entity[_\s]?type$",
        r"^transaction[_\s]?type$",
        r"^event[_\s]?type$",
        r"^type$",
        r"^category$",
        r"^kind$",
        r"^table[_\s]?type$",
    ]

    @classmethod
    def discover(cls, df: pl.DataFrame) -> Dict[str, Any]:
        row_count = df.height
        col_names = df.columns
        num_cols = len(col_names)

        if row_count < 10 or num_cols < 2:
            return {"is_mixed": False, "discriminator_column": None, "families": [], "primary_domain": None}

        # Discover primary domain from any email-like columns
        primary_domain = cls._discover_primary_domain(df)

        # 1. Look for explicit discriminator column candidates
        candidate_disc_cols: List[str] = []
        for col in col_names:
            c_lower = col.strip().lower()
            if any(re.match(pat, c_lower) for pat in cls.DISCRIMINATOR_PATTERNS):
                candidate_disc_cols.append(col)

        # Also check string columns with 2 to 15 unique values and low nulls (<15%)
        for col in col_names:
            if col not in candidate_disc_cols:
                series = df[col]
                if series.dtype == pl.String:
                    n_uniq = series.n_unique()
                    null_c = series.null_count()
                    if 2 <= n_uniq <= 15 and null_c < row_count * 0.15:
                        candidate_disc_cols.append(col)

        best_disc = None
        best_disc_score = 0.0

        for col in candidate_disc_cols:
            series = df[col]
            n_uniq = series.n_unique()
            if n_uniq < 2 or n_uniq > 20:
                continue

            val_counts = series.value_counts().filter(pl.col(col).is_not_null())
            if val_counts.height < 2:
                continue

            min_count = val_counts["count"].min()
            if min_count < max(5, int(row_count * 0.02)):
                continue

            distinct_vals = [v for v in val_counts[col].to_list() if v is not None]
            family_null_profiles = []
            for v in distinct_vals:
                sub = df.filter(pl.col(col) == v)
                sub_len = len(sub)
                if sub_len == 0:
                    continue
                null_rates = {c: sub[c].null_count() / sub_len for c in col_names if c != col}
                family_null_profiles.append(null_rates)

            if not family_null_profiles:
                continue

            divergent_columns = 0
            for c in col_names:
                if c == col:
                    continue
                rates = [p[c] for p in family_null_profiles]
                if max(rates) - min(rates) >= 0.5:
                    divergent_columns += 1

            score = divergent_columns / (num_cols - 1)
            c_lower = col.strip().lower()
            if any(re.match(pat, c_lower) for pat in cls.DISCRIMINATOR_PATTERNS[:5]):
                score += 0.35
            elif any(re.match(pat, c_lower) for pat in cls.DISCRIMINATOR_PATTERNS):
                score += 0.15

            if score > 0.3 and score > best_disc_score:
                best_disc_score = score
                best_disc = col

        # If explicit discriminator found
        if best_disc:
            families = cls._build_explicit_families(df, best_disc, col_names)
            is_mixed = len(families) > 1 and any(len(f["mostly_not_applicable_columns"]) > 0 for f in families)
            return {
                "is_mixed": is_mixed,
                "discriminator_column": best_disc if is_mixed else None,
                "primary_domain": primary_domain,
                "families": families if is_mixed else []
            }

        # 2. No explicit discriminator: Infer from column population patterns (signatures)
        sparse_cols = [c for c in col_names if df[c].null_count() / row_count > 0.2]
        if len(sparse_cols) >= 2:
            sig_exprs = [pl.when(pl.col(c).is_not_null()).then(pl.lit("1")).otherwise(pl.lit("0")) for c in sparse_cols]
            sig_col = pl.concat_str(sig_exprs).alias("__row_sig__")
            df_with_sig = df.with_columns(sig_col)
            sig_counts = df_with_sig["__row_sig__"].value_counts().filter(
                pl.col("count") >= max(5, int(row_count * 0.03))
            ).sort("count", descending=True)

            if len(sig_counts) >= 2:
                families = cls._build_inferred_families(df_with_sig, sig_counts, sparse_cols, col_names, row_count)
                is_mixed = len(families) > 1 and any(len(f["mostly_not_applicable_columns"]) > 0 for f in families)
                return {
                    "is_mixed": is_mixed,
                    "discriminator_column": None,
                    "primary_domain": primary_domain,
                    "families": families if is_mixed else []
                }

        return {
            "is_mixed": False,
            "discriminator_column": None,
            "primary_domain": primary_domain,
            "families": []
        }

    @classmethod
    def _discover_primary_domain(cls, df: pl.DataFrame) -> Optional[str]:
        """Discovers the dominant internal/company domain from email addresses in any column."""
        domain_counts: Dict[str, int] = {}
        for col in df.columns:
            if df[col].dtype == pl.String:
                for val in df[col].drop_nulls().head(1000).to_list():
                    val_str = str(val).lower()
                    if "@" in val_str:
                        for m in re.findall(r"@([a-z0-9.-]+)", val_str):
                            if m not in {"gmail.com", "outlook.com", "yahoo.com", "hotmail.com", "icloud.com"}:
                                domain_counts[m] = domain_counts.get(m, 0) + 1
        if domain_counts:
            sorted_domains = sorted(domain_counts.items(), key=lambda x: x[1], reverse=True)
            return sorted_domains[0][0]
        return None

    @classmethod
    def _classify_column_role(
        cls,
        col_name: str,
        inferred_type: str,
        sub_len: int,
        null_count: int,
        zero_count: int,
        non_zero_count: int,
        distinct_count: int,
        sample_values: List[str]
    ) -> str:
        name_lower = col_name.strip().lower()

        if inferred_type == "datetime":
            return "timestamp"
        if any(term in name_lower for term in ["time", "date", "timestamp", "datetime", "created_at", "updated_at"]):
            return "timestamp"

        if inferred_type == "boolean":
            return "flag"
        if distinct_count <= 2 and (name_lower.startswith("is_") or name_lower.startswith("has_")):
            return "flag"

        id_suffixes = ("_id", " id", "id", "_key", " key", "_code", " code", "_no", " no", "number")
        if (any(name_lower.endswith(sfx) or name_lower == sfx for sfx in id_suffixes)
                and inferred_type != "float" and sub_len > 0 and (distinct_count / sub_len > 0.4 or distinct_count >= 50)):
            return "identifier"

        if inferred_type == "string" and (
            name_lower in {"status", "action", "severity", "state", "stage", "action_status", "channel"}
            or (1 < distinct_count <= 20 and any(kw in name_lower for kw in ["status", "action", "severity", "stage", "channel", "priority"]))
        ):
            return "status"

        if inferred_type == "string" and (
            any(len(str(s)) > 80 for s in sample_values)
            or name_lower in {"description", "policies", "policy", "notes", "comment", "file name", "file_name", "message", "query"}
        ):
            return "text"

        if inferred_type in ["integer", "float"]:
            if sub_len > 0 and (null_count > 0 or zero_count > 0) and non_zero_count > 0:
                return "sparse_measure"
            return "measure"

        return "dimension"

    @classmethod
    def _build_explicit_families(cls, df: pl.DataFrame, disc_col: str, col_names: List[str]) -> List[Dict[str, Any]]:
        families = []
        val_counts = df[disc_col].value_counts().filter(pl.col(disc_col).is_not_null()).sort("count", descending=True)

        for row in val_counts.iter_rows(named=True):
            val = row[disc_col]
            sub = df.filter(pl.col(disc_col) == val)
            sub_len = len(sub)
            active_cols: List[str] = []
            not_applicable_cols: List[str] = []
            col_presence: Dict[str, float] = {}
            col_null_rate: Dict[str, float] = {}
            col_zero_rate: Dict[str, float] = {}
            col_nonzero_rate: Dict[str, float] = {}
            col_distinct: Dict[str, int] = {}
            col_samples: Dict[str, List[str]] = {}
            col_roles: Dict[str, str] = {}
            col_stats: Dict[str, Any] = {}

            for c in col_names:
                series = sub[c]
                null_c = int(series.null_count())
                null_rate = null_c / sub_len if sub_len else 1.0
                presence_rate = 1.0 - null_rate

                dtype_str = str(series.dtype).lower()
                if "int" in dtype_str:
                    inferred_type = "integer"
                elif "float" in dtype_str:
                    inferred_type = "float"
                elif "bool" in dtype_str:
                    inferred_type = "boolean"
                elif "date" in dtype_str or "time" in dtype_str:
                    inferred_type = "datetime"
                else:
                    inferred_type = "string"

                zero_c = 0
                non_zero_c = 0
                if inferred_type in ["integer", "float"] and sub_len > 0:
                    try:
                        zero_c = int((series == 0).sum())
                        non_zero_c = int(((series != 0) & series.is_not_null()).sum())
                    except Exception:
                        non_zero_c = max(0, sub_len - null_c)

                distinct_c = int(series.n_unique())
                samples = [str(s) for s in series.drop_nulls().head(5).to_list()]

                # Determine if column is applicable inside this family
                if null_rate >= 0.85 and c != disc_col:
                    not_applicable_cols.append(c)
                    role = "not_applicable"
                else:
                    active_cols.append(c)
                    role = cls._classify_column_role(
                        col_name=c,
                        inferred_type=inferred_type,
                        sub_len=sub_len,
                        null_count=null_c,
                        zero_count=zero_c,
                        non_zero_count=non_zero_c,
                        distinct_count=distinct_c,
                        sample_values=samples
                    )

                null_type = "NOT_APPLICABLE" if role == "not_applicable" else ("MISSING" if null_c > 0 else ("ZERO" if zero_c > 0 and non_zero_c == 0 else "POPULATED"))

                col_presence[c] = round(presence_rate, 4)
                col_null_rate[c] = round(null_rate, 4)
                col_zero_rate[c] = round(zero_c / sub_len, 4) if sub_len else 0.0
                col_nonzero_rate[c] = round(non_zero_c / sub_len, 4) if sub_len else 0.0
                col_distinct[c] = distinct_c
                col_samples[c] = samples
                col_roles[c] = role

                col_stats[c] = {
                    "inferred_type": inferred_type,
                    "role": role,
                    "null_type": null_type,
                    "family_null_count": null_c,
                    "null_count": null_c,
                    "null_rate": round(null_rate, 4),
                    "family_zero_count": zero_c,
                    "zero_count": zero_c,
                    "zero_rate": round(zero_c / sub_len, 4) if sub_len else 0.0,
                    "family_nonzero_count": non_zero_c,
                    "non_zero_count": non_zero_c,
                    "non_zero_rate": round(non_zero_c / sub_len, 4) if sub_len else 0.0,
                    "distinct_count": distinct_c,
                    "sample_values": samples,
                    "is_active": role != "not_applicable",
                    "is_applicable": role != "not_applicable"
                }

            family_id = re.sub(r'[^a-zA-Z0-9_]', '_', str(val).lower()).strip('_')
            families.append({
                "family": str(val),
                "family_name": str(val),
                "family_id": family_id,
                "row_count": sub_len,
                "family_row_count": sub_len,
                "inferred": False,
                "discriminator": {
                    "column": disc_col,
                    "operator": "equals",
                    "value": val
                },
                "active_columns": active_cols,
                "mostly_not_applicable_columns": not_applicable_cols,
                "column_presence": col_presence,
                "column_null_rate": col_null_rate,
                "column_zero_rate": col_zero_rate,
                "column_nonzero_rate": col_nonzero_rate,
                "column_distinct": col_distinct,
                "column_value_samples": col_samples,
                "column_presence_by_family": col_presence,
                "column_null_rate_by_family": col_null_rate,
                "column_zero_rate_by_family": col_zero_rate,
                "column_nonzero_rate_by_family": col_nonzero_rate,
                "column_distinct_by_family": col_distinct,
                "column_value_samples_by_family": col_samples,
                "column_roles": col_roles,
                "column_stats": col_stats
            })

        return families

    @classmethod
    def _build_inferred_families(
        cls,
        df_with_sig: pl.DataFrame,
        sig_counts: pl.DataFrame,
        sparse_cols: List[str],
        col_names: List[str],
        total_rows: int
    ) -> List[Dict[str, Any]]:
        # Cluster signatures with Jaccard similarity >= 0.75
        clusters: List[Dict[str, Any]] = []
        for row in sig_counts.iter_rows(named=True):
            sig = row["__row_sig__"]
            cnt = row["count"]
            active_indices = {i for i, ch in enumerate(sig) if ch == "1"}
            if not active_indices:
                continue

            best_cluster = None
            best_sim = 0.0
            for clus in clusters:
                union = active_indices | clus["active_indices"]
                inter = active_indices & clus["active_indices"]
                jaccard = len(inter) / len(union) if union else 0.0
                if jaccard > best_sim:
                    best_sim = jaccard
                    best_cluster = clus

            if best_cluster and best_sim >= 0.70:
                best_cluster["sigs"].append(sig)
                best_cluster["count"] += cnt
                best_cluster["active_indices"] |= active_indices
            else:
                clusters.append({
                    "sigs": [sig],
                    "active_indices": active_indices,
                    "count": cnt
                })

        families = []
        for idx, clus in enumerate(clusters):
            sigs = clus["sigs"]
            sub = df_with_sig.filter(pl.col("__row_sig__").is_in(sigs))
            sub_len = len(sub)
            if sub_len == 0:
                continue

            active_cols: List[str] = []
            not_applicable_cols: List[str] = []
            col_presence: Dict[str, float] = {}
            col_null_rate: Dict[str, float] = {}
            col_zero_rate: Dict[str, float] = {}
            col_nonzero_rate: Dict[str, float] = {}
            col_distinct: Dict[str, int] = {}
            col_samples: Dict[str, List[str]] = {}
            col_roles: Dict[str, str] = {}
            col_stats: Dict[str, Any] = {}
            key_active_col = None

            for c in col_names:
                series = sub[c]
                null_c = int(series.null_count())
                null_rate = null_c / sub_len if sub_len else 1.0
                presence_rate = 1.0 - null_rate

                dtype_str = str(series.dtype).lower()
                if "int" in dtype_str:
                    inferred_type = "integer"
                elif "float" in dtype_str:
                    inferred_type = "float"
                elif "bool" in dtype_str:
                    inferred_type = "boolean"
                elif "date" in dtype_str or "time" in dtype_str:
                    inferred_type = "datetime"
                else:
                    inferred_type = "string"

                zero_c = 0
                non_zero_c = 0
                if inferred_type in ["integer", "float"] and sub_len > 0:
                    try:
                        zero_c = int((series == 0).sum())
                        non_zero_c = int(((series != 0) & series.is_not_null()).sum())
                    except Exception:
                        non_zero_c = max(0, sub_len - null_c)

                distinct_c = int(series.n_unique())
                samples = [str(s) for s in series.drop_nulls().head(5).to_list()]

                if null_rate >= 0.85:
                    not_applicable_cols.append(c)
                    role = "not_applicable"
                else:
                    active_cols.append(c)
                    if not key_active_col and c in sparse_cols and null_rate == 0.0:
                        key_active_col = c
                    role = cls._classify_column_role(
                        col_name=c,
                        inferred_type=inferred_type,
                        sub_len=sub_len,
                        null_count=null_c,
                        zero_count=zero_c,
                        non_zero_count=non_zero_c,
                        distinct_count=distinct_c,
                        sample_values=samples
                    )

                null_type = "NOT_APPLICABLE" if role == "not_applicable" else ("MISSING" if null_c > 0 else ("ZERO" if zero_c > 0 and non_zero_c == 0 else "POPULATED"))

                col_presence[c] = round(presence_rate, 4)
                col_null_rate[c] = round(null_rate, 4)
                col_zero_rate[c] = round(zero_c / sub_len, 4) if sub_len else 0.0
                col_nonzero_rate[c] = round(non_zero_c / sub_len, 4) if sub_len else 0.0
                col_distinct[c] = distinct_c
                col_samples[c] = samples
                col_roles[c] = role

                col_stats[c] = {
                    "inferred_type": inferred_type,
                    "role": role,
                    "null_type": null_type,
                    "family_null_count": null_c,
                    "null_count": null_c,
                    "null_rate": round(null_rate, 4),
                    "family_zero_count": zero_c,
                    "zero_count": zero_c,
                    "zero_rate": round(zero_c / sub_len, 4) if sub_len else 0.0,
                    "family_nonzero_count": non_zero_c,
                    "non_zero_count": non_zero_c,
                    "non_zero_rate": round(non_zero_c / sub_len, 4) if sub_len else 0.0,
                    "distinct_count": distinct_c,
                    "sample_values": samples,
                    "is_active": role != "not_applicable",
                    "is_applicable": role != "not_applicable"
                }

            if not key_active_col and active_cols:
                key_active_col = active_cols[0]

            family_label = f"family_{idx+1}"
            if key_active_col:
                clean_name = re.sub(r'[^a-zA-Z0-9_]', '_', key_active_col.lower()).strip('_')
                family_label = f"family_{clean_name}"

            families.append({
                "family": family_label,
                "family_name": family_label,
                "family_id": f"family_{idx+1}",
                "row_count": sub_len,
                "family_row_count": sub_len,
                "inferred": True,
                "discriminator": {
                    "column": key_active_col,
                    "operator": "is_not_null",
                    "value": None
                } if key_active_col else None,
                "active_columns": active_cols,
                "mostly_not_applicable_columns": not_applicable_cols,
                "column_presence": col_presence,
                "column_null_rate": col_null_rate,
                "column_zero_rate": col_zero_rate,
                "column_nonzero_rate": col_nonzero_rate,
                "column_distinct": col_distinct,
                "column_value_samples": col_samples,
                "column_presence_by_family": col_presence,
                "column_null_rate_by_family": col_null_rate,
                "column_zero_rate_by_family": col_zero_rate,
                "column_nonzero_rate_by_family": col_nonzero_rate,
                "column_distinct_by_family": col_distinct,
                "column_value_samples_by_family": col_samples,
                "column_roles": col_roles,
                "column_stats": col_stats
            })

        return families

    @classmethod
    def classify_null_type(cls, family_meta: Dict[str, Any], col: str, val: Any) -> str:
        """
        Distinguishes NULL types:
        - NOT_APPLICABLE: column is not in active_columns for this family
        - MISSING: column is active in this family but value is null/None
        - ZERO: value is 0
        - POPULATED: value is populated non-zero
        """
        if col in family_meta.get("mostly_not_applicable_columns", []) or col not in family_meta.get("active_columns", []):
            return "NOT_APPLICABLE"
        if val is None or (isinstance(val, float) and val != val) or str(val).strip() in ("", "nan", "None", "null"):
            return "MISSING"
        if val == 0 or val == "0" or val == 0.0:
            return "ZERO"
        return "POPULATED"
