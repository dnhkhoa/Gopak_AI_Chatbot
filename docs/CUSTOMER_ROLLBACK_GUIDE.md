# Customer Rollback Guide

## Rollback Target

Use the previous Git commit or branch before `release/customer-demo-rc1` if a customer demo blocker appears.

## Steps

1. Stop local services:
   - `Get-CimInstance Win32_Process -Filter "name = 'python.exe'" | Where-Object { $_.CommandLine -like '*uvicorn backend.main:app*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }`
   - Stop the frontend dev server terminal if one is running.
2. Switch to the last known good commit or branch.
3. Rebuild catalog if needed:
   - `python -c "from src.config import get_settings; from src.catalog.profiler import build_catalog; from src.ingestion.cache_manager import ParquetCache; s=get_settings(); build_catalog(ParquetCache(s.cache_dir).load_tables(), s.cache_dir)"`
4. Start backend:
   - `python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000`
5. Start frontend:
   - `cd frontend`
   - `npm run dev`

## Data Safety

Do not delete `data/uploaded_files.json`, `data/uploads`, `cache/manifest.json`, or `cache/tables` during rollback unless the customer explicitly asks to reset uploaded data.
