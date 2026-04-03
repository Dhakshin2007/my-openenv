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
HF_TOKEN: str     = os.getenv("HF_TOKEN", os.getenv("OPENAI_API_KEY", ""))
LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
MAX_EPISODE_STEPS: int = 20

# ── LLM client ───────────────────────────────────────────────────────────────
llm = OpenAI(base_url=LLM_BASE_URL, api_key=HF_TOKEN)

SYSTEM_PROMPT = """You are an expert SQL agent operating inside an interactive database environment.

AVAILABLE ACTIONS (respond with EXACTLY ONE JSON object, no markdown, no extra text):

1. Examine a table schema:
   {"action_type": "examine_schema", "table_name": "<name>"}

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
    """Call the LLM with conversation history. Returns the raw text response."""
    response = llm.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "system", "content": SYSTEM_PROMPT}] + messages,
        temperature=0.0,
        max_tokens=512,
    )
    return response.choices[0].message.content.strip()


def parse_action(text: str) -> dict:
    """Parse LLM output into an action dict. Falls back to submit on parse error."""
    text = text.strip()
    # Strip optional markdown fences
    if text.startswith("```"):
        lines = text.splitlines()
        inner = [l for l in lines if not l.startswith("```")]
        text = "\n".join(inner).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to extract first JSON object
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
    # Fallback
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


def run_episode(task_id: str) -> float:
    """Run one full episode for *task_id*. Returns the grader score (0.0–1.0)."""
    print(f"\n{'─'*60}")
    print(f"  TASK: {task_id}")
    print(f"{'─'*60}")

    # ── Reset ────────────────────────────────────────────────────────────────
    data = env_post("/reset", params={"task_id": task_id})
    session_id = data["session_id"]
    obs = data["observation"]

    conversation: list = []
    final_score = 0.0

    for step_num in range(1, MAX_EPISODE_STEPS + 1):
        if obs.get("done"):
            break

        # Build user message from current observation
        user_msg = (
            f"TASK:\n{obs['task_description']}\n\n"
            f"Available tables: {obs['available_tables']}\n"
            f"Step: {obs['step_count']} / 25\n"
            f"Last result: {json.dumps(obs.get('last_result'), default=str)[:600]}\n"
            f"Last error: {obs.get('last_error') or 'none'}\n"
            f"Recent history: {json.dumps(obs.get('query_history', [])[-3:])}\n\n"
            "What is your next action? (JSON only)"
        )

        conversation.append({"role": "user", "content": user_msg})

        # ── LLM decision ─────────────────────────────────────────────────────
        try:
            llm_text = call_llm(conversation)
        except Exception as exc:
            print(f"  [step {step_num}] LLM error: {exc}")
            llm_text = json.dumps({"action_type": "submit_solution", "sql": "SELECT 1"})

        conversation.append({"role": "assistant", "content": llm_text})
        action = parse_action(llm_text)

        action_label = action.get("action_type", "?")
        action_detail = action.get("table_name") or (action.get("sql", "")[:60])
        print(f"  [step {step_num}] {action_label}: {action_detail!r}")

        # ── Send action ───────────────────────────────────────────────────────
        try:
            step_data = env_post(f"/step/{session_id}", json=action)
        except requests.HTTPError as exc:
            print(f"  [step {step_num}] HTTP error: {exc}")
            break

        obs = step_data["observation"]
        reward = step_data["reward"]
        print(f"           reward={reward['value']:+.4f}  msg={reward['reason'][:70]!r}")

        if step_data.get("done"):
            info = step_data.get("info", {})
            final_score = info.get("score", 0.0)
            print(f"\n  ✓ Episode finished.  SCORE = {final_score:.4f}")
            if "grading_details" in info:
                for k, v in info["grading_details"].items():
                    print(f"    {k}: {v}")
            break

    return final_score


def main() -> None:
    print("=" * 60)
    print("  SQL Debug OpenEnv — Baseline Evaluation")
    print(f"  ENV  : {ENV_BASE_URL}")
    print(f"  MODEL: {MODEL_NAME}")
    print("=" * 60)

    # Verify server is up
    try:
        health = env_get("/health")
        print(f"  Server health: {health}")
    except Exception as exc:
        print(f"ERROR: Cannot reach environment at {ENV_BASE_URL}\n  {exc}")
        sys.exit(1)

    tasks = ["fix_broken_query", "write_business_query", "complex_analytics"]
    scores: dict = {}
    t0 = time.time()

    for task_id in tasks:
        score = run_episode(task_id)
        scores[task_id] = score

    elapsed = time.time() - t0

    print("\n" + "=" * 60)
    print("  FINAL SCORES")
    print("=" * 60)
    for tid, s in scores.items():
        bar = "█" * int(s * 20) + "░" * (20 - int(s * 20))
        print(f"  {tid:<28} {s:.4f}  [{bar}]")
    avg = sum(scores.values()) / len(scores)
    print(f"\n  Average score: {avg:.4f}")
    print(f"  Total time:    {elapsed:.1f}s")
    print("=" * 60)

    # Persist scores
    with open("baseline_scores.json", "w") as fh:
        json.dump({"scores": scores, "average": avg, "elapsed_seconds": elapsed}, fh, indent=2)
    print("\n  Scores saved to baseline_scores.json")


if __name__ == "__main__":
    main()
