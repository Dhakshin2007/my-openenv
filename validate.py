"""
validate.py — Pre-submission validation script.

Runs all checks that the automated judge will run.
All checks must pass before you submit.

Usage:
  # Validate local environment only (no server required):
  python validate.py

  # Validate against a running server:
  python validate.py --url http://localhost:7860

  # Validate against deployed HF Space:
  python validate.py --url https://<user>-sql-debug-env.hf.space
"""

import argparse
import importlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).parent
PASS = "  ✅ PASS"
FAIL = "  ❌ FAIL"
WARN = "  ⚠️  WARN"


def check(label: str, ok: bool, detail: str = "") -> bool:
    icon = PASS if ok else FAIL
    msg = f"{icon}  {label}"
    if detail:
        msg += f"\n       {detail}"
    print(msg)
    return ok


def section(title: str) -> None:
    print(f"\n{'─'*55}")
    print(f"  {title}")
    print(f"{'─'*55}")


# ──────────────────────────────────────────────────────────────
# 1. File presence
# ──────────────────────────────────────────────────────────────
def check_files() -> bool:
    section("1. Required files present")
    required = [
        "main.py",
        "environment.py",
        "tasks.py",
        "graders.py",
        "inference.py",
        "openenv.yaml",
        "Dockerfile",
        "requirements.txt",
        "README.md",
    ]
    all_ok = True
    for f in required:
        exists = (ROOT / f).exists()
        all_ok &= check(f, exists)
    return all_ok


# ──────────────────────────────────────────────────────────────
# 2. inference.py location check
# ──────────────────────────────────────────────────────────────
def check_inference_location() -> bool:
    section("2. inference.py in root directory")
    ok = (ROOT / "inference.py").exists()
    return check("inference.py at project root", ok)


# ──────────────────────────────────────────────────────────────
# 3. openenv.yaml validity
# ──────────────────────────────────────────────────────────────
def check_yaml() -> bool:
    section("3. openenv.yaml structure")
    try:
        import yaml  # type: ignore
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "pyyaml", "-q"],
                       capture_output=True)
        import yaml  # type: ignore

    yaml_path = ROOT / "openenv.yaml"
    if not yaml_path.exists():
        return check("openenv.yaml", False, "File missing")

    with open(yaml_path) as fh:
        data = yaml.safe_load(fh)

    required_keys = ["name", "version", "tasks", "action_space",
                     "observation_space", "reward", "endpoints"]
    all_ok = True
    for k in required_keys:
        ok = k in data
        all_ok &= check(f"  field '{k}'", ok)

    tasks = data.get("tasks", [])
    all_ok &= check(f"  ≥3 tasks defined", len(tasks) >= 3,
                    f"Found {len(tasks)}")

    difficulties = {t.get("difficulty") for t in tasks}
    has_all = {"easy", "medium", "hard"} <= difficulties
    all_ok &= check("  easy/medium/hard difficulty levels", has_all,
                    f"Found: {difficulties}")

    return all_ok


# ──────────────────────────────────────────────────────────────
# 4. OpenEnv Python spec compliance
# ──────────────────────────────────────────────────────────────
def check_spec() -> bool:
    section("4. OpenEnv Python spec compliance")
    all_ok = True

    # Typed Pydantic models
    try:
        from environment import Action, Observation, Reward, StepResult
        all_ok &= check("Observation Pydantic model", True)
        all_ok &= check("Action Pydantic model", True)
        all_ok &= check("Reward Pydantic model", True)
        all_ok &= check("StepResult Pydantic model", True)
    except ImportError as exc:
        all_ok &= check("Pydantic models importable", False, str(exc))
        return all_ok

    # Interface methods
    try:
        from environment import SQLDebugEnv
        env = SQLDebugEnv()
        has_reset = callable(getattr(env, "reset", None))
        has_step  = callable(getattr(env, "step",  None))
        has_state = callable(getattr(env, "state", None))
        all_ok &= check("env.reset() exists", has_reset)
        all_ok &= check("env.step()  exists", has_step)
        all_ok &= check("env.state() exists", has_state)
    except Exception as exc:
        all_ok &= check("SQLDebugEnv importable", False, str(exc))
        return all_ok

    return all_ok


