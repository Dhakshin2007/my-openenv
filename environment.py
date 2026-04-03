"""
environment.py — SQL Debug OpenEnv (v3)

Major upgrades:
  • Procedural task generation  — unique DB per episode, agents must generalise
  • Performance grading         — rewards query efficiency (index usage)
  • Adaptive curriculum         — tracks rolling performance, auto-adjusts difficulty
  • Incident Response task      — multi-stage expert-level production DB repair
  • explain_query action        — exposes EXPLAIN QUERY PLAN to the agent
  • Richer reward shaping       — step efficiency, exploration bonus, error doubling
"""

import random
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from tasks import TASKS
from graders import grade
from incident_task import get_incident_task
from incident_grader import grade_incident_response
from generator import get_variant


# ═══════════════════════════════════════════════════════════════════════════
# Progressive Hint Bank  (costs -0.15 per hint, encourages self-reliance)
# ═══════════════════════════════════════════════════════════════════════════

HINTS: Dict[str, List[str]] = {
    "fix_broken_query": [
        "Hint 1: The table alias in FROM/JOIN is misspelled — use a simple alias like 'c'.",
        "Hint 2: The JOIN condition uses a wrong column name for the foreign key — it should be 'customer_id'.",
        "Hint 3: The WHERE clause has a typo in the column name — it should be 'status'.",
        "Hint 4: ORDER BY direction is wrong — use 'DESC' not a typo.",
    ],
    "write_business_query": [
        "Hint 1: Use GROUP BY d.id with HAVING COUNT(e.id) > 1 to exclude single-employee depts.",
        "Hint 2: Get the top earner with a correlated subquery: (SELECT name FROM employees WHERE department_id=d.id ORDER BY salary DESC LIMIT 1).",
        "Hint 3: Use ROUND(AVG(e.salary), 2) for the average salary column.",
        "Hint 4: Final ORDER BY avg_salary DESC.",
    ],
    "complex_analytics": [
        "Hint 1: Filter 2023 data with WHERE s.sale_date LIKE '2023-%'.",
        "Hint 2: Use a CTE to compute SUM(quantity * unit_price) grouped by country + category.",
        "Hint 3: Add ROW_NUMBER() OVER (PARTITION BY country ORDER BY total_revenue DESC) AS rn.",
        "Hint 4: Outer query: SELECT ... FROM ranked WHERE rn <= 2.",
    ],
    "recursive_org_hierarchy": [
        "Hint 1: Start anchor: SELECT id, name, title, manager_id, 0 AS depth FROM employees WHERE id=1.",
        "Hint 2: Recursive step: JOIN employees ON e.manager_id = cte.id, depth+1.",
        "Hint 3: LEFT JOIN projects ON lead_id=cte.id AND status='active' to count projects.",
        "Hint 4: Use COALESCE(COUNT(p.id), 0) and GROUP BY employee id.",
    ],
    "data_quality_audit": [
        "Hint 1: Use UNION ALL with 5 SELECT blocks, one per issue type.",
        "Hint 2: Duplicate emails: GROUP BY email HAVING COUNT(*)>1, then pick non-minimum ids.",
        "Hint 3: Orphan txns: LEFT JOIN customers ON customer_id=id WHERE customer.id IS NULL.",
        "Hint 4: Use GROUP_CONCAT(id) for the example_ids column in each block.",
    ],
    "query_optimizer": [
        "Hint 1: Replace all correlated subqueries with a single JOIN to orders + GROUP BY u.id.",
        "Hint 2: Move the count filter to HAVING COUNT(CASE WHEN status='completed' THEN 1 END) > 2.",
        "Hint 3: Compute total_spent as SUM(CASE WHEN o.status='completed' THEN o.amount END).",
        "Hint 4: Keep WHERE u.status='active' AND u.country IN ('USA','Canada') on the users table.",
    ],
    "nl_to_sql": [
        "Hint 1: JOIN all 4 tables: employees → LEFT JOIN performance_reviews (review_year=2023) → LEFT JOIN project_assignments → LEFT JOIN projects.",
        "Hint 2: Company-wide avg subquery: (SELECT AVG(score) FROM performance_reviews WHERE review_year=2023).",
        "Hint 3: above_avg_count: COUNT(CASE WHEN pr.score > (company_avg) THEN 1 END).",
        "Hint 4: HAVING COUNT(e.id) >= 3 to exclude small departments. ORDER BY avg_score DESC.",
    ],
    "transaction_deadlock": [
        "Hint 1: overdraft — WHERE a.balance < (SELECT COALESCE(SUM(amount),0) FROM transactions WHERE from_account=a.id AND status='completed').",
        "Hint 2: unreleased_lock — COUNT(*) FROM locks WHERE released_at IS NULL.",
        "Hint 3: duplicate_txn — self-join: t1 JOIN t2 ON same from/to/amount AND t1.id < t2.id AND time diff < 60s using julianday().",
        "Hint 4: self_transfer — from_account=to_account; large_transfer — amount > 10000.",
    ],
}


