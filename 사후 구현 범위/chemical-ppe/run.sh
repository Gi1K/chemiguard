#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi
if [[ -n "${PPE_TAILSCALE_ORIGIN:-}" && "${PPE_HOST:-127.0.0.1}" != 127.0.0.1 ]]; then
  echo 'Tailscale 사진 미리보기는 PPE_HOST=127.0.0.1에서만 실행할 수 있습니다.' >&2
  exit 1
fi
npm run build
exec .venv/bin/uvicorn server:app --host "${PPE_HOST:-127.0.0.1}" --port "${PPE_PORT:-34402}" --workers 1 --no-access-log --no-proxy-headers
