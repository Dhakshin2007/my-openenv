"""
SQL Debug Environment — FastAPI server.

OpenEnv REST API:
  POST /reset?task_id=...            → {session_id, observation}
  POST /step/{session_id}            → StepResult
  GET  /state/{session_id}           → Observation
  GET  /tasks                        → task list
  GET  /health                       → {status}
  GET  /openenv.yaml                 → serves the openenv.yaml spec file
"""

import os
import uuid
from collections import defaultdict
from typing import Dict, List, Optional

import gradio as gr
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from demo import build_demo
from environment import Action, SQLDebugEnv

app = FastAPI(
    title="SQL Debug OpenEnv",
    description=(
        "A real-world environment where AI agents learn to debug and write SQL queries. "
        "Supports the OpenEnv step()/reset()/state() interface."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory session store  { session_id -> SQLDebugEnv }
_sessions: Dict[str, SQLDebugEnv] = {}

# Leaderboard: { task_id -> [ {score, steps, session_id} ] } top-10 per task
_leaderboard: Dict[str, List[Dict]] = defaultdict(list)


# ═══════════════════════════════════════════════════════════════════════════
# OpenEnv Endpoints
# ═══════════════════════════════════════════════════════════════════════════

@app.post("/reset", summary="Start a new episode")
async def reset(task_id: Optional[str] = "fix_broken_query"):
    """
    Reset the environment for *task_id* and return the initial observation.
    Also returns a *session_id* that must be passed to /step and /state.

    Available task_ids:
      - fix_broken_query   (easy)
      - write_business_query (medium)
      - complex_analytics  (hard)
    """
    env = SQLDebugEnv()
    obs = env.reset(task_id=task_id or "fix_broken_query")
    session_id = str(uuid.uuid4())
    _sessions[session_id] = env
    return {"session_id": session_id, "observation": obs.model_dump()}


@app.post("/step/{session_id}", summary="Execute one action")
async def step(session_id: str, action: Action):
    """
    Execute *action* in the environment identified by *session_id*.

    Action types:
      - examine_schema   → inspect a table (requires table_name)
      - run_query        → run arbitrary SQL (requires sql)
      - submit_solution  → submit final answer for grading (requires sql)
    """
    env = _get_session(session_id)
    result = env.step(action)
    if result.done:
        # Record to leaderboard if it was a submission with a score
        score = result.info.get("score")
        if score is not None:
            task_id = result.observation.task_id
            entry = {
                "score": score,
                "steps": result.observation.step_count,
                "session_id": session_id[:8],
            }
            board = _leaderboard[task_id]
            board.append(entry)
            board.sort(key=lambda x: (-x["score"], x["steps"]))
            _leaderboard[task_id] = board[:10]  # keep top 10
        _sessions.pop(session_id, None)
    return result.model_dump()


@app.get("/leaderboard", summary="Top scores per task")
async def leaderboard(task_id: Optional[str] = None):
    """Return top-10 scores for each task (or a specific task if task_id given)."""
    if task_id:
        return {"task_id": task_id, "top_scores": _leaderboard.get(task_id, [])}
    return {
        "leaderboard": {
            tid: entries for tid, entries in _leaderboard.items()
        }
    }


@app.get("/state/{session_id}", summary="Get current state without advancing")
async def state(session_id: str):
    """Return the current Observation without executing any action."""
    env = _get_session(session_id)
    return env.state().model_dump()


@app.get("/tasks", summary="List all available tasks")
async def list_tasks():
    """Return metadata for all three tasks."""
    return {
        "tasks": [
            {
                "id": "fix_broken_query",
                "name": "Fix the Broken SQL Query",
                "difficulty": "easy",
                "max_steps": SQLDebugEnv.MAX_STEPS,
                "description": "Fix a SQL query with multiple syntax and semantic errors.",
            },
            {
                "id": "write_business_query",
                "name": "Write a Business Analytics Query",
                "difficulty": "medium",
                "max_steps": SQLDebugEnv.MAX_STEPS,
                "description": "Write SQL with GROUP BY, aggregations, and a HAVING clause.",
            },
            {
                "id": "complex_analytics",
                "name": "Complex Multi-table Analytics",
                "difficulty": "hard",
                "max_steps": SQLDebugEnv.MAX_STEPS,
                "description": "Write complex SQL with window functions, 2+ JOINs, and top-N ranking.",
            },
            {
                "id": "recursive_org_hierarchy",
                "name": "Recursive Org-Chart Query",
                "difficulty": "hard",
                "max_steps": SQLDebugEnv.MAX_STEPS,
                "description": "Write a recursive CTE to traverse an org hierarchy with project counts.",
            },
            {
                "id": "data_quality_audit",
                "name": "Data Quality Audit Pipeline",
                "difficulty": "hard",
                "max_steps": SQLDebugEnv.MAX_STEPS,
                "description": "Write SQL to detect 5 types of data quality issues using UNION ALL.",
            },
            {
                "id": "query_optimizer",
                "name": "SQL Query Optimizer",
                "difficulty": "expert",
                "max_steps": SQLDebugEnv.MAX_STEPS,
                "description": "Rewrite a slow correlated-subquery into a fast JOIN+GROUP BY.",
            },
            {
                "id": "nl_to_sql",
                "name": "Natural Language → SQL Report Builder",
                "difficulty": "expert",
                "max_steps": SQLDebugEnv.MAX_STEPS,
                "description": "Translate a plain-English business request into complex multi-table SQL.",
            },
            {
                "id": "transaction_deadlock",
                "name": "Transaction Deadlock & Anomaly Detector",
                "difficulty": "expert",
                "max_steps": SQLDebugEnv.MAX_STEPS,
                "description": "Detect 5 types of banking transaction anomalies using UNION ALL.",
            },
        ]
    }


@app.get("/openenv.yaml", summary="Serve the OpenEnv spec file")
async def serve_openenv_yaml():
    path = os.path.join(os.path.dirname(__file__), "openenv.yaml")
    if os.path.exists(path):
        return FileResponse(path, media_type="text/yaml")
    raise HTTPException(status_code=404, detail="openenv.yaml not found")


@app.get("/health", summary="Health check")
async def health():
    return {"status": "ok", "active_sessions": len(_sessions)}


# ── Mount Gradio demo at /demo ────────────────────────────────────────────
gradio_app = build_demo()
app = gr.mount_gradio_app(app, gradio_app, path="/demo")


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _get_session(session_id: str) -> SQLDebugEnv:
    env = _sessions.get(session_id)
    if env is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found. Call POST /reset first.",
        )
    return env


# ═══════════════════════════════════════════════════════════════════════════
# Entry-point
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
