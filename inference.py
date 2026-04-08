"""
inference.py — Baseline agent for SQL Debug Environment.

Usage:
  export API_BASE_URL=https://<your-hf-space>.hf.space
  export MODEL_NAME=meta-llama/Llama-3.1-70B-Instruct
  export HF_TOKEN=hf_...
  python inference.py

The agent:
  1. Calls POST /reset to start an episode.
  2. Uses the LLM to decide actions (examine_schema → run_query → submit_solution).
  3. Collects the grader score from the step result.
  4. Repeats for all 3 tasks and prints a summary.

Environment variables:
  API_BASE_URL   URL of the deployed OpenEnv server (default: http://localhost:7860)
  MODEL_NAME     LLM model identifier (default: gpt-4o-mini)
  HF_TOKEN       Hugging Face / OpenAI API key
  LLM_BASE_URL   Base URL for the OpenAI-compatible LLM API
                 (default: https://api.openai.com/v1)
"""

import json
import os
import sys
import time

import requests
from openai import OpenAI

# ── Configuration ────────────────────────────────────────────────────────────
ENV_BASE_URL: str = os.getenv("API_BASE_URL", "http://localhost:7860").rstrip("/")
MODEL_NAME: str   = os.getenv("MODEL_NAME", "gpt-4o-mini")
HF_TOKEN: str     = os.getenv("HF_TOKEN", os.getenv("OPENAI_API_KEY", "")) or "EMPTY"
LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
MAX_EPISODE_STEPS: int = 20

# Health-check retry settings
HEALTH_RETRIES: int        = 5
HEALTH_RETRY_DELAY: float  = 6.0   # seconds between retries

# ── LLM client ───────────────────────────────────────────────────────────────
llm = OpenAI(base_url=LLM_BASE_URL, api_key=HF_TOKEN)

SYSTEM_PROMPT = """You are an expert SQL agent operating inside an interactive database environment.

AVAILABLE ACTIONS (respond with EXACTLY ONE JSON object, no markdown, no extra text):

1. Examine a table schema:
   {"action_type": "examine_schema", "table_name": "<n>"}

2. Run a SQL query to explore the data:
   {"action_type": "run_query", "sql": "<SELECT ...>"}

3. Submit your final answer:
   {"action_type": "submit_solution", "sql": "<corrected/written SQL>"}

STRATEGY:
- First examine ALL available tables to understand the schema.
- Run test queries to validate your understanding.
- Once confident, submit your solution.
- Be efficient: aim to solve tasks in ≤10 steps.
- Think carefully about the task requirements before submitting.
"""


def call_llm(messages: list) -> str:
    response = llm.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "system", "content": SYSTEM_PROMPT}] + messages,
        temperature=0.0,
        max_tokens=512,
    )
    if not response.choices:
        raise ValueError("LLM returned no choices")
    content = response.choices[0].message.content
    if content is None:
        return json.dumps({"action_type": "submit_solution", "sql": "SELECT 'no_content' AS error"})
    return content.strip()


