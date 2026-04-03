"""
demo.py — Gradio interactive demo for SQL Debug OpenEnv.

Runs alongside the FastAPI server on a separate port (7861) or can be
mounted into the FastAPI app. On HF Spaces, mount it into the main app.
"""

import json

import gradio as gr

from environment import SQLDebugEnv, Action
from tasks import TASKS

# ── Helpers ──────────────────────────────────────────────────────────────────

def _fmt_result(rows, error=None) -> str:
    if error:
        return f"❌ Error:\n{error}"
    if not rows:
        return "⚠️  Query returned 0 rows."
    # Table header
    cols = list(rows[0].keys())
    col_w = {c: max(len(c), max(len(str(r.get(c, ""))) for r in rows)) for c in cols}
    sep = "─" * (sum(col_w.values()) + 3 * len(cols) + 1)
    header = " │ ".join(c.ljust(col_w[c]) for c in cols)
    lines = [sep, header, sep]
    for row in rows[:20]:
        lines.append(" │ ".join(str(row.get(c, "")).ljust(col_w[c]) for c in cols))
    if len(rows) > 20:
        lines.append(f"  … {len(rows) - 20} more rows")
    lines.append(sep)
    return "\n".join(lines)


# ── Session store ────────────────────────────────────────────────────────────
_sessions: dict = {}


def get_env(session_id: str) -> SQLDebugEnv:
    if session_id not in _sessions:
        env = SQLDebugEnv()
        env.reset("fix_broken_query")
        _sessions[session_id] = env
    return _sessions[session_id]


# ── Gradio handlers ──────────────────────────────────────────────────────────

def start_task(task_id: str, session_id: str) -> tuple:
    env = SQLDebugEnv()
    obs = env.reset(task_id)
    _sessions[session_id] = env
    schema_info = []
    for tbl in obs.available_tables:
        rows, _ = env._execute(f"PRAGMA table_info({tbl})")
        col_names = [r["name"] for r in rows] if rows else []
        schema_info.append(f"📋 **{tbl}** ({', '.join(col_names)})")
    schema_str = "\n".join(schema_info)
    return (
        obs.task_description,
        schema_str,
        "✅ Task started! Write SQL below and click Run.",
        "",
        "Steps: 0 / 25    Reward: 0.00    Score: —"
    )


def run_sql(sql: str, action_type: str, session_id: str, stats: str) -> tuple:
    if not session_id or session_id not in _sessions:
        return "⚠️ Start a task first.", stats

    env = _sessions[session_id]
    if env._done:
        return "⚠️ Episode finished. Start a new task.", stats

    action = Action(action_type=action_type, sql=sql.strip() if sql.strip() else None)
    result = env.step(action)

    obs  = result.observation
    rew  = result.reward
    info = result.info

    # Format output
    if action_type == "submit_solution":
        score = info.get("score", 0.0)
        gd    = info.get("grading_details", {})
        bar   = "█" * int(score * 20) + "░" * (20 - int(score * 20))
        out   = f"🏁 SUBMISSION GRADED\n\nScore: {score:.4f}  [{bar}]\n\n"
        out  += "\n".join(f"  {k}: {v}" for k, v in gd.items())
        if info.get("result_preview"):
            out += "\n\nResult preview:\n" + _fmt_result(info["result_preview"])
    elif obs.last_error:
        out = _fmt_result([], obs.last_error)
    elif obs.last_result:
        r = obs.last_result
        if isinstance(r, list):
            out = _fmt_result(r)
        elif isinstance(r, dict):
            # schema info
            cols_info = r.get("columns", [])
            sample    = r.get("sample_rows", [])
            cnt       = r.get("row_count", "?")
            out  = f"📊 Schema ({cnt} rows):\n"
            if cols_info:
                out += _fmt_result(cols_info)
            if sample:
                out += f"\nSample rows:\n{_fmt_result(sample)}"
        else:
            out = str(r)
    else:
        out = rew.reason

    steps  = obs.step_count
    cumrew = sum(
        (r.reward.value if hasattr(r, "reward") else 0)
        for r in [result]
    )
    # parse previous cumulative reward from stats
    try:
        prev_rew = float(stats.split("Reward:")[1].split()[0])
    except Exception:
        prev_rew = 0.0

    score_str = f"{info['score']:.4f}" if action_type == "submit_solution" and "score" in info else "—"
    new_stats = (
        f"Steps: {steps} / 25    "
        f"Reward: {prev_rew + rew.value:.3f}    "
        f"Score: {score_str}"
    )
    return out, new_stats


# ── Build interface ──────────────────────────────────────────────────────────

TASK_CHOICES = [
    ("🟢 Easy — Fix the Broken SQL Query",        "fix_broken_query"),
    ("🟡 Medium — Write a Business Analytics Query", "write_business_query"),
    ("🔴 Hard — Complex Multi-table Analytics",   "complex_analytics"),
    ("🔴 Hard — Recursive Org-Chart Query",       "recursive_org_hierarchy"),
    ("🔴 Hard — Data Quality Audit Pipeline",     "data_quality_audit"),
]

