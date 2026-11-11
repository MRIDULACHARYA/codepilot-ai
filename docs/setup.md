# Setup

## Prerequisites
- Python 3.11+ (developed on 3.13)
- Docker (optional but required for test execution / verification)
- A Gemini or Groq API key (optional — without one you get static analysis + the simulated demo)

## 1. Install
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env     # edit to add a key; .env is git-ignored
```

## 2. (Optional) enable verification
```bash
bash scripts/build_sandbox.sh        # builds codepilot-sandbox:latest (python:3.11-slim + pytest, non-root)
curl localhost:8000/api/health       # after starting the API: "sandbox": {"available": true}
```
The Settings page and `/api/health` show the exact reason if the sandbox is unavailable (CLI missing, daemon down, image not built).

## 3. Run
```bash
bash scripts/run_dev.sh                              # both processes
# or separately
uvicorn backend.main:app --reload --port 8000
API_URL=http://localhost:8000 streamlit run frontend/app.py
```
UI <http://localhost:8501> · API docs <http://localhost:8000/docs> · OpenAPI JSON `/openapi.json`.

The knowledge base is ingested into `data/chroma` on first retrieval (or `python scripts/seed_kb.py --force`).

## 4. Docker Compose
```bash
docker compose up --build
docker compose --profile build build sandbox-image        # build the execution image on the host daemon
# opt in to execution from inside the API container (mounts the Docker socket into the API container — see warning in the file):
docker compose -f docker-compose.yml -f docker-compose.exec.yml up --build
```

## 5. Tests, benchmark, screenshots
```bash
python -m pytest
python -m evaluation.benchmark --validate-dataset
python -m evaluation.benchmark --mode static
python -m evaluation.benchmark --mode validator     # needs Docker + sandbox image
python -m evaluation.benchmark --mode pipeline      # needs an API key AND Docker; makes paid API calls (~34 × 5 requests)
python scripts/take_screenshots.py                  # needs `pip install playwright` + Chrome, with API and UI running
```

## 6. PostgreSQL
`DATABASE_URL=postgresql+psycopg://user:pass@host/db` (install `psycopg[binary]`). Tables are created at startup (`create_all`);
add Alembic migrations before a production deployment.

## Troubleshooting
| Symptom | Cause / fix |
|---|---|
| UI: "Cannot reach the CodePilot API" | Start `uvicorn`, or set `API_URL` |
| "Docker sandbox unavailable" | Start Docker, build the image (`scripts/build_sandbox.sh`) |
| Results say `static_only` | No API key configured (or `LLM_PROVIDER=none`) |
| Retrieval method says "local hashing fallback" | No Gemini key, or the embedding API failed; results are lexical |
| `429` from the API | Raise `RATE_LIMIT_PER_MINUTE` |