# ═══════════════════════════════════════════════════════════════════════════
# Typed Pydantic Models
# ═══════════════════════════════════════════════════════════════════════════

class Observation(BaseModel):
    task_id: str
    task_description: str
    available_tables: List[str]
    last_result: Optional[Any] = None
    last_error: Optional[str] = None
    query_history: List[Dict[str, Any]] = Field(default_factory=list)
    step_count: int = 0
    done: bool = False
    message: str = ""
    episode_seed: Optional[int] = None
    performance_hint: Optional[str] = None


class Action(BaseModel):
    action_type: str   # examine_schema | run_query | explain_query | submit_solution
    table_name: Optional[str] = None
    sql: Optional[str] = None


class Reward(BaseModel):
    value: float
    breakdown: Dict[str, float] = Field(default_factory=dict)
    reason: str


class StepResult(BaseModel):
    observation: Observation
    reward: Reward
    done: bool
    info: Dict[str, Any] = Field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════════
# Adaptive Curriculum Tracker
# ═══════════════════════════════════════════════════════════════════════════

class CurriculumTracker:
    """
    Tracks agent performance and recommends next difficulty.
    Promotes when EMA >= 0.75 over 3 episodes; demotes when EMA < 0.35.
    """
    LEVELS            = ["easy", "medium", "hard", "expert"]
    PROMOTE_THRESHOLD = 0.75
    DEMOTE_THRESHOLD  = 0.35
    EMA_ALPHA         = 0.4

    def __init__(self) -> None:
        self._ema      = {l: 0.5 for l in self.LEVELS}
        self._episodes = {l: 0   for l in self.LEVELS}
        self._current  = "easy"

    def record(self, difficulty: str, score: float) -> None:
        if difficulty not in self._ema:
            return
        self._ema[difficulty] = (
            self.EMA_ALPHA * score + (1 - self.EMA_ALPHA) * self._ema[difficulty]
        )
        self._episodes[difficulty] += 1
        self._adapt()

    def _adapt(self) -> None:
        idx = self.LEVELS.index(self._current)
        ema = self._ema[self._current]
        eps = self._episodes[self._current]
        if eps >= 3 and ema >= self.PROMOTE_THRESHOLD and idx < len(self.LEVELS) - 1:
            self._current = self.LEVELS[idx + 1]
        elif eps >= 2 and ema < self.DEMOTE_THRESHOLD and idx > 0:
            self._current = self.LEVELS[idx - 1]

    @property
    def recommended_difficulty(self) -> str:
        return self._current

    def stats(self) -> Dict[str, Any]:
        return {
            "current_level":      self._current,
            "ema_scores":         {k: round(v, 3) for k, v in self._ema.items()},
            "episodes_per_level": dict(self._episodes),
        }


# ═══════════════════════════════════════════════════════════════════════════
# Environment
# ═══════════════════════════════════════════════════════════════════════════

