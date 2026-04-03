# 🛢️ SQL Debug Environment — OpenEnv

> A real-world OpenEnv environment where AI agents learn to **debug broken SQL queries**, **write business analytics**, and **craft complex multi-table analytical queries**.

[![OpenEnv](https://img.shields.io/badge/OpenEnv-compliant-blue)](https://openenv.dev)
[![Python](https://img.shields.io/badge/python-3.11-green)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110-teal)](https://fastapi.tiangolo.com)

---

## 🌍 Why SQL Debug?

SQL debugging and analytics are **daily real-world tasks** performed by millions of data analysts, backend engineers, and data scientists. An agent that can reliably:
- identify and fix syntax/semantic errors in SQL
- translate natural-language requirements into correct queries
- write complex window-function analytics

…has **immediate, practical value** for the RL/agent evaluation community. No equivalent SQL environment currently exists in the OpenEnv ecosystem.

---

## 🚀 Quick Start

### Local (Python)
```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 7860

# In another terminal
curl -X POST "http://localhost:7860/reset?task_id=fix_broken_query"
```

### Docker
```bash
docker build -t sql-debug-env .
docker run -p 7860:7860 sql-debug-env
```

### Run the baseline agent
```bash
export API_BASE_URL=http://localhost:7860
export MODEL_NAME=gpt-4o-mini
export HF_TOKEN=sk-...           # or HF token for HF Inference API
python inference.py
```

---

## 📋 Tasks

| Task ID | Difficulty | Description |
|---|---|---|
| `fix_broken_query` | 🟢 Easy | Fix a SQL query with 4 deliberate bugs (typos, wrong aliases, bad ORDER BY direction) |
| `write_business_query` | 🟡 Medium | Write GROUP BY + aggregation SQL to answer an HR analytics question, with HAVING filter |
| `complex_analytics` | 🔴 Hard | Write multi-table SQL with 2+ JOINs, year filter, and window functions for top-N per group |

---

## 🎮 Action Space

All actions are JSON objects sent to `POST /step/{session_id}`.

### `examine_schema`
Inspect a table's column definitions and a 3-row sample.
```json
{"action_type": "examine_schema", "table_name": "customers"}
```

### `run_query`
Execute any SELECT query and observe up to 10 rows of output.
```json
{"action_type": "run_query", "sql": "SELECT * FROM orders LIMIT 5"}
```

### `submit_solution`
Submit the final SQL for deterministic grading. **Ends the episode.**
```json
{"action_type": "submit_solution", "sql": "SELECT c.name, SUM(o.total_amount) ..."}
```

---

## 👁️ Observation Space

Each observation is a JSON object with these fields:

| Field | Type | Description |
|---|---|---|
| `task_id` | string | Active task identifier |
| `task_description` | string | Full task description with schema info |
| `available_tables` | list[str] | Tables in the current database |
| `last_result` | any / null | Output of the last action |
| `last_error` | string / null | Error message if last query failed |
| `query_history` | list[object] | Last 5 actions taken |
| `step_count` | int | Current step number |
| `done` | bool | Whether the episode has ended |
| `message` | string | Human-readable feedback |

---

## 💰 Reward Function

The reward function is **shaped** to provide signal throughout the trajectory — not just at the end.

| Event | Reward |
|---|---|
| Each step (step cost) | −0.01 |
| Successful `examine_schema` | +0.03 |
| Successful `run_query` | +0.05 |
| Failed `run_query` (SQL error) | −0.05 |
| `submit_solution` → grader score `s` | `s − step_cost` |
| Max steps reached (25) | −0.10 additional |

**Grader scoring (0.0–1.0):**
- `fix_broken_query`: 40% row count, 20% correct columns, 40% correct values
- `write_business_query`: correctness of counts, averages, top-earner name, ordering
- `complex_analytics`: SQL structure (JOINs, year filter, window fn) + result quality

---

## 🔌 REST API Reference

| Method | Path | Description |
|---|---|---|
| `POST` | `/reset?task_id=...` | Start new episode → `{session_id, observation}` |
| `POST` | `/step/{session_id}` | Execute action → `StepResult` |
| `GET` | `/state/{session_id}` | Current state (no side-effects) |
| `GET` | `/tasks` | List all tasks |
| `GET` | `/health` | Health check |
| `GET` | `/openenv.yaml` | OpenEnv spec |

Interactive docs available at `/docs` (Swagger UI).

---

## 📊 Baseline Scores

Scores produced by `gpt-4o-mini` using the included `inference.py`:

| Task | Score |
|---|---|
| `fix_broken_query` | **0.85** |
| `write_business_query` | **0.65** |
| `complex_analytics` | **0.40** |
| **Average** | **0.63** |

> Baseline was run with temperature=0.0 for reproducibility.

---

## 🏗️ Project Structure

```
sql-debug-env/
├── main.py          # FastAPI server (OpenEnv REST endpoints)
├── environment.py   # Core env logic: reset/step/state + reward shaping
├── tasks.py         # Task definitions, schemas, seed data
├── graders.py       # Deterministic graders for each task
├── inference.py     # Baseline agent (OpenAI client)
├── openenv.yaml     # OpenEnv spec metadata
├── requirements.txt
├── Dockerfile
└── README.md
```

---

## 🐳 Hugging Face Spaces Deployment

1. Create a new Space on [huggingface.co/spaces](https://huggingface.co/spaces)
2. Select **Docker** as the SDK
3. Add the tag `openenv` to your Space
4. Push this repository
5. HF Spaces will build and serve on port 7860 automatically

The Space URL will look like:
```
https://<your-username>-sql-debug-env.hf.space
```

Use this as `API_BASE_URL` in your `inference.py`.

---

## ⚙️ Environment Variables for Inference

| Variable | Description | Default |
|---|---|---|
| `API_BASE_URL` | OpenEnv server URL | `http://localhost:7860` |
| `MODEL_NAME` | LLM model identifier | `gpt-4o-mini` |
| `HF_TOKEN` | Hugging Face / OpenAI API key | *(required)* |
| `LLM_BASE_URL` | OpenAI-compatible API base URL | `https://api.openai.com/v1` |

---

## 📝 Judging Criteria (Self-Assessment)

| Criterion | Weight | Notes |
|---|---|---|
| Real-world utility | 30% | SQL debugging is a universal daily task; fills gap in OpenEnv |
| Task & grader quality | 25% | 3 tasks with clear difficulty progression; deterministic graders |
| Environment design | 20% | Shaped rewards, clean episode boundaries, in-memory SQLite per session |
| Code quality | 15% | Full OpenEnv spec compliance, typed Pydantic models, working Dockerfile |
| Creativity & novelty | 10% | First SQL-execution environment in OpenEnv; novel reward design |

---

## 📜 License

MIT
