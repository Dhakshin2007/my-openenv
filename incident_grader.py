"""
incident_grader.py — Multi-stage grader for the Incident Response task.

Scores 5 stages with partial credit:
  Stage 1 DIAGNOSE  (20%) — did the agent find all corrupt tables/columns?
  Stage 2 TRIAGE    (15%) — did the agent correctly count affected rows?
  Stage 3 REPAIR    (40%) — did the repair queries actually fix the data?
  Stage 4 VERIFY    (15%) — did the agent prove the fix worked?
  Stage 5 PREVENT   (10%) — did the agent write detection/prevention SQL?
"""

import sqlite3
from typing import Any, Dict, List, Optional, Tuple


def _run(conn: sqlite3.Connection, sql: str) -> Tuple[Optional[List[Dict]], Optional[str]]:
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        for stmt in sql.split(";"):
            stmt = stmt.strip()
            if stmt:
                cur.execute(stmt)
        conn.commit()
        if cur.description:
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()], None
        return [], None
    except Exception as exc:
        return None, str(exc)


def grade_incident_response(
    submitted_sql: str,
    task_def: Dict,
    env_conn: sqlite3.Connection,
) -> Tuple[float, Dict]:
    """
    Grade an incident response submission.
    The agent may submit multiple SQL statements separated by semicolons.
    """
    details: Dict[str, Any] = {}
    score = 0.0
    sql_up = " ".join(submitted_sql.upper().split())
    corruptions = task_def.get("corruptions", [])

    # ── Stage 1: DIAGNOSE — SQL mentions affected tables/columns (20%) ────────
    stage1 = 0.0
    diagnosis_hits = 0
    for c in corruptions:
        table   = c["affected_table"].upper()
        hint_kw = c["diagnosis_hint"].upper()
        # Check that the submitted SQL references the right table and a relevant condition
        keywords = hint_kw.split()
        if table in sql_up and any(kw in sql_up for kw in keywords if len(kw) > 3):
            diagnosis_hits += 1

    stage1 = (diagnosis_hits / max(len(corruptions), 1)) * 0.20
    score += stage1
    details["stage1_diagnose"] = (
        f"✓ {diagnosis_hits}/{len(corruptions)} issues diagnosed"
        if diagnosis_hits == len(corruptions)
        else f"~ {diagnosis_hits}/{len(corruptions)} issues diagnosed"
    )

    # ── Stage 2: TRIAGE — COUNT(*) queries for each issue (15%) ─────────────
    stage2 = 0.0
    has_count = "COUNT" in sql_up
    has_group  = "GROUP BY" in sql_up or sql_up.count("COUNT") >= len(corruptions)
    if has_count and diagnosis_hits >= 2:
        stage2 = 0.15 * (diagnosis_hits / len(corruptions))
        score += stage2
        details["stage2_triage"] = f"✓ COUNT queries present for {diagnosis_hits} issues"
    elif has_count:
        stage2 = 0.05
        score += stage2
        details["stage2_triage"] = "~ COUNT present but triage incomplete"
    else:
        details["stage2_triage"] = "✗ No COUNT/triage queries found"

    # ── Stage 3: REPAIR — actually execute fixes and verify DB state (40%) ───
    stage3 = 0.0
    repair_results = []

    for c in corruptions:
        verify_sql  = c["verify_sql"]
        expected_val = c["verify_expected"]  # should be 0 after fix

        # First, try running the submitted SQL against the live connection
        rows, err = _run(env_conn, submitted_sql)

        # Then check if the corruption is fixed
        verify_rows, verify_err = _run(env_conn, verify_sql)

        if verify_err:
            repair_results.append({
                "issue": c["affected_table"],
                "fixed": False,
                "detail": f"Verify query error: {verify_err}",
            })
            continue

        # Extract the count
        actual_val = None
        if verify_rows:
            for v in verify_rows[0].values():
                if isinstance(v, (int, float)):
                    actual_val = int(v)
                    break

        fixed = (actual_val is not None and actual_val == expected_val)
        repair_results.append({
            "issue": c["affected_table"],
            "fixed": fixed,
            "remaining": actual_val,
            "expected": expected_val,
        })

    repairs_done = sum(1 for r in repair_results if r["fixed"])
    stage3 = (repairs_done / max(len(corruptions), 1)) * 0.40
    score += stage3

    for r in repair_results:
        icon = "✓" if r["fixed"] else "✗"
        remaining = r.get("remaining", "?")
        details[f"stage3_{r['issue']}"] = (
            f"{icon} {r['issue']}: {'fixed' if r['fixed'] else f'still {remaining} corrupt rows'}"
        )

    # ── Stage 4: VERIFY — explicit verification queries present (15%) ────────
    stage4 = 0.0
    # Check if the submission includes verify-style queries (SELECT COUNT from affected tables)
    verify_hits = 0
    for c in corruptions:
        table = c["affected_table"].upper()
        if "SELECT" in sql_up and "COUNT" in sql_up and table in sql_up:
            verify_hits += 1

    if repairs_done == len(corruptions):
        # Full repair → full verify credit
        stage4 = 0.15
        details["stage4_verify"] = "✓ All issues verified clean"
    elif verify_hits > 0:
        stage4 = 0.15 * (verify_hits / len(corruptions))
        details["stage4_verify"] = f"~ {verify_hits}/{len(corruptions)} verify queries present"
    else:
        details["stage4_verify"] = "✗ No verification queries found"
    score += stage4

    # ── Stage 5: PREVENT — prevention/monitoring SQL present (10%) ───────────
    stage5 = 0.0
    prevention_keywords = [
        "CONSTRAINT", "CHECK", "TRIGGER", "UNIQUE", "NOT NULL",
        "MONITORING", "ALERT", "DASHBOARD", "HAVING", "-- ADD"
    ]
    prevent_hits = sum(1 for kw in prevention_keywords if kw in sql_up)
    if prevent_hits >= 2:
        stage5 = 0.10
        details["stage5_prevent"] = f"✓ Prevention SQL present ({prevent_hits} prevention keywords)"
    elif prevent_hits == 1:
        stage5 = 0.05
        details["stage5_prevent"] = "~ Some prevention SQL present"
    else:
        # Partial credit if all repairs done
        if repairs_done == len(corruptions):
            stage5 = 0.03
        details["stage5_prevent"] = "✗ No prevention/monitoring SQL found"
    score += stage5

    # ── Bonus: perfect repair (all 3 fixed) ──────────────────────────────────
    if repairs_done == len(corruptions):
        details["bonus"] = "🌟 All corruptions repaired — full repair bonus applied"

    details["summary"] = (
        f"Diagnosed: {diagnosis_hits}/{len(corruptions)}  |  "
        f"Repaired: {repairs_done}/{len(corruptions)}  |  "
        f"Score: {score:.2f}/1.00"
    )
    details["feedback"] = f"Score: {score:.2f}/1.00"
    return round(min(score, 1.0), 4), details
