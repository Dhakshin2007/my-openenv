"""
Deterministic graders for each task.
Each grader returns (score: float, details: dict) where score ∈ [0.0, 1.0].
"""

from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _cols(rows: List[Dict]) -> set:
    if not rows:
        return set()
    return {k.lower() for k in rows[0].keys()}


def _val(row: Dict, *candidates: str) -> Optional[Any]:
    """Return first value whose key (case-insensitive) matches any candidate."""
    for k, v in row.items():
        if k.lower() in candidates:
            return v
    return None


# ---------------------------------------------------------------------------
# Task 1 – fix_broken_query (easy)
# ---------------------------------------------------------------------------

def grade_fix_broken_query(result: List[Dict], sql: str) -> Tuple[float, Dict]:
    details: Dict[str, Any] = {}
    score = 0.0

    if not result:
        details["feedback"] = "Query returned no rows. Expected 3."
        return 0.0, details

    # ── Row count (40 pts) ──────────────────────────────────────────────────
    if len(result) == 3:
        score += 0.40
        details["row_count"] = "✓ correct (3)"
    else:
        details["row_count"] = f"✗ expected 3, got {len(result)}"
        if len(result) > 0:
            score += 0.05  # partial credit

    # ── Required columns (20 pts) ───────────────────────────────────────────
    cols = _cols(result)
    required = {"name", "email", "total_spent"}
    missing = required - cols
    if not missing:
        score += 0.20
        details["columns"] = "✓ name, email, total_spent present"
    else:
        details["columns"] = f"✗ missing: {missing}"

    # ── Value correctness (40 pts) ──────────────────────────────────────────
    expected_map = {
        "alice smith":  225.50,
        "bob jones":    200.00,
        "carol white":  300.00,
    }
    correct = 0
    for row in result:
        name = (_val(row, "name") or "").lower()
        total = _val(row, "total_spent")
        if name in expected_map and total is not None:
            if abs(float(total) - expected_map[name]) < 0.02:
                correct += 1

    value_score = correct / len(expected_map)
    score += value_score * 0.40
    details["values"] = f"✓ {correct}/3 customer totals correct" if correct == 3 \
        else f"✗ {correct}/3 customer totals correct"

    # ── DESC ordering bonus (if 40/40 + 20/20) ─────────────────────────────
    if len(result) == 3 and not missing:
        totals = [_val(r, "total_spent") for r in result]
        if totals == sorted(totals, reverse=True):
            details["ordering"] = "✓ ordered DESC"
        else:
            details["ordering"] = "✗ not ordered DESC (lose no points, but fix it)"

    details["feedback"] = f"Score: {score:.2f}/1.00"
    return round(min(score, 1.0), 4), details


# ---------------------------------------------------------------------------
# Task 2 – write_business_query (medium)
# ---------------------------------------------------------------------------

