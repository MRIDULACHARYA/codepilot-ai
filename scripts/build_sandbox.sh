#!/usr/bin/env bash
# Build the isolated execution image used by the Validation Agent.
set -euo pipefail
cd "$(dirname "$0")/.."
docker build -t "${SANDBOX_IMAGE:-codepilot-sandbox:latest}" -f execution/Dockerfile execution/
echo "Sandbox image built. Execution/verification is now available."
