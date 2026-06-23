# Customer Deployment Guide

## Prerequisites

- Python environment with project requirements installed.
- Node/npm installed for the React frontend.
- Ollama available with `qwen3.5:9b` when real LLM routing is required.
- Three baseline Excel workbooks present at the repository root.

## Backend

Run:

```powershell
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

## Frontend

Run:

```powershell
cd frontend
npm run dev
```

Open `http://127.0.0.1:5173/`.

## Verification

Recommended release checks:

```powershell
python evaluation\run_file_scoped_benchmark.py
python evaluation\run_customer_challenge_benchmark.py
python evaluation\run_black_box_customer_uat.py
python evaluation\run_new_workbook_generalization.py
python -m pytest -q
cd frontend
npm test -- --run
npm run build
```