def grade_write_business_query(result: List[Dict], sql: str) -> Tuple[float, Dict]:
    details: Dict[str, Any] = {}
    score = 0.0

    if not result:
        details["feedback"] = "Query returned no rows. Expected 3."
        return 0.0, details

    # ── Row count (25 pts) ──────────────────────────────────────────────────
    if len(result) == 3:
        score += 0.25
        details["row_count"] = "✓ correct (3 depts with >1 employee)"
    elif len(result) == 4:
        details["row_count"] = "✗ returned 4 rows — HR dept should be excluded (only 1 employee)"
        score += 0.05
    else:
        details["row_count"] = f"✗ expected 3, got {len(result)}"

    # ── Department names (15 pts) ───────────────────────────────────────────
    result_str = " ".join(str(v).lower() for row in result for v in row.values())
    expected_depts = {"engineering", "marketing", "finance"}
    found_depts = {d for d in expected_depts if d in result_str}
    dept_score = len(found_depts) / len(expected_depts) * 0.15
    score += dept_score
    details["departments"] = f"✓ found: {found_depts}" if found_depts == expected_depts \
        else f"✗ found: {found_depts}, missing: {expected_depts - found_depts}"

    # ── Employee count column present (10 pts) ──────────────────────────────
    cols = _cols(result)
    has_count = any(k in cols for k in
                    {"count", "num_employees", "employee_count", "emp_count", "headcount",
                     "count(*)", "count(e.id)", "cnt"})
    # looser check: any numeric column that isn't salary
    if not has_count:
        for row in result:
            for k, v in row.items():
                if isinstance(v, (int, float)) and v in (2, 3) and "salary" not in k.lower():
                    has_count = True
                    break
    if has_count:
        score += 0.10
        details["emp_count_col"] = "✓ employee count column detected"
    else:
        details["emp_count_col"] = "✗ employee count column not detected"

    # ── Avg salary column present and roughly correct (15 pts) ─────────────
    for row in result:
        row_lower = {k.lower(): v for k, v in row.items()}
        if "engineering" in str(list(row.values())).lower():
            # Engineering avg salary = (120000+95000+110000)/3 = 108333.33
            for k, v in row_lower.items():
                if isinstance(v, (int, float)) and 108000 < v < 109000:
                    score += 0.15
                    details["avg_salary"] = "✓ Engineering avg salary correct (~108333)"
                    break
            break

    # ── Highest-paid employee name (20 pts) ─────────────────────────────────
    for row in result:
        row_str = str(list(row.values())).lower()
        if "engineering" in row_str and "alice" in row_str:
            score += 0.20
            details["top_earner"] = "✓ Alice identified as Engineering top earner"
            break
    else:
        details["top_earner"] = "✗ Alice not found as Engineering top earner"

    # ── Ordering by avg salary DESC (15 pts) ────────────────────────────────
    avg_vals = []
    for row in result:
        for k, v in row.items():
            if isinstance(v, (int, float)) and 50000 < v < 200000:
                avg_vals.append(v)
                break
    if len(avg_vals) == 3 and avg_vals == sorted(avg_vals, reverse=True):
        score += 0.15
        details["ordering"] = "✓ ordered by avg salary DESC"
    else:
        details["ordering"] = "✗ not ordered by avg salary DESC (or couldn't detect)"

    details["feedback"] = f"Score: {score:.2f}/1.00"
    return round(min(score, 1.0), 4), details


# ---------------------------------------------------------------------------
# Task 3 – complex_analytics (hard)
# ---------------------------------------------------------------------------

def grade_complex_analytics(result: List[Dict], sql: str) -> Tuple[float, Dict]:
    details: Dict[str, Any] = {}
    score = 0.0
    # Normalise: collapse whitespace, uppercase for pattern matching
    sql_norm = " ".join(sql.upper().split())

    # ── SQL structure checks ─────────────────────────────────────────────────

    # JOINs (need ≥ 2 for 3 tables — may be inside a CTE)
    join_count = sql_norm.count(" JOIN ")
    if join_count >= 2:
        score += 0.15
        details["joins"] = f"✓ {join_count} JOINs present"
    elif join_count == 1:
        score += 0.05
        details["joins"] = "✗ only 1 JOIN; need 2 for 3 tables"
    else:
        details["joins"] = "✗ no JOINs found"

    # Year filter for 2023 (handles CTEs and sub-queries too)
    has_year_filter = (
        "2023" in sql or
        "STRFTIME" in sql_norm or
        ("YEAR" in sql_norm and "2023" in sql)
    )
    if has_year_filter:
        score += 0.10
        details["year_filter"] = "✓ 2023 filter present"
    else:
        details["year_filter"] = "✗ no year filter found — 2022 data may be included"

    # GROUP BY (may be inside CTE)
    if "GROUP BY" in sql_norm:
        score += 0.05
        details["group_by"] = "✓ GROUP BY present"
    else:
        details["group_by"] = "✗ GROUP BY missing"

    # Window function / ranking for top-2
    has_window = any(fn in sql_norm for fn in
                     ["ROW_NUMBER()", "RANK()", "DENSE_RANK()", "OVER (", "OVER("])
    has_multi_select = sql_norm.count("SELECT") > 1  # subquery or CTE approach
    if has_window:
        score += 0.15
        details["ranking"] = "✓ window function used for ranking"
    elif has_multi_select:
        score += 0.08
        details["ranking"] = "~ CTE/subquery used for ranking (window fn preferred)"
    else:
        details["ranking"] = "✗ no window function or subquery for top-2 ranking"

    # ── Result quality checks ────────────────────────────────────────────────

    if not result:
        details["feedback"] = f"Score: {score:.2f}/1.00 — query returned no rows"
        return round(min(score, 1.0), 4), details

    # Row count (should be 4: top-2 USA + top-2 Canada)
    if len(result) == 4:
        score += 0.20
        details["row_count"] = "✓ 4 rows (top-2 per country)"
    elif 3 <= len(result) <= 6:
        score += 0.08
        details["row_count"] = f"~ {len(result)} rows (expected 4)"
    else:
        details["row_count"] = f"✗ {len(result)} rows (expected 4)"

    # Required columns present
    cols = _cols(result)
    req_cols = {"country", "category", "total_revenue"}
    optional_cols = {"total_units_sold", "num_transactions"}
    found_req = req_cols & cols
    found_opt = optional_cols & cols

    if found_req == req_cols:
        score += 0.10
        details["columns"] = f"✓ required cols: {found_req}; bonus: {found_opt}"
    else:
        details["columns"] = f"✗ missing required: {req_cols - found_req}"

    # No 2022 data in results
    result_str = " ".join(str(v) for row in result for v in row.values())
    if "2022" not in result_str:
        score += 0.10
        details["no_2022"] = "✓ 2022 data excluded from results"
    else:
        details["no_2022"] = "✗ 2022 data appears in results"

    # Top-2 per country constraint
    from collections import defaultdict
    country_counts: Dict[str, int] = defaultdict(int)
    for row in result:
        country = _val(row, "country")
        if country:
            country_counts[str(country)] += 1
    all_le2 = all(v <= 2 for v in country_counts.values())
    if all_le2 and len(country_counts) >= 2:
        score += 0.15
        details["top_2"] = f"✓ ≤2 rows per country: {dict(country_counts)}"
    else:
        details["top_2"] = f"✗ country counts: {dict(country_counts)} (need ≤2 per country)"

    details["feedback"] = f"Score: {score:.2f}/1.00"
    return round(min(score, 1.0), 4), details


