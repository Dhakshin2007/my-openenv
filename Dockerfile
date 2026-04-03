# ── SQL Debug OpenEnv — Dockerfile ────────────────────────────────────────
# Compatible with Hugging Face Spaces (port 7860, non-root user).
#
# Build & run locally:
#   docker build -t sql-debug-env .
#   docker run -p 7860:7860 sql-debug-env
#
# Then test:
#   curl -X POST http://localhost:7860/reset?task_id=fix_broken_query
# ──────────────────────────────────────────────────────────────────────────

FROM python:3.11-slim

# HF Spaces expects a non-root user named "user"
RUN useradd -m -u 1000 user
WORKDIR /app

# ── Install dependencies ──────────────────────────────────────────────────
COPY --chown=user:user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Copy application code ─────────────────────────────────────────────────
COPY --chown=user:user . .

# ── Switch to non-root user ───────────────────────────────────────────────
USER user

# ── Expose port (HF Spaces default = 7860) ───────────────────────────────
EXPOSE 7860

# ── Health check ─────────────────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:7860/health')"

# ── Start server ──────────────────────────────────────────────────────────
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
