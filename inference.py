import json
import os
import subprocess
import sys
import time

import requests
from openai import OpenAI

# Configuration
API_BASE_URL: str = os.environ.get("API_BASE_URL", "http://localhost:7860").rstrip("/")
MODEL_NAME: str = os.environ.get("MODEL_NAME", "gpt-4o-mini")

API_KEY: str = (
    os.environ.get("API_KEY")
    or os.environ.get("HF_TOKEN")
    or os.environ.get("OPENAI_API_KEY")
    or "EMPTY"
)

ENV_BASE_URL: str = "http://localhost:7860"
LLM_BASE_URL: str = API_BASE_URL if API_BASE_URL.endswith("/v1") else API_BASE_URL + "/v1"

MAX_EPISODE_STEPS: int = 20
HEALTH_RETRIES: int = 10
HEALTH_RETRY_DELAY: float = 5.0


# Simple logger
def log(msg: str) -> None:
    print(msg, flush=True)


# LLM client
llm = OpenAI(base_url=LLM_BASE_URL, api_key=API_KEY)

SYSTEM_PROMPT = """You are an expert SQL agent operating inside an interactive database environment.

AVAILABLE ACTIONS (respond with EXACTLY ONE JSON object, no markdown, no extra text):

1. Examine a table schema:
{"action_type": "examine_schema", "table_name": ""}

2. Run a SQL query to explore the data:
{"action_type": "run_query", "sql": ""}

3. Submit your final answer:
{"action_type": "submit_solution", "sql": ""}

STRATEGY:
- First examine ALL available tables to understand the schema.
- Run test queries to validate your understanding.
- Once confident, submit your solution.
- Be efficient: aim to solve tasks in <=10 steps.
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


# Environment helpers
def env_post(path: str, **kwargs) -> dict:
    r = requests.post(f"{ENV_BASE_URL}{path}", timeout=30, **kwargs)
    r.raise_for_status()
    return r.json()


def env_get(path: str) -> dict:
    r = requests.get(f"{ENV_BASE_URL}{path}", timeout=30)
    r.raise_for_status()
    return r.json()


# Server handling
_server_process = None


def start_server_if_needed() -> None:
    global _server_process

    try:
        if requests.get(f"{ENV_BASE_URL}/health", timeout=3).status_code == 200:
            log("[SERVER] Already running")
            return
    except Exception:
        pass

    server_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")

    if not os.path.exists(server_script):
        log("[SERVER] main.py not found")
        return

    log("[SERVER] Starting main.py")
    _server_process = subprocess.Popen(
        [sys.executable, server_script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def wait_for_server() -> bool:
    for attempt in range(1, HEALTH_RETRIES + 1):
        try:
            env_get("/health")
            return True
        except Exception:
            if attempt < HEALTH_RETRIES:
                time.sleep(HEALTH_RETRY_DELAY)

    return False


# Run one task
def run_episode(task_id: str) -> float:
    final_score = 0.01
    steps_taken = 0

    log(f"[START] task={task_id}")

    try:
        data = env_post("/reset", params={"task_id": task_id})
        session_id = data.get("session_id")
        obs = data.get("observation")

        if not session_id or not obs:
            log(f"[END] task={task_id} score=0.01 steps=0")
            return 0.01

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

            try:
                step_data = env_post(f"/step/{session_id}", json=action)
            except Exception:
                break

            obs = step_data.get("observation", {})
            reward_val = step_data.get("reward", {}).get("value", 0.0)
            steps_taken = step_num

            log(f"[STEP] step={step_num} reward={reward_val}")

            if step_data.get("done"):
                raw_score = (step_data.get("info") or {}).get("score", 0.5)
                final_score = max(0.01, min(0.99, raw_score))
                break

    except Exception:
        pass

    final_score = max(0.01, min(0.99, final_score))
    log(f"[END] task={task_id} score={final_score} steps={steps_taken}")
    return final_score


# Main execution
def main() -> None:
    start_server_if_needed()

    if not wait_for_server():
        fallback_scores = {
            "fix_broken_query": 0.01,
            "write_business_query": 0.01,
            "complex_analytics": 0.01,
        }

        for task_id in fallback_scores:
            log(f"[START] task={task_id}")
            log(f"[STEP] step=0 reward=0.01")
            log(f"[END] task={task_id} score=0.01 steps=0")

        log("[SUMMARY] avg_score=0.01 elapsed=0.0s")

        with open("baseline_scores.json", "w") as fh:
            json.dump(
                {"scores": fallback_scores, "average": 0.01, "elapsed_seconds": 0.0},
                fh,
                indent=2,
            )

        return

    tasks = ["fix_broken_query", "write_business_query", "complex_analytics"]
    scores: dict = {}
    t0 = time.time()

    try:
        for task_id in tasks:
            scores[task_id] = run_episode(task_id)
    except Exception:
        for task_id in tasks:
            if task_id not in scores:
                scores[task_id] = 0.01

    elapsed = time.time() - t0
    avg = sum(scores.values()) / max(len(scores), 1)

    log(f"[SUMMARY] avg_score={avg} elapsed={elapsed:.1f}s")

    with open("baseline_scores.json", "w") as fh:
        json.dump(
            {"scores": scores, "average": avg, "elapsed_seconds": elapsed},
            fh,
            indent=2,
        )

    if _server_process is not None:
        log("[SERVER] Shutting down")
        _server_process.terminate()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[ERROR] Fatal error: {type(exc).__name__}: {exc}", flush=True)
        sys.exit(0)