# ---------------------------------------------------------------------------
# Task 4 – recursive_org_hierarchy (hard)
# ---------------------------------------------------------------------------

def grade_recursive_org(result: List[Dict], sql: str) -> Tuple[float, Dict]:
    details: Dict[str, Any] = {}
    score = 0.0
    sql_norm = " ".join(sql.upper().split())

    # ── SQL structure (35 pts) ───────────────────────────────────────────────
    has_recursive = "WITH RECURSIVE" in sql_norm
    if has_recursive:
        score += 0.15
        details["recursive_cte"] = "✓ WITH RECURSIVE present"
    else:
        details["recursive_cte"] = "✗ WITH RECURSIVE missing (required)"

    has_union_all = "UNION ALL" in sql_norm
    if has_union_all:
        score += 0.10
        details["union_all"] = "✓ UNION ALL present (needed for recursion)"
    else:
        details["union_all"] = "✗ UNION ALL missing inside CTE"

    has_left_join = "LEFT JOIN" in sql_norm
    if has_left_join:
        score += 0.10
        details["left_join"] = "✓ LEFT JOIN present (handles 0-project employees)"
    else:
        details["left_join"] = "✗ LEFT JOIN missing (employees with no projects will be NULL)"

    if not result:
        details["feedback"] = f"Score: {score:.2f}/1.00 — query returned no rows"
        return round(min(score, 1.0), 4), details

    # ── Row count (20 pts) ───────────────────────────────────────────────────
    if len(result) == 7:
        score += 0.20
        details["row_count"] = "✓ 7 rows (CTO + 6 in org)"
    elif 5 <= len(result) <= 9:
        score += 0.08
        details["row_count"] = f"~ {len(result)} rows (expected 7)"
    else:
        details["row_count"] = f"✗ {len(result)} rows (expected 7)"

    # ── CEO / Henry excluded (10 pts) ────────────────────────────────────────
    names_in_result = {str(_val(r, "name") or "").lower() for r in result}
    no_ceo = "sarah ceo" not in names_in_result
    no_henry = "henry cfo" not in names_in_result
    if no_ceo and no_henry:
        score += 0.10
        details["exclusion"] = "✓ CEO and CFO correctly excluded"
    else:
        missing = []
        if not no_ceo: missing.append("CEO appeared in results")
        if not no_henry: missing.append("CFO appeared in results")
        details["exclusion"] = f"✗ {'; '.join(missing)}"

    # ── Depth column present and correct (15 pts) ────────────────────────────
    depth_vals = []
    for r in result:
        for k, v in r.items():
            if "depth" in k.lower() and isinstance(v, (int, float)):
                depth_vals.append(int(v))
                break

    if depth_vals:
        has_zero = 0 in depth_vals
        has_two  = 2 in depth_vals
        max_d    = max(depth_vals)
        if has_zero and has_two and max_d == 2:
            score += 0.15
            details["depth"] = "✓ depth column correct (0, 1, 2)"
        elif has_zero:
            score += 0.07
            details["depth"] = f"~ depth starts at 0 but max={max_d} (expected 2)"
        else:
            details["depth"] = f"✗ depth values unexpected: {sorted(set(depth_vals))}"
    else:
        details["depth"] = "✗ no depth column detected"

    # ── num_active_projects correct (includes 0s) (10 pts) ──────────────────
    project_vals = []
    for r in result:
        for k, v in r.items():
            if "project" in k.lower() and isinstance(v, (int, float)):
                project_vals.append(int(v))
                break

    if project_vals:
        has_zero_proj = 0 in project_vals
        has_two_proj  = 2 in project_vals   # Carol leads 2 active projects
        if has_zero_proj and has_two_proj:
            score += 0.10
            details["projects"] = "✓ project counts correct (has 0s and 2)"
        elif has_zero_proj:
            score += 0.05
            details["projects"] = "~ has 0 project counts but Carol's 2 not detected"
        else:
            details["projects"] = "✗ no 0 project counts (LEFT JOIN issue?)"
    else:
        details["projects"] = "✗ num_active_projects column not detected"

    # ── manager_name column present and correct (10 pts) ────────────────────
    has_manager = any(
        "manager" in str(k).lower() for row in result for k in row.keys()
    )
    if has_manager:
        # Verify CTO's manager is the CEO
        for row in result:
            row_str = " ".join(str(v).lower() for v in row.values())
            if "alice cto" in row_str or (
                any("depth" in k.lower() and v == 0 for k, v in row.items())
            ):
                manager_val = _val(row, "manager_name", "manager")
                if manager_val and "ceo" in str(manager_val).lower():
                    score += 0.10
                    details["manager_name"] = "✓ manager_name column present and correct"
                    break
                elif manager_val:
                    score += 0.05
                    details["manager_name"] = f"~ manager_name present: {manager_val}"
                    break
        else:
            score += 0.05
            details["manager_name"] = "~ manager_name column present but couldn't verify"
    else:
        details["manager_name"] = "✗ manager_name column missing"

    details["feedback"] = f"Score: {score:.2f}/1.00"
    return round(min(score, 1.0), 4), details