def parse_action(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        inner = [l for l in lines if not l.startswith("```")]
        text = "\n".join(inner).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
    return {"action_type": "submit_solution", "sql": "SELECT 'parse_error' AS error"}


def env_post(path: str, **kwargs) -> dict:
    url = f"{ENV_BASE_URL}{path}"
    r = requests.post(url, timeout=30, **kwargs)
    r.raise_for_status()
    return r.json()


def env_get(path: str) -> dict:
    url = f"{ENV_BASE_URL}{path}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json()


def wait_for_server() -> bool:
    """
    Retry the /health endpoint up to HEALTH_RETRIES times.
    Returns True if the server responds OK, False otherwise.
    HF Spaces can take 30-60 s to warm up, so retrying is essential.
    """
    for attempt in range(1, HEALTH_RETRIES + 1):
        try:
            env_get("/health")
            return True
        except Exception as exc:
            if attempt < HEALTH_RETRIES:
                print(
                    f"[HEALTH] attempt={attempt} server not ready "
                    f"({type(exc).__name__}), retrying in {HEALTH_RETRY_DELAY}s ..."
                )
                time.sleep(HEALTH_RETRY_DELAY)
            else:
                print(
                    f"[HEALTH] attempt={attempt} server unreachable after "
                    f"{HEALTH_RETRIES} retries ({type(exc).__name__}: {exc})"
                )
    return False


def run_episode(task_id: str) -> float:
    final_score = 0.0
    print(f"[START] task_id={task_id}")
    try:
        data = env_post("/reset", params={"task_id": task_id})
        session_id = data.get("session_id")
        obs = data.get("observation")
        if not session_id or not obs:
            print(f"[END] task_id={task_id} score=0.0")
            return 0.0

        conversation: list = []

        for step_num in range(1, MAX_EPISODE_STEPS + 1):
            if obs.get("done"):
                break

            user_msg = (
                f"TASK:\n{obs.get('task_description', 'No description')}\n\n"
                f"Available tables: {obs.get('available_tables', [])}\n"
                f"Step: {obs.get('step_count', 0)} / 25\n"
                f"Last result: {json.dumps(obs.get('last_result'), default=str)[:600]}\n"
                f"Last error: {obs.get('last_error') or 'none'}\n"
                f"Recent history: {json.dumps(obs.get('query_history', [])[-3:])}\n\n"
                "What is your next action? (JSON only)"
            )

            conversation.append({"role": "user", "content": user_msg})

            try:
                llm_text = call_llm(conversation)
            except Exception:
                llm_text = json.dumps({"action_type": "submit_solution", "sql": "SELECT 1"})

            conversation.append({"role": "assistant", "content": llm_text})
            action = parse_action(llm_text)

            action_label = action.get("action_type", "?")
            action_detail = (action.get("table_name") or action.get("sql", "")[:60]).replace("\n", " ")
            print(f"[STEP] step={step_num} action={action_label} detail={action_detail!r}")

            try:
                step_data = env_post(f"/step/{session_id}", json=action)
            except Exception:
                break

            obs = step_data.get("observation", {})
            reward = step_data.get("reward", {})
            reward_val = reward.get("value", 0.0)
            reward_msg = reward.get("reason", "").replace("\n", " ")[:70]
            print(f"[REWARD] value={reward_val} reason={reward_msg!r}")

            if step_data.get("done"):
                info = step_data.get("info") or {}
                final_score = info.get("score", 0.0)
                break
    except Exception:
        pass

    print(f"[END] task_id={task_id} score={final_score}")
    return final_score


def main() -> None:
    server_ok = wait_for_server()
    if not server_ok:
        # Server is unreachable — write zero scores so the evaluator still gets
        # a valid JSON artifact and exit cleanly (exit code 0).
        print("[SUMMARY] avg_score=0.0 elapsed=0.0s")
        zero_scores = {
            "fix_broken_query": 0.0,
            "write_business_query": 0.0,
            "complex_analytics": 0.0,
        }
        try:
            with open("baseline_scores.json", "w") as fh:
                json.dump(
                    {"scores": zero_scores, "average": 0.0, "elapsed_seconds": 0.0},
                    fh,
                    indent=2,
                )
        except Exception:
            pass
        return

    tasks = ["fix_broken_query", "write_business_query", "complex_analytics"]
    scores: dict = {}
    t0 = time.time()

    try:
        for task_id in tasks:
            score = run_episode(task_id)
            scores[task_id] = score
    except Exception as exc:
        print(f"[ERROR] Unexpected error during episodes: {type(exc).__name__}: {exc}")
        for task_id in tasks:
            if task_id not in scores:
                scores[task_id] = 0.0

    elapsed = time.time() - t0
    avg = sum(scores.values()) / max(len(scores), 1)

    print(f"[SUMMARY] avg_score={avg} elapsed={elapsed:.1f}s")

    try:
        with open("baseline_scores.json", "w") as fh:
            json.dump(
                {"scores": scores, "average": avg, "elapsed_seconds": elapsed},
                fh,
                indent=2,
            )
    except Exception as exc:
        print(f"[ERROR] Could not write baseline_scores.json: {exc}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Last-resort safety net — ensures we never exit with an unhandled traceback.
        print(f"[ERROR] Fatal error in main: {type(exc).__name__}: {exc}")
        sys.exit(0)
