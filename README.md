# fireguard-agent-compliance

The reasoning engine of the FireGuard platform — takes building details
from the user, fetches relevant fire regulation chunks from
`fireguard-agent-retrieval`, and asks Gemini to produce a strict,
structured compliance verdict (COMPLIANT / NON_COMPLIANT / PARTIAL, per
clause).

## Build status

- [x] **Step 1** — FastAPI skeleton, config/logger/exceptions, `/health`,
      Dockerized + joined to `fireguard-vector-store`'s Docker network
- [ ] Step 2 — Retrieval client (calls fireguard-agent-retrieval, with real retries)
- [ ] Step 3 — Compliance engine (Gemini integration)
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