ACTION_CHOICES = [
    ("examine_schema — inspect a table", "examine_schema"),
    ("run_query — test your SQL",         "run_query"),
    ("explain_query — see query plan",    "explain_query"),
    ("submit_solution — grade your answer", "submit_solution"),
]

CSS = """
#title { text-align: center; }
#stats_box { font-family: monospace; background: #1a1a2e; color: #00ff88;
             padding: 8px 16px; border-radius: 8px; font-size: 14px; }
#output_box { font-family: monospace; font-size: 13px; }
"""

def build_demo() -> gr.Blocks:
    import uuid

    with gr.Blocks(css=CSS, title="SQL Debug OpenEnv") as demo:
        session_state = gr.State(str(uuid.uuid4()))

        gr.Markdown("# 🛢️ SQL Debug OpenEnv\n"
                    "An interactive environment where AI agents learn to debug and write SQL.",
                    elem_id="title")

        with gr.Row():
            with gr.Column(scale=1):
                task_dd = gr.Dropdown(
                    choices=TASK_CHOICES, value="fix_broken_query",
                    label="Select Task", interactive=True
                )
                start_btn = gr.Button("▶ Start Task", variant="primary")
                stats_box = gr.Textbox(
                    value="Steps: 0 / 25    Reward: 0.00    Score: —",
                    label="Episode Stats", interactive=False, elem_id="stats_box"
                )
                schema_box = gr.Markdown("*Start a task to see the schema*", label="Schema")

            with gr.Column(scale=2):
                task_desc = gr.Textbox(
                    label="Task Description", lines=10,
                    interactive=False, placeholder="Start a task to see the description…"
                )
                sql_box = gr.Textbox(
                    label="Your SQL",
                    lines=8,
                    placeholder="SELECT ...",
                    interactive=True
                )
                action_dd = gr.Dropdown(
                    choices=ACTION_CHOICES, value="run_query",
                    label="Action Type", interactive=True
                )
                run_btn  = gr.Button("⚡ Execute Action", variant="primary")
                feedback = gr.Textbox(
                    label="Result / Feedback", lines=14,
                    interactive=False, elem_id="output_box"
                )

        # ── Wire up events ────────────────────────────────────────────────────
        start_btn.click(
            fn=start_task,
            inputs=[task_dd, session_state],
            outputs=[task_desc, schema_box, feedback, sql_box, stats_box],
        )
        run_btn.click(
            fn=run_sql,
            inputs=[sql_box, action_dd, session_state, stats_box],
            outputs=[feedback, stats_box],
        )

        gr.Markdown(
            "### How to use\n"
            "1. **Select a task** and click **▶ Start Task**\n"
            "2. Use `examine_schema` (put table name in SQL box) to inspect tables\n"
            "3. Use `run_query` to test your SQL iteratively\n"
            "4. When ready, switch to `submit_solution` and click Execute to get your score\n\n"
            "**Available tables per task:** shown in the Schema panel after starting.\n\n"
            "💡 *Tip: For `examine_schema`, type the table name (e.g. `customers`) in the SQL box.*"
        )

    return demo


# ── For examine_schema, accept table name in sql field ─────────────────────
_original_run_sql = run_sql

def run_sql(sql: str, action_type: str, session_id: str, stats: str) -> tuple:
    if action_type == "examine_schema":
        # Allow user to type just the table name in the SQL box
        table = sql.strip()
        if not table.upper().startswith("SELECT"):
            env = _sessions.get(session_id)
            if env:
                action = Action(action_type="examine_schema", table_name=table)
                result = env.step(action)
                obs = result.observation
                rew = result.reward
                r   = obs.last_result
                if obs.last_error:
                    out = f"❌ {obs.last_error}"
                elif isinstance(r, dict):
                    cols_info = r.get("columns", [])
                    sample    = r.get("sample_rows", [])
                    cnt       = r.get("row_count", "?")
                    out  = f"📊 **{table}** schema ({cnt} rows):\n"
                    out += _fmt_result(cols_info) if cols_info else ""
                    out += f"\nSample rows:\n{_fmt_result(sample)}" if sample else ""
                else:
                    out = str(r)
                try:
                    prev_rew = float(stats.split("Reward:")[1].split()[0])
                except Exception:
                    prev_rew = 0.0
                new_stats = (
                    f"Steps: {obs.step_count} / 25    "
                    f"Reward: {prev_rew + rew.value:.3f}    Score: —"
                )
                return out, new_stats
    return _original_run_sql(sql, action_type, session_id, stats)


if __name__ == "__main__":
    demo = build_demo()
    demo.launch(server_name="0.0.0.0", server_port=7861)
