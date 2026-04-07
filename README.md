---
title: SQL Debug Environment — OpenEnv
emoji: 🛢️
colorFrom: blue
colorTo: green
sdk: docker
sdk_version: "latest"
python_version: "3.11"
app_file: app.py
pinned: false
---

# 🛢️ SQL Debug Environment — Reliability & Performance Edition

> A production-grade OpenEnv environment where AI agents learn to **debug SQL**, **optimize performance**, and **ensure security** in an interactive database setting.

[![OpenEnv](https://img.shields.io/badge/OpenEnv-compliant-blue)](https://openenv.dev)
[![Security](https://img.shields.io/badge/SQL_Sentinel-Active-red)](#)
[![Performance](https://img.shields.io/badge/Performance_Oracle-Active-orange)](#)

---

## 🌟 New in v3.1: Reliability & Performance

We've upgraded the environment from a simple benchmark to a **Reliability and Observability Platform**:

- **🛡️ SQL Sentinel (AI Safety Shield):** Automatically blocks and penalizes destructive commands (`DROP`, `TRUNCATE`) and PII leakage (accessing `ssn`, `password`), turning this into a **Security Benchmark**.
- **⚖️ Performance Oracle:** Uses `EXPLAIN QUERY PLAN` to calculate a real-time **Query Cost**. Agents are rewarded for efficient `O(1)` index seeks and penalized for heavy `O(N)` table scans.
- **🚨 Chaos Monkey:** In expert tasks, data corruption is injected *mid-episode* to test the agent's real-time monitoring and resilience.
- **📊 Interactive Dashboard:** A built-in Gradio UI with a "Live Terminal" look, featuring performance gauges and security alerts.

---

## 🚀 How to Run

### 1. Setup Environment
```bash
# Install dependencies
pip install -r requirements.txt
```

### 2. Launch the Platform
You have two ways to interact with the environment:

**A. Interactive Web Demo (Recommended for Humans)**
This launches a Gradio dashboard where you can manually play the tasks and see the Performance Oracle in action.
```bash
python demo.py
# Open http://localhost:7861 in your browser
```

**B. REST API Server (For AI Agents)**
This launches the FastAPI server compliant with the OpenEnv specification.
```bash
python main.py
# Server runs on http://localhost:7860
# Swagger docs available at http://localhost:7860/docs
```

---

## 🧪 How to Test

### 1. Run the Baseline Agent
Test how an LLM performs across all tasks, including the new security and performance constraints.
```bash
# Set your API keys
export API_BASE_URL=http://localhost:7860
export HF_TOKEN=your_token_here
export MODEL_NAME=gpt-4o-mini

# Run the evaluation
python inference.py
```

### 2. Verify Security & Performance (Internal Test)
I've included a comprehensive test suite to verify the SQL Sentinel and Performance Oracle logic.
```bash
# Create and run a quick feature test
cat <<EOF > test_features.py
from environment import SQLDebugEnv, Action, SafetyValidator
env = SQLDebugEnv()
print("--- Testing Security ---")
print(SafetyValidator.validate("DROP TABLE customers"))
print("\n--- Testing Performance ---")
env.reset(task_id="fix_broken_query")
print(env.step(Action(action_type="run_query", sql="SELECT * FROM orders WHERE id=1")).info.get("performance_hint"))
EOF

python test_features.py
```

### 3. Docker Deployment
```bash
docker build -t sql-debug-env .
docker run -p 7860:7860 sql-debug-env
```

---

## 📋 Task Categories

| Task ID | Difficulty | Focus |
|---|---|---|
| `fix_broken_query` | 🟢 Easy | Syntax & Alias correction |
| `write_business_query` | 🟡 Medium | Aggregations & JOINS |
| `complex_analytics` | 🔴 Hard | Window Functions & Ranking |
| `incident_alpha` | 🟣 Expert | **Chaos Mode**: Live Incident Response |

---

## 🛡️ Security & Performance Rewards

| Event | Reward | Note |
|---|---|---|
| Destructive SQL | **-0.50** | Blocked by SQL Sentinel |
| PII Access | **-0.30** | Privacy Violation |
| Optimized Query | **+0.05** | O(1) Index Seek |
| Table Scan | **-0.02** | O(N) Performance Penalty |

---

## 📜 License
MIT

---

## 📜 License

MIT