# ---------------------------------------------------------------------------
# Task 5 – data_quality_audit (hard)
# ---------------------------------------------------------------------------

def grade_data_quality(result: List[Dict], sql: str) -> Tuple[float, Dict]:
    details: Dict[str, Any] = {}
    score = 0.0
    sql_norm = " ".join(sql.upper().split())

    # ── SQL structure (20 pts) ───────────────────────────────────────────────
    union_count = sql_norm.count("UNION ALL")
    if union_count >= 4:
        score += 0.10
        details["union_all"] = f"✓ {union_count} UNION ALLs (need ≥4 for 5 issues)"
    elif union_count > 0:
        score += 0.04
        details["union_all"] = f"~ only {union_count} UNION ALLs"
    else:
        details["union_all"] = "✗ no UNION ALL found"

    has_left_join = "LEFT JOIN" in sql_norm
    if has_left_join:
        score += 0.10
        details["left_join"] = "✓ LEFT JOIN present (needed for orphan detection)"
    else:
        details["left_join"] = "✗ LEFT JOIN missing (orphan_txn check won't work)"

    if not result:
        details["feedback"] = f"Score: {score:.2f}/1.00 — query returned no rows"
        return round(min(score, 1.0), 4), details

    # ── Row count = 5 (10 pts) ───────────────────────────────────────────────
    if len(result) == 5:
        score += 0.10
        details["row_count"] = "✓ 5 rows (one per issue type)"
    else:
        details["row_count"] = f"✗ {len(result)} rows (expected 5)"

    # ── Required columns (10 pts) ────────────────────────────────────────────
    cols = _cols(result)
    has_issue_type  = any("issue" in c and "type" in c for c in cols)
    has_issue_count = any("count" in c for c in cols)
    has_example_ids = any("example" in c or "id" in c for c in cols)
    if has_issue_type and has_issue_count:
        score += 0.10
        details["columns"] = f"✓ issue_type and issue_count columns present"
    else:
        details["columns"] = f"✗ missing required columns; got: {cols}"

    # ── Issue type presence (25 pts, 5 pts each) ────────────────────────────
    EXPECTED_ISSUES = {
        "duplicate_email": 2,
        "null_name": 1,
        "invalid_amount": 3,
        "orphan_txn": 2,
        "future_txn": 1,
    }

    # Build a map: issue_type -> row
    issue_map: Dict[str, Dict] = {}
    for row in result:
        for k, v in row.items():
            if "issue" in k.lower() and "type" in k.lower() and v:
                issue_map[str(v).lower().strip()] = row
                break
            elif "type" in k.lower() and v and any(
                    x in str(v).lower() for x in EXPECTED_ISSUES):
                issue_map[str(v).lower().strip()] = row
                break

    found_issues = set(issue_map.keys())
    issue_pts = 0
    issue_details = []
    for expected_type, expected_count in EXPECTED_ISSUES.items():
        # fuzzy match
        matched = next(
            (k for k in found_issues if expected_type.replace("_", "") in k.replace("_", "")),
            None
        )
        if matched:
            row = issue_map[matched]
            # find count value
            actual_count = None
            for k, v in row.items():
                if "count" in k.lower() and isinstance(v, (int, float)):
                    actual_count = int(v)
                    break
            if actual_count == expected_count:
                issue_pts += 5
                issue_details.append(f"  ✓ {expected_type}: count={actual_count}")
            elif actual_count is not None:
                issue_pts += 2
                issue_details.append(
                    f"  ~ {expected_type}: count={actual_count} (expected {expected_count})"
                )
            else:
                issue_pts += 1
                issue_details.append(f"  ~ {expected_type}: present but count unreadable")
        else:
            issue_details.append(f"  ✗ {expected_type}: MISSING from results")

    issue_score = issue_pts / 25.0 * 0.50   # 50 pts for correctness
    score += issue_score
    details["issues"] = "\n".join(issue_details)

    # ── example_ids column present (10 pts) ─────────────────────────────────
    has_example = any(
        "example" in str(k).lower() or ("id" in str(k).lower() and "issue" not in str(k).lower())
        for row in result for k in row.keys()
    )
    if has_example:
        # spot-check: orphan_txn should mention ids 7 and 8
        for row in result:
            row_vals = " ".join(str(v) for v in row.values())
            if "orphan" in row_vals.lower():
                if "7" in row_vals and "8" in row_vals:
                    score += 0.10
                    details["example_ids"] = "✓ example_ids present and correct (orphan check)"
                    break
                else:
                    score += 0.05
                    details["example_ids"] = "~ example_ids present but orphan ids not 7,8"
                    break
        else:
            score += 0.05
            details["example_ids"] = "~ example_ids column present"
    else:
        details["example_ids"] = "✗ example_ids column missing"

    details["feedback"] = f"Score: {score:.2f}/1.00"
    return round(min(score, 1.0), 4), details


