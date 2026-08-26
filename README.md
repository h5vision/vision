# Vision Backend P

FastAPI Backend that receives VS Code workspace overlays, records Snapshot state,
and forwards validated file payloads to Model/RAG Lab.

Phase 1 provides the application skeleton, environment validation, structured JSON
errors, request correlation, liveness, and readiness. Snapshot forwarding is added
in later phases.

## Local setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

Set a non-secret local `DATABASE_URL` in `.env` before expecting readiness to pass.
Do not commit `.env`.

## Run

```powershell
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Frontend-facing health endpoint:

```text
GET http://127.0.0.1:8000/v1/health
```

Readiness endpoint:

```text
GET http://127.0.0.1:8000/v1/health/ready
```

Liveness never contacts PostgreSQL or RAG Lab. Readiness currently verifies required
configuration only; dependency connection probes are added with their integrations.

## Verify

```powershell
python -m compileall -q backend
python -m pytest -q tests/contract
python -m pytest -q tests/unit
python -m pytest -q tests/integration
python -m pytest -q
```
