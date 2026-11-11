# Resume & interview notes — CodePilot AI

Only claims that the repository can back up. Add your own numbers **only** after running the benchmark with a real key and Docker.

## One-line description
Multi-agent AI code-review platform (LangGraph, FastAPI, ChromaDB RAG, Streamlit) that detects bugs, proposes fixes, generates tests and verifies them in a hardened Docker sandbox, with explicit provenance for every finding.

## Resume bullets (pick 3–4)
- Designed and built **CodePilot AI**, a six-agent code review/repair system on **LangGraph** with intent-based routing (6 intents, per-intent plans) and a **bounded self-repair loop** (max 3 attempts) driven by executed test failures.
- Implemented **agentic RAG** (ChromaDB, LangChain LCEL) over a 9-document engineering knowledge base: intent-driven retrieval decisions, category/language filtering, source-referenced context, and an offline embedding fallback when the embedding API is unavailable.
- Built a **hardened Docker execution sandbox** (non-root, no network, read-only FS, CPU/memory/PID limits, timeouts, no host secrets) and a validator that distinguishes *verified*, *tests-don't-expose-the-bug*, *failed* and *unverified* outcomes, plus regression detection.
- Engineered trustworthy AI output: findings carry **provenance** (static / LLM-suspected / confirmed-by-execution / simulated), a **deterministic quality score** replaces LLM scoring, and LLM line numbers are validated against the source.
- Created a **34-program benchmark** with machine-validated reference fixes and tests, an evaluation harness that reports "not measured" rather than estimating, and an **89-test** suite (agents, graph, API, RAG, sandbox, security, Streamlit UI) — which caught real defects during development (e.g. dropped static findings on LLM outage, mislabelled demo line numbers, error-message leakage).
- Delivered a FastAPI backend (Pydantic schemas, rate limiting, secret-redacting structured logs, SQLAlchemy models portable to PostgreSQL) and a dark SaaS-style Streamlit UI with live agent activity.

## Verified facts you can quote
- 34 benchmark programs: 6 correct, 21 functional bugs, 4 security, 3 style; 4 regression variants.
- Static-only baseline on that benchmark: 20% defect recall (security 75%), 0/6 false positives.
- 89 automated tests passing.

## Facts you must NOT claim (unless you run it yourself)
- LLM-pipeline accuracy, fix success rate, test pass rate — the harness exists (`--mode pipeline`), but no number has been produced.
- That execution was exercised against a live Docker daemon in the development environment.

## Interview talking points
1. **Why provenance?** LLM bug reports are hypotheses; only an executed failing-then-passing test upgrades them. Show `validator.annotate_issues`.
2. **Why not just trust passing tests?** Tests that also pass on the buggy code prove nothing → `passed_no_discrimination`.
3. **Sandbox design:** threat model, what each Docker flag mitigates, why no local fallback, why the socket is never mounted into the execution container.
4. **Prompt injection:** delimiters, delimiter neutralisation, intent classifier never sees code, tests with an injected "ignore previous instructions" payload.
5. **Failure isolation:** `@traced` wrapper; one degraded node never kills the run; static results survive an LLM outage.
6. **Evaluation honesty:** why static recall is low, what is automatic vs human-reviewed, what is not yet measured.
7. **Scaling next steps:** async job queue (Redis/Celery), auth + per-user history, Alembic migrations, Java/C sandboxes, semantic embeddings by default.
