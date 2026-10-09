#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi
npm run build
exec .venv/bin/uvicorn server:app --host "${PPE_HOST:-127.0.0.1}" --port "${PPE_PORT:-34402}" --workers 1 --no-access-log