# ---------------------------------------------------------------------------
# Task 6 – query_optimizer (expert)
# ---------------------------------------------------------------------------

def grade_query_optimizer(result: List[Dict], sql: str) -> Tuple[float, Dict]:
    details: Dict[str, Any] = {}
    score = 0.0
    sql_norm = " ".join(sql.upper().split())

    has_join     = "JOIN" in sql_norm
    has_group_by = "GROUP BY" in sql_norm
    has_having   = "HAVING" in sql_norm

    # Correlated subquery smell: SELECT inside WHERE
    where_pos = sql_norm.find(" WHERE ")
    having_pos = sql_norm.find(" HAVING ")
    if where_pos > 0:
        end = having_pos if having_pos > where_pos else len(sql_norm)
        corr_in_where = sql_norm[where_pos:end].count("SELECT") > 0
    else:
        corr_in_where = False

    if has_join and has_group_by and has_having and not corr_in_where:
        score += 0.30
        details["optimization"] = "✓ JOIN + GROUP BY + HAVING — no correlated subquery in WHERE"
    elif has_join and has_group_by:
        score += 0.15
        details["optimization"] = "~ JOIN + GROUP BY but correlated subquery still in WHERE"
    elif has_join:
        score += 0.05
        details["optimization"] = "✗ Has JOIN but missing GROUP BY/HAVING"
    else:
        details["optimization"] = "✗ No JOIN — correlated subqueries likely still present"

    if not result:
        details["feedback"] = f"Score: {score:.2f}/1.00 — no rows"
        return round(min(score, 1.0), 4), details

    if len(result) == 3:
        score += 0.20
        details["row_count"] = "✓ 3 qualifying users (Alice, Bob, Frank)"
    else:
        score += max(0, 0.08 - abs(len(result) - 3) * 0.02)
        details["row_count"] = f"~ {len(result)} rows (expected 3)"

    cols = _cols(result)
    has_name  = any("name"  in c for c in cols)
    has_total = any("total" in c or "spent" in c or "amount" in c for c in cols)
    has_cnt   = any("count" in c or "order" in c for c in cols)
    has_last  = any("last" in c or "date" in c or "recent" in c for c in cols)
    col_pts = sum([has_name, has_total, has_cnt, has_last]) / 4 * 0.20
    score += col_pts
    details["columns"] = f"✓ {int(col_pts/0.05)}/4 required columns present"

    result_str = " ".join(str(v).lower() for row in result for v in row.values())
    if "bob" in result_str:
        score += 0.15
        details["bob_included"] = "✓ Bob Jones present (4 completed orders)"
    else:
        details["bob_included"] = "✗ Bob Jones missing"

    if "carol" not in result_str:
        score += 0.15
        details["carol_excluded"] = "✓ Carol excluded (only 2 completed orders)"
    else:
        details["carol_excluded"] = "✗ Carol should be excluded (≤2 completed)"

    details["feedback"] = f"Score: {score:.2f}/1.00"
    return round(min(score, 1.0), 4), details


