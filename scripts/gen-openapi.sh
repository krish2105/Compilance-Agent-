#!/usr/bin/env bash
# Regenerate the OpenAPI spec from the FastAPI app + the typed TS client.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/backend/.venv/bin/python"; [ -x "$PY" ] || PY=python
(cd "$ROOT/backend" && "$PY" -c "import json; from app.main import app; open('openapi.json','w').write(json.dumps(app.openapi(), indent=2))")
(cd "$ROOT/frontend" && npx openapi-typescript ../backend/openapi.json -o src/lib/api-types.ts)
echo "OpenAPI spec + typed client regenerated."
