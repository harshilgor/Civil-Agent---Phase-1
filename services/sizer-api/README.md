# Civil Agent Sizer API

Thin HTTP wrapper around `civilagent-sizer`. The service imports the engine directly and does not reimplement sizing logic.

## Run locally

```powershell
cd services/sizer-api
python -m pip install -r requirements.txt
$env:SIZER_API_PORT = "8001"
uvicorn main:app --host 127.0.0.1 --port 8001
```

If `civilagent-sizer` is checked out locally instead of published, install it first:

```powershell
python -m pip install -e "C:\Civil Agent - sizing\civilagent-sizer"
```

## Endpoints

- `GET /health`
- `POST /api/v1/size`
- `POST /api/v1/size/compare`
- `POST /api/v1/export/pdf`

The `/api/v1/size` endpoint accepts the same plan JSON shape as the CLI, plus an optional `layout` field (`A` or `B`). It also accepts the simplified frontend form payload and converts it to the CLI plan schema before calling the engine.
