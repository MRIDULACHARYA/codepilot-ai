#!/usr/bin/env bash
# Start API (:8000) and Streamlit UI (:8501) locally.
set -euo pipefail
cd "$(dirname "$0")/.."
export API_URL="${API_URL:-http://localhost:8000}"
uvicorn backend.main:app --port 8000 &
API_PID=$!
trap 'kill $API_PID 2>/dev/null' EXIT
streamlit run frontend/app.py --server.port 8501