# ──────────────────────────────────────────────────────────────
# 5. Grader correctness — 3 tasks
# ──────────────────────────────────────────────────────────────
def check_graders() -> bool:
    section("5. Graders: 3 tasks, scores ∈ [0.0, 1.0]")
    all_ok = True

    try:
        from environment import SQLDebugEnv, Action
        from graders import grade
        from tasks import TASKS
    except ImportError as exc:
        return check("modules importable", False, str(exc))

    correct_sqls = {
        "fix_broken_query": (
            "SELECT c.name, c.email, SUM(o.total_amount) as total_spent "
            "FROM customers c INNER JOIN orders o ON c.id = o.customer_id "
            "WHERE o.status = 'completed' GROUP BY c.id ORDER BY total_spent DESC"
        ),
        "write_business_query": (
            "SELECT d.name, COUNT(e.id) as emp_count, "
            "ROUND(AVG(e.salary),2) as avg_salary, "
            "(SELECT e2.name FROM employees e2 "
            "WHERE e2.department_id = d.id ORDER BY e2.salary DESC LIMIT 1) as top_earner "
            "FROM departments d JOIN employees e ON e.department_id = d.id "
            "GROUP BY d.id HAVING COUNT(e.id) > 1 ORDER BY avg_salary DESC"
        ),
        "complex_analytics": (
            "WITH base AS (SELECT r.country, p.category, "
            "SUM(s.quantity * p.unit_price) AS total_revenue, "
            "SUM(s.quantity) AS total_units_sold, COUNT(*) AS num_transactions "
            "FROM sales s JOIN products p ON s.product_id = p.id "
            "JOIN regions r ON s.region_id = r.id "
            "WHERE s.sale_date LIKE '2023-%' GROUP BY r.country, p.category), "
            "ranked AS (SELECT *, ROW_NUMBER() OVER "
            "(PARTITION BY country ORDER BY total_revenue DESC) AS rn FROM base) "
            "SELECT country, category, total_revenue, total_units_sold, num_transactions "
            "FROM ranked WHERE rn <= 2 ORDER BY country, total_revenue DESC"
        ),
    }

    for task_id, sql in correct_sqls.items():
        env = SQLDebugEnv()
        env.reset(task_id, procedural=False)
        rows, err = env._execute(sql)
        if err:
            all_ok &= check(f"  {task_id} — query runs", False, err)
            continue
        score, details = grade(task_id, rows or [], sql)
        in_range = 0.0 <= score <= 1.0
        all_ok &= check(f"  {task_id} — score in [0,1]", in_range, f"score={score}")
        all_ok &= check(f"  {task_id} — correct sol scores ≥0.90", score >= 0.90,
                        f"score={score:.4f}")
        # Broken solution (empty sql, empty rows) should score low
        broken_score, _ = grade(task_id, [], "")
        all_ok &= check(f"  {task_id} — empty sql+rows scores <0.3", broken_score < 0.30,
                        f"empty_score={broken_score:.4f}")

    return all_ok


# ──────────────────────────────────────────────────────────────
# 6. Full episode smoke-test
# ──────────────────────────────────────────────────────────────
def check_episode() -> bool:
    section("6. Full episode smoke test")
    all_ok = True

    try:
        from environment import SQLDebugEnv, Action
    except ImportError as exc:
        return check("environment importable", False, str(exc))

    env = SQLDebugEnv()
    obs = env.reset("fix_broken_query", procedural=False)
    all_ok &= check("reset() returns Observation", obs.task_id == "fix_broken_query")
    all_ok &= check("step_count starts at 0", obs.step_count == 0)
    all_ok &= check("done starts False", not obs.done)

    r = env.step(Action(action_type="examine_schema", table_name="customers"))
    all_ok &= check("examine_schema reward > 0",  r.reward.value > 0,
                    f"reward={r.reward.value}")
    all_ok &= check("step_count increments",       r.observation.step_count == 1)
    all_ok &= check("episode not done yet",        not r.done)

    sql = ("SELECT c.name, c.email, SUM(o.total_amount) as total_spent "
           "FROM customers c INNER JOIN orders o ON c.id = o.customer_id "
           "WHERE o.status = 'completed' GROUP BY c.id ORDER BY total_spent DESC")
    r2 = env.step(Action(action_type="submit_solution", sql=sql))
    all_ok &= check("submit ends episode",  r2.done)
    all_ok &= check("score in info dict",   "score" in r2.info)
    score = r2.info.get("score", -1)
    all_ok &= check(f"grader score ≥ 0.9 (got {score:.4f})", score >= 0.9)

    # state() after done
    s = env.state()
    all_ok &= check("state() returns done=True after episode", s.done)

    return all_ok


