#!/usr/bin/env bash
# Prueba de humo de punta a punta.
#
#   ./scripts/smoke.sh
#
# Arranca el backend local, espera a llama-server, carga datos demo, consulta al
# copiloto y exporta el XLSX. Sirve como verificación reproducible de la app.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PORT="${FINANZAR_SMOKE_PORT:-8975}"
DATA_DIR="${FINANZAR_DATA_DIR:-$HOME/Library/Application Support/FinanzAR}"
export FINANZAR_DATA_DIR="$DATA_DIR"
export FINANZAR_ALLOW_SEED=1
BASE="http://127.0.0.1:$PORT"
LOG="/tmp/finanzar-smoke-backend.log"

pretty() { python3 -c 'import sys,json; print(json.dumps(json.load(sys.stdin), indent=2, ensure_ascii=False))'; }

echo "==> Arrancando backend en $BASE (datos en $DATA_DIR)"
(cd backend && uv run python -m finanzar_backend --host 127.0.0.1 --port "$PORT" --data-dir "$DATA_DIR" >"$LOG" 2>&1) &
BACKEND_PID=$!
cleanup() { kill "$BACKEND_PID" 2>/dev/null || true; }
trap cleanup EXIT

echo "==> Esperando /health"
for _ in $(seq 1 120); do
  if curl -sf "$BASE/health" >/dev/null 2>&1; then break; fi
  sleep 1
done
curl -sf "$BASE/health" | pretty

echo
echo "==> Esperando a llama-server (copiloto local)"
for _ in $(seq 1 180); do
  if curl -sf "$BASE/health" | grep -q '"llmAvailable": *true'; then break; fi
  sleep 1
done
LLM_JSON="$(curl -sf "$BASE/api/llm/status")"
echo "$LLM_JSON" | pretty
LLM_BASE="$(printf '%s' "$LLM_JSON" | python3 -c 'import sys,json; print(json.load(sys.stdin)["data"]["baseUrl"] or "")')"
if [ -n "$LLM_BASE" ]; then
  echo "    llama-server /health -> $(curl -sf "$LLM_BASE/health")"
  echo "    llama-server /v1/models -> $(curl -sf "$LLM_BASE/v1/models" | head -c 160)…"
fi

echo
echo "==> Estado de modelos"
curl -sf "$BASE/api/models/status" | pretty

echo
echo "==> Cargando datos demo (seed)"
curl -sf -X POST "$BASE/api/dev/seed" | pretty

echo
echo "==> Pregunta al copiloto"
curl -sf -X POST "$BASE/api/copilot/chat" \
  -H 'Content-Type: application/json' \
  -d '{"question":"¿Cuánto tengo que pagar este mes y qué cuotas siguen?"}' | pretty

echo
echo "==> Exportando XLSX"
curl -sf -X POST "$BASE/api/export/xlsx" \
  -H 'Content-Type: application/json' -d '{}' | pretty

echo
echo "==> Prueba de humo completada"
