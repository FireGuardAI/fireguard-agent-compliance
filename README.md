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
- [x] **Step 4** — `/api/v1/audit` endpoint
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

`app/services/compliance_engine.py` — fixes three bugs, one found during
initial reference-doc review, two found through actual testing:

1. **Import-time instantiation** (`engine = ComplianceEngine()` at module
   load) meant a missing/bad API key crashed the app before it could
   report a clean error. Now built in the startup event, like every
   other service here.
2. **`tenacity` was listed as a dependency but never used.** Now the
   actual Gemini API call retries transient failures (rate limits,
   network errors) with exponential backoff.
3. **(Found via live testing) Gemini returned a partial JSON object**
   (only `overall_status`, missing `compliance_score`/`detailed_checks`/
   `summary`) when relying on prompt-only schema instructions with the
   deprecated `google-generativeai` SDK. Fixed by migrating to the
   current `google-genai` SDK, which accepts the `ComplianceResponse`
   Pydantic model directly as `response_schema` — Gemini's output is
   then schema-enforced server-side, not just prompt-requested.

Response parsing still has a defensive fallback: `response.parsed` can
be `None` if generation was truncated, in which case a clean
`LLMResponseParsingError` is raised instead of a crash.

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

## Step 4 — Full audit (`/api/v1/audit`)

Wires retrieval + compliance engine together. Fixes the reference doc's
blanket `except Exception: raise HTTPException(500, str(e))`, which
couldn't distinguish "retrieval agent is down" from "Gemini returned
garbage" from "no relevant regulations found" — each now gets its own
status code:

| Failure | Status | Meaning |
|---|---|---|
| Services not initialized | 503 | Shouldn't happen post-startup |
| Retrieval agent unreachable | 502 | Upstream dependency down |
| No chunks found for the query | 422 | Nothing relevant to check against |
| Gemini response unparseable | 502 | LLM didn't return valid/matching JSON |
| Gemini API call failed | 503 | Upstream LLM service issue |

```powershell
docker compose up -d --build
```

```powershell
$body = @{
    building_details = @{
        building_type = "Commercial"
        number_of_floors = 5
        has_extinguishers = $true
        extinguisher_details = "ABC type, 5kg, one per floor near stairwell"
    }
} | ConvertTo-Json
Invoke-RestMethod -Uri "http://localhost:8002/api/v1/audit" -Method Post -Body $body -ContentType "application/json"
```

Expected: a JSON object with `overall_status`, `compliance_score`,
`detailed_checks` (each citing a `rule_clause` from the retrieved
regulation chunks), and `summary`. This call chains all three services
(retrieval → Gemini) and typically takes a few seconds.