class SQLDebugEnv:
    """
    SQL Debug & Analytics OpenEnv — v3

    Reward shaping:
      Every step:            -0.01
      examine_schema:        +0.03
      run_query (success):   +0.05
      run_query (error):     -0.05  (×2 after 3 consecutive errors)
      explain_query:         +0.02
      submit_solution:       grader score + up to +0.05 efficiency bonus
      max_steps penalty:     -0.10
    """

    MAX_STEPS = 25

    def __init__(self, curriculum: Optional[CurriculumTracker] = None) -> None:
        self._conn:               Optional[sqlite3.Connection] = None
        self._task:               Optional[Dict]               = None
        self._obs:                Optional[Observation]        = None
        self._step_count:         int                          = 0
        self._done:               bool                         = False
        self._query_history:      List[Dict]                   = []
        self._cumulative_reward:  float                        = 0.0
        self._consecutive_errors: int                          = 0
        self._hints_used:         int                          = 0
        self._episode_seed:       Optional[int]                = None
        self._is_incident:        bool                         = False
        self._incident_def:       Optional[Dict]               = None
        self.curriculum:          CurriculumTracker            = curriculum or CurriculumTracker()

    # ── Public API ────────────────────────────────────────────────────────

    def reset(
        self,
        task_id: str = "fix_broken_query",
        seed: Optional[int] = None,
        procedural: bool = True,
    ) -> Observation:
        """
        Start a new episode.

        task_id special values:
          'auto'           → curriculum auto-selects difficulty
          'incident_alpha' → Black Friday incident scenario
          'incident_beta'  → ETL pipeline incident scenario
        """
        if task_id == "auto":
            task_id = self._pick_task_by_difficulty(
                self.curriculum.recommended_difficulty
            )

        self._is_incident  = task_id.startswith("incident_")
        self._episode_seed = seed if seed is not None else random.randint(0, 99999)

        if self._is_incident:
            self._incident_def = get_incident_task(task_id)
            self._task = self._incident_def
        else:
            if task_id not in TASKS:
                task_id = "fix_broken_query"
            self._task = dict(TASKS[task_id])
            if procedural:
                variant = get_variant(task_id, self._episode_seed)
                if variant:
                    if "seed_data" in variant:
                        self._task = {**self._task, "seed_data": variant["seed_data"]}
                    if "description_suffix" in variant:
                        base = self._task["description"].split("THE BROKEN QUERY")[0]
                        self._task = {**self._task,
                                      "description": base + variant["description_suffix"]}
                    self._task["_variant"] = variant

        self._conn                = self._build_db(self._task)
        self._step_count          = 0
        self._done                = False
        self._cumulative_reward   = 0.0
        self._consecutive_errors  = 0
        self._hints_used          = 0
        self._query_history       = []

        self._obs = Observation(
            task_id=self._task["id"],
            task_description=self._task["description"],
            available_tables=list(self._task["schema"].keys()),
            episode_seed=self._episode_seed,
            message=(
                f"Episode started (seed={self._episode_seed}). "
                "Each episode has a unique dataset. "
                "examine_schema → run_query → submit_solution"
            ),
        )
        return self._obs

    def step(self, action: Action) -> StepResult:
        if self._done or self._task is None:
            return StepResult(
                observation=self._obs,
                reward=Reward(value=0.0, reason="Episode finished — call reset()"),
                done=True,
                info={"error": "Episode finished"},
            )

        self._step_count += 1
        base_cost = -0.01

        dispatch = {
            "examine_schema":  self._do_examine_schema,
            "run_query":       self._do_run_query,
            "explain_query":   self._do_explain_query,
            "request_hint":    self._do_request_hint,
            "submit_solution": self._do_submit,
        }
        handler = dispatch.get(action.action_type)
        if handler is None:
            delta, reason, info = -0.05, f"Unknown action '{action.action_type}'", {
                "error": f"Unknown action. Valid: {list(dispatch.keys())}"
            }
        else:
            delta, reason, info = handler(action)

        reward_val = base_cost + delta
        self._cumulative_reward += reward_val

        if self._step_count >= self.MAX_STEPS and not self._done:
            self._done  = True
            reward_val -= 0.10
            reason     += " | Max steps reached."

        self._obs = Observation(
            task_id=self._task["id"],
            task_description=self._task["description"],
            available_tables=list(self._task["schema"].keys()),
            last_result=info.get("result"),
            last_error=info.get("error"),
            query_history=self._query_history[-5:],
            step_count=self._step_count,
            done=self._done,
            episode_seed=self._episode_seed,
            message=reason,
            performance_hint=info.get("performance_hint"),
        )
        return StepResult(
            observation=self._obs,
            reward=Reward(value=round(reward_val, 4), reason=reason,
                          breakdown=info.get("reward_breakdown", {})),
            done=self._done,
            info=info,
        )

    def state(self) -> Observation:
        if self._obs is None:
            raise RuntimeError("Call reset() before state()")
        return self._obs

    def curriculum_stats(self) -> Dict[str, Any]:
        return self.curriculum.stats()

    # ── DB builder ────────────────────────────────────────────────────────

    @staticmethod
    def _build_db(task: Dict) -> sqlite3.Connection:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        cur  = conn.cursor()
        cur.executescript("PRAGMA foreign_keys = OFF;")  # allow incident injections
        for ddl in task["schema"].values():
            cur.execute(ddl)
        for dml in task.get("seed_data", []):
            try:
                cur.execute(dml)
            except Exception:
                pass
        conn.commit()
        return conn

    def _execute(self, sql: str) -> Tuple[Optional[List[Dict]], Optional[str]]:
        try:
            cur     = self._conn.cursor()
            results = []
            for stmt in sql.split(";"):
                stmt = stmt.strip()
                if stmt:
                    cur.execute(stmt)
                    if cur.description:
                        cols    = [d[0] for d in cur.description]
                        results = [dict(zip(cols, row)) for row in cur.fetchall()]
            self._conn.commit()
            return results, None
        except Exception as exc:
            return None, str(exc)

    # ── Performance analyser ─────────────────────────────────────────────

    def _analyse_performance(self, sql: str) -> Tuple[float, str]:
        try:
            cur = self._conn.cursor()
            cur.execute(f"EXPLAIN QUERY PLAN {sql}")
            plan_rows = cur.fetchall()
            plan_text = " ".join(
                str(dict(zip([d[0] for d in cur.description], r)).get("detail", ""))
                for r in plan_rows
            ).upper()
            scans  = plan_text.count("SCAN")
            seeks  = plan_text.count("SEARCH") + plan_text.count("INDEX")
            if scans == 0 or seeks > scans:
                return 0.05, f"⚡ Efficient ({seeks} index seeks, {scans} scans)"
            elif scans <= 2:
                return 0.02, f"~ Acceptable ({scans} table scan(s))"
            else:
                return 0.0,  f"⚠ Slow ({scans} full table scans)"
        except Exception:
            return 0.0, ""

    # ── Action handlers ──────────────────────────────────────────────────

    def _do_examine_schema(self, action: Action) -> Tuple[float, str, Dict]:
        tbl = action.table_name or (action.sql or "").strip()
        if not tbl or tbl not in self._task["schema"]:
            avail = list(self._task["schema"].keys())
            return -0.02, f"Table '{tbl}' not found. Available: {avail}", {
                "error": f"Available tables: {avail}"
            }
        schema_rows, _ = self._execute(f"PRAGMA table_info({tbl})")
        sample_rows,  _ = self._execute(f"SELECT * FROM {tbl} LIMIT 3")
        count_rows,   _ = self._execute(f"SELECT COUNT(*) AS cnt FROM {tbl}")
        row_count = count_rows[0]["cnt"] if count_rows else "?"
        self._query_history.append({"action": "examine_schema", "table": tbl})
        return 0.03, f"Schema '{tbl}' ({row_count} rows)", {
            "result": {"columns": schema_rows, "sample_rows": sample_rows,
                       "row_count": row_count}
        }

    def _do_explain_query(self, action: Action) -> Tuple[float, str, Dict]:
        if not action.sql:
            return -0.02, "explain_query needs sql", {"error": "Provide sql"}
        rows, err = self._execute(f"EXPLAIN QUERY PLAN {action.sql}")
        self._query_history.append({"action": "explain_query", "sql": action.sql[:80]})
        if err:
            return -0.02, f"Explain error: {err}", {"error": err}
        return 0.02, "Query plan retrieved", {"result": rows}

    def _do_run_query(self, action: Action) -> Tuple[float, str, Dict]:
        if not action.sql:
            return -0.02, "run_query needs sql", {"error": "Provide sql"}
        rows, err = self._execute(action.sql)
        self._query_history.append({"action": "run_query", "sql": action.sql[:120]})
        if err:
            self._consecutive_errors += 1
            penalty = -0.05 * (2 if self._consecutive_errors >= 3 else 1)
            return penalty, f"Query error: {err}", {"error": err}
        self._consecutive_errors = 0
        return 0.05, f"Query OK — {len(rows)} row(s)", {"result": rows[:10]}

    def _do_submit(self, action: Action) -> Tuple[float, str, Dict]:
        if not action.sql:
            return -0.10, "submit_solution needs sql", {"error": "Provide sql"}
        self._done = True

        # ── Incident task ─────────────────────────────────────────────────
        if self._is_incident and self._incident_def:
            score, grading = grade_incident_response(
                action.sql, self._incident_def, self._conn
            )
            self.curriculum.record("expert", score)
            return score, f"Incident graded. Score: {score:.4f}.", {
                "score": score, "grading_details": grading,
                "curriculum": self.curriculum.stats(),
            }

        # ── Standard tasks ─────────────────────────────────────────────────
        rows, err = self._execute(action.sql)
        if err:
            self.curriculum.record(self._task.get("difficulty", "easy"), 0.0)
            return -0.20, f"Submission errored: {err}", {
                "error": err, "score": 0.0,
                "grading_details": {"feedback": f"Error: {err}"},
            }

        score, grading = grade(self._task["id"], rows or [], action.sql)

        # ── Performance bonus (only if correct) ───────────────────────────
        eff_bonus, perf_hint = 0.0, ""
        if score >= 0.70:
            first = next(
                (s.strip() for s in action.sql.split(";") if "SELECT" in s.upper()), None
            )
            if first:
                eff_bonus, perf_hint = self._analyse_performance(first)
                if eff_bonus > 0:
                    grading["performance"] = perf_hint

        final = min(score + eff_bonus, 1.0)
        self.curriculum.record(self._task.get("difficulty", "easy"), score)

        return final, (
            f"Graded. Score={final:.4f} (base={score:.4f} + eff={eff_bonus:.4f}). "
            f"{grading.get('feedback','')}"
        ), {
            "score":            round(final, 4),
            "base_score":       round(score, 4),
            "efficiency_bonus": round(eff_bonus, 4),
            "performance_hint": perf_hint,
            "grading_details":  grading,
            "result_preview":   (rows or [])[:5],
            "curriculum":       self.curriculum.stats(),
        }

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _pick_task_by_difficulty(difficulty: str) -> str:
        return {
            "easy":   "fix_broken_query",
            "medium": "write_business_query",
            "hard":   "complex_analytics",
            "expert": "incident_alpha",
        }.get(difficulty, "fix_broken_query")


    def _do_request_hint(self, action=None) -> tuple:
        task_hints = HINTS.get(self._task["id"], [])
        if not task_hints:
            return -0.05, "No hints for this task.", {"hint": None, "hints_used": 0, "hints_remaining": 0}
        idx  = min(self._hints_used, len(task_hints) - 1)
        hint = task_hints[idx]
        self._hints_used += 1
        self._query_history.append({"action": "request_hint", "hint_index": idx})
        return -0.15, f"Hint {idx+1}/{len(task_hints)}: {hint}", {
            "hint":            hint,
            "hints_used":      self._hints_used,
            "hints_remaining": max(0, len(task_hints) - self._hints_used),
        }
