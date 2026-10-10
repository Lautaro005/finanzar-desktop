# finanzar-backend

Backend local de **FinanzAR Desktop**. Corre como *sidecar* en `127.0.0.1` y
nunca envía datos financieros a la red.

- **FastAPI + uvicorn** como contrato HTTP local.
- **SQLite** como fuente de verdad estructurada (`db/migrations`).
- **ChromaDB `PersistentClient`** como memoria semántica de recuperación.
- **GLM-OCR** (`zai-org/GLM-OCR`) para OCR de resúmenes.
- **llama.cpp + Spark-X2.5-1.7B (Q4_K_M)** como copiloto OpenAI-compatible local.

## Desarrollo

```bash
cd backend
uv venv --python 3.12
uv pip install -e ".[dev]"
uv run pytest -q
uv run python -m finanzar_backend --port 8765
```

## Endpoints principales

Todas las respuestas usan el envelope `{ok, data, error, request_id}`.
La lista completa está en `finanzar_backend/api/routes.py` y en el `AGENT.md` del
repositorio.

## Privacidad

- Bind exclusivo en `127.0.0.1`.
- Sin telemetría. La red solo se usa para descargar modelos, comprobar
  actualizaciones y descargar una actualización aceptada por la persona.
- Logs con redacción de números de tarjeta e importes.

## Licencias

- GLM-OCR: MIT.
- PP-DocLayoutV3: Apache-2.0.
- Spark-X2.5-1.7B GGUF: Apache-2.0.
- llama.cpp: MIT.