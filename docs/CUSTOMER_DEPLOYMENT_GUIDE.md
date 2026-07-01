# Customer Deployment Guide

1. Install Python 3.11 and Node.js.
2. Install dependencies:

```powershell
.\setup.ps1
cd frontend
npm install
```

3. Configure `.env`:

```text
CUSTOMER_PRODUCTION_MODE=true
CUSTOMER_UPLOAD_ENABLED=false
BUSINESS_TIMEZONE=Asia/Ho_Chi_Minh
PERFORMANCE_FORMULA_MODE=disabled
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3.5:9b
```

4. Place the three workbook files at the repository root:

- `Machine_Downtime_20260203_100753.xlsx`
- `Loss_Assignment_20260203_100840.xlsx`
- `Cup3.xlsx`

5. Rebuild cache:

```powershell
python scripts_ingest.py
```

6. Start services:

```powershell
.\start-backend.ps1
.\start-frontend.ps1
```

7. Verify:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
cd frontend
npm test
npm run build
```

Current release note: local Ollama was not reachable during this verification run, so customer release remains blocked.
