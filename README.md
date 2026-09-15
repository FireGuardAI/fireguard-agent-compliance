# fireguard-agent-compliance

The reasoning engine of the FireGuard platform — takes building details
from the user, fetches relevant fire regulation chunks from
`fireguard-agent-retrieval`, and asks Gemini to produce a strict,
structured compliance verdict (COMPLIANT / NON_COMPLIANT / PARTIAL, per
clause).

## Build status

- [x] **Step 1** — FastAPI skeleton, config/logger/exceptions, `/health`,
      Dockerized + joined to `fireguard-vector-store`'s Docker network
- [x] **Step 2** — Retrieval client (`httpx` + real `tenacity` retries), `/health/retrieval`
- [x] **Step 3** — Compliance engine (Gemini integration), `/health/gemini`
- [ ] Step 4 — `/api/v1/audit` endpoint
- [ ] Step 5 — Production hardening (optional)

## Prerequisites

- `fireguard-vector-store` running (provides the Docker network)
- `fireguard-agent-retrieval` running (this service calls it)
- A free Gemini API key from https://aistudio.google.com/apikey

**Folder layout assumed** (sibling repos):
```
SLIT/
├── fireguard-vector-store/
├── fireguard-agent-retrieval/
└── fireguard-agent-compliance/
```

## Step 1 — Run locally

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
cp .env.example .env
# edit .env and set GEMINI_API_KEY (required — the app won't start without it)

uvicorn app.main:app --reload --port 8002
```

Test it:
```bash
curl.exe http://localhost:8002/health
```
Expected:
```json
{"status":"ok","service":"FireGuard Compliance Agent"}
```

## Step 1 — Run with Docker

```powershell
Copy-Item .env.example .env
# edit .env and set GEMINI_API_KEY
docker compose up -d --build
```

Test it:
```powershell
curl.exe http://localhost:8002/health
docker ps   # fireguard-agent-compliance should show (healthy)
```

If it fails with a "network not found" error, see the same troubleshooting
note in `fireguard-agent-retrieval`'s README — your `fireguard-vector-store`
folder name needs to match what's in `docker-compose.yml`'s `networks:`
section.

Port `8002` — `8000` is ChromaDB, `8001` is `fireguard-agent-retrieval`.

## Step 2 — Retrieval client

`app/services/retrieval_client.py` calls `fireguard-agent-retrieval`'s
`/api/v1/retrieve` endpoint, with `tenacity`-based exponential-backoff
retries — but **only** for transient failures (timeouts, connection
errors, 5xx responses). A 4xx response fails immediately without
retrying, since retrying a rejected request can't fix it.

**Prerequisite:** `fireguard-agent-retrieval` must be running (Steps 1-5
of that repo) for `/health/retrieval` to succeed.

```powershell
docker compose up -d --build
curl.exe http://localhost:8002/health/retrieval
```

Expected:
```json
{"status":"ok","retrieval_agent":{"status":"ok","service":"FireGuard Retrieval Agent"}}
```

If it returns `503`, check `fireguard-agent-retrieval` is actually
running on the same Docker network (`docker ps`, `docker network
inspect fireguard-vector-store_fireguard-net`).

## Step 3 — Compliance engine (Gemini)

`app/services/compliance_engine.py` — fixes two reference-doc bugs:

1. **Import-time instantiation** (`engine = ComplianceEngine()` at module
   load) meant a missing/bad API key crashed the app before it could
   report a clean error. Now built in the startup event, like every
   other service here.
2. **`tenacity` was listed as a dependency but never used.** Now the
   actual Gemini API call retries transient failures (rate limits,
   network errors) with exponential backoff.

Response parsing is defensive: `json.loads()` and the Pydantic
`ComplianceResponse` validation are both wrapped, raising a clean
`LLMResponseParsingError` instead of an uncaught crash if Gemini's
output isn't valid JSON or doesn't match the schema.

```powershell
docker compose up -d --build
curl.exe http://localhost:8002/health/gemini
```

Expected:
```json
{"status":"ok","model":"gemini-1.5-flash"}
```

This makes one real (tiny) Gemini API call — don't script it into a
tight polling loop, Gemini's free tier is rate-limited.