# ──────────────────────────────────────────────────────────────
# 7. Server API check (optional)
# ──────────────────────────────────────────────────────────────
def check_server(base_url: str) -> bool:
    section(f"7. Live server API check  ({base_url})")
    all_ok = True

    def get(path):
        return requests.get(f"{base_url}{path}", timeout=15)

    def post(path, **kw):
        return requests.post(f"{base_url}{path}", timeout=15, **kw)

    # Health
    try:
        r = get("/health")
        all_ok &= check("/health → 200", r.status_code == 200)
    except Exception as exc:
        all_ok &= check("/health reachable", False, str(exc))
        print(f"\n  {WARN}  Cannot reach server — skipping remaining server checks")
        return all_ok

    # Tasks list
    r = get("/tasks")
    all_ok &= check("/tasks → 200", r.status_code == 200)
    tasks = r.json().get("tasks", [])
    all_ok &= check(f"/tasks returns ≥3 tasks", len(tasks) >= 3, f"got {len(tasks)}")

    # openenv.yaml
    r = get("/openenv.yaml")
    all_ok &= check("/openenv.yaml served", r.status_code == 200)

    # Reset
    r = post("/reset", params={"task_id": "fix_broken_query"})
    all_ok &= check("POST /reset → 200", r.status_code == 200)
    data = r.json()
    session_id = data.get("session_id")
    all_ok &= check("reset returns session_id", bool(session_id))
    all_ok &= check("reset returns observation", "observation" in data)

    if not session_id:
        return all_ok

    # Step
    r = post(f"/step/{session_id}",
             json={"action_type": "examine_schema", "table_name": "customers"})
    all_ok &= check("POST /step → 200", r.status_code == 200)

    # State
    r = get(f"/state/{session_id}")
    all_ok &= check("GET /state → 200", r.status_code == 200)

    # Submit
    sql = ("SELECT c.name, c.email, SUM(o.total_amount) as total_spent "
           "FROM customers c INNER JOIN orders o ON c.id = o.customer_id "
           "WHERE o.status = 'completed' GROUP BY c.id ORDER BY total_spent DESC")
    r = post(f"/step/{session_id}", json={"action_type": "submit_solution", "sql": sql})
    all_ok &= check("POST /step submit → 200", r.status_code == 200)
    info = r.json().get("info", {})
    score = info.get("score", -1)
    all_ok &= check(f"submit score ≥ 0.9 (got {score:.4f})", score >= 0.9)
    all_ok &= check("done=True after submit", r.json().get("done", False))

    return all_ok


# ──────────────────────────────────────────────────────────────
# 8. Dockerfile present and syntactically valid
# ──────────────────────────────────────────────────────────────
def check_dockerfile() -> bool:
    section("8. Dockerfile checks")
    all_ok = True
    df = ROOT / "Dockerfile"
    all_ok &= check("Dockerfile exists", df.exists())
    if not df.exists():
        return all_ok

    content = df.read_text()
    all_ok &= check("FROM instruction present",  "FROM" in content)
    all_ok &= check("EXPOSE 7860 present",        "7860" in content)
    all_ok &= check("CMD / ENTRYPOINT present",
                    "CMD" in content or "ENTRYPOINT" in content)
    all_ok &= check("requirements.txt referenced", "requirements.txt" in content)
    return all_ok


# ──────────────────────────────────────────────────────────────
# main
# ──────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Pre-submission validation")
    parser.add_argument("--url", default=None,
                        help="Base URL of running server (e.g. http://localhost:7860)")
    args = parser.parse_args()

    print("=" * 55)
    print("  SQL Debug OpenEnv — Pre-Submission Validation")
    print("=" * 55)

    checkers = [
        check_files,
        check_inference_location,
        check_yaml,
        check_spec,
        check_graders,
        check_episode,
        check_dockerfile,
    ]

    all_pass = True
    for fn in checkers:
        try:
            ok = fn()
        except Exception as exc:
            print(f"  ❌ EXCEPTION in {fn.__name__}: {exc}")
            ok = False
        all_pass = all_pass and ok

    if args.url:
        try:
            ok = check_server(args.url)
        except Exception as exc:
            print(f"  ❌ EXCEPTION in check_server: {exc}")
            ok = False
        all_pass = all_pass and ok

    print("\n" + "=" * 55)
    if all_pass:
        print("  🎉  ALL CHECKS PASSED — ready to submit!")
    else:
        print("  ❌  SOME CHECKS FAILED — fix before submitting.")
    print("=" * 55)
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