# ---------------------------------------------------------------------------
# Task 7 – nl_to_sql (expert)
# ---------------------------------------------------------------------------

def grade_nl_to_sql(result: List[Dict], sql: str) -> Tuple[float, Dict]:
    details: Dict[str, Any] = {}
    score = 0.0
    sql_norm = " ".join(sql.upper().split())

    join_count = sql_norm.count("JOIN")
    if join_count >= 3:
        score += 0.15
        details["joins"] = f"✓ {join_count} JOINs (need ≥3 for 4 tables)"
    elif join_count >= 1:
        score += 0.05
        details["joins"] = f"~ {join_count} JOINs (need ≥3)"
    else:
        details["joins"] = "✗ No JOINs found"

    if "GROUP BY" in sql_norm:
        score += 0.05
        details["group_by"] = "✓ GROUP BY present"
    else:
        details["group_by"] = "✗ GROUP BY missing"

    if "HAVING" in sql_norm:
        score += 0.05
        details["having"] = "✓ HAVING present (dept headcount filter)"
    else:
        details["having"] = "✗ HAVING missing"

    if sql_norm.count("SELECT") > 1:
        score += 0.05
        details["subquery"] = "✓ Subquery present (company-wide avg)"
    else:
        details["subquery"] = "~ No subquery — above_avg_count may be wrong"

    if not result:
        details["feedback"] = f"Score: {score:.2f}/1.00 — no rows"
        return round(min(score, 1.0), 4), details

    if len(result) == 3:
        score += 0.20
        details["row_count"] = "✓ 3 departments (HR excluded)"
    elif len(result) == 4:
        score += 0.05
        details["row_count"] = "✗ 4 rows — HR should be excluded (<3 employees)"
    else:
        details["row_count"] = f"✗ {len(result)} rows (expected 3)"

    cols = _cols(result)
    req_groups = ["department", "headcount", "avg", "hours", "salary"]
    found_cols = sum(1 for r in req_groups if any(r in c for c in cols))
    score += found_cols / len(req_groups) * 0.20
    details["columns"] = f"✓ {found_cols}/{len(req_groups)} column groups found"

    result_str = " ".join(str(v) for row in result for v in row.values())
    if result:
        first_dept = str(_val(result[0], "department") or "").lower()
        if "finance" in first_dept:
            score += 0.15
            details["ordering"] = "✓ Finance first (highest avg score)"
        else:
            details["ordering"] = f"✗ Expected Finance first, got: '{first_dept}'"

    if "hr" not in result_str.lower():
        score += 0.15
        details["hr_excluded"] = "✓ HR excluded correctly"
    else:
        details["hr_excluded"] = "✗ HR should not appear (<3 employees)"

    details["feedback"] = f"Score: {score:.2f}/1.00"
    return round(min(score, 1.0), 4), details


