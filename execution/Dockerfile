# Sandbox image used ONLY to run generated pytest suites against submitted code.
# Build:  docker build -t codepilot-sandbox:latest -f execution/Dockerfile execution/
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

RUN pip install --no-cache-dir "pytest>=8,<10" \
    && groupadd --gid 10001 sandbox \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin sandbox

USER 10001:10001
WORKDIR /work