# ---------------------------------------------------------------------------
# Task 8 – transaction_deadlock (expert)
# ---------------------------------------------------------------------------

def grade_transaction_deadlock(result: List[Dict], sql: str) -> Tuple[float, Dict]:
    details: Dict[str, Any] = {}
    score = 0.0
    sql_norm = " ".join(sql.upper().split())

    union_count = sql_norm.count("UNION ALL")
    if union_count >= 4:
        score += 0.15
        details["union_all"] = f"✓ {union_count} UNION ALLs"
    elif union_count > 0:
        score += 0.05
        details["union_all"] = f"~ {union_count} UNION ALLs (need ≥4)"
    else:
        details["union_all"] = "✗ No UNION ALL"

    if "JOIN" in sql_norm:
        score += 0.05
        details["join"] = "✓ JOIN present"
    else:
        details["join"] = "✗ No JOIN"

    if "IS NULL" in sql_norm:
        score += 0.05
        details["null_check"] = "✓ IS NULL present (unreleased locks)"
    else:
        details["null_check"] = "✗ IS NULL missing"

    if not result:
        details["feedback"] = f"Score: {score:.2f}/1.00 — no rows"
        return round(min(score, 1.0), 4), details

    if len(result) == 5:
        score += 0.15
        details["row_count"] = "✓ 5 rows (one per anomaly)"
    else:
        score += max(0, 0.08 - abs(len(result) - 5) * 0.02)
        details["row_count"] = f"~ {len(result)} rows (expected 5)"

    EXPECTED = {
        "overdraft": 1, "unreleased_lock": 3, "duplicate_txn": 1,
        "self_transfer": 1, "large_transfer": 2,
    }
    correct = 0
    anom_lines = []
    for atype, exp_cnt in EXPECTED.items():
        matched = None
        for row in result:
            row_str = " ".join(str(v).lower() for v in row.values())
            slug = atype.replace("_", "")
            if slug in row_str.replace("_", "") or atype.split("_")[0] in row_str:
                matched = row
                break
        if matched:
            actual = next((int(v) for k, v in matched.items()
                           if "count" in k.lower() and isinstance(v, (int, float))), None)
            if actual == exp_cnt:
                score += 0.10   # 5 × 0.10 = 0.50; total max = 0.15+0.05+0.05+0.15+0.50+0.10 = 1.00
                correct += 1
                anom_lines.append(f"  ✓ {atype}: {actual}")
            elif actual is not None:
                score += 0.04
                anom_lines.append(f"  ~ {atype}: {actual} (expected {exp_cnt})")
            else:
                score += 0.02
                anom_lines.append(f"  ~ {atype}: present, count unreadable")
        else:
            anom_lines.append(f"  ✗ {atype}: MISSING")

    details["anomalies"] = "\n".join(anom_lines)

    cols = _cols(result)
    if any("detail" in c or "description" in c or ("id" in c and "anomaly" not in c)
           for c in cols):
        score += 0.10
        details["details_col"] = "✓ details column present"
    else:
        details["details_col"] = "✗ details/IDs column missing"

    details["feedback"] = f"Score: {score:.2f}/1.00 ({correct}/5 anomalies correct)"
    return round(min(score, 1.0), 4), details


GRADERS = {
    "fix_broken_query":        grade_fix_broken_query,
    "write_business_query":    grade_write_business_query,
    "complex_analytics":       grade_complex_analytics,
    "recursive_org_hierarchy": grade_recursive_org,
    "data_quality_audit":      grade_data_quality,
    "query_optimizer":         grade_query_optimizer,
    "nl_to_sql":               grade_nl_to_sql,
    "transaction_deadlock":    grade_transaction_deadlock,
}


def grade(task_id: str, result: List[Dict], sql: str) -> Tuple[float, Dict]:
    """Grade a submitted SQL query. Returns (score, details)."""
    fn = GRADERS.get(task_id)
    if fn is None:
        return 0.0, {"feedback": f"Unknown task: {task_id}"}
    return fn(result, sql)
