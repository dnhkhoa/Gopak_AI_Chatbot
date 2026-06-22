# Offline Excel Analytics Chatbot

Streamlit demo for asking Vietnamese questions over local Excel files without cloud APIs.

## Architecture

Excel workbooks are scanned dynamically, headers are detected, tables are normalized, and parquet files are cached by file hash. DuckDB runs read-only analytical SQL generated from validated Pydantic query plans. Ollama is the preferred local LLM planner; when Ollama is unavailable, a schema-driven heuristic fallback can keep the demo usable without sending data outside the machine.

## Setup on Windows

1. Install Python 3.11.
2. Install Ollama for Windows.
3. From this repository, run:

```powershell
.\setup.ps1
```

4. Copy or edit `.env` if needed. Defaults:

```env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3.5:9b
```

5. Start Ollama and make sure the model exists:

```powershell
ollama list
ollama pull qwen3.5:9b
```

6. Run ingestion and the app:

```powershell
.\run.ps1
```

## Developer Commands

```powershell
python scripts_ingest.py
python -m pytest
python evaluation.py
streamlit run app.py
```

## Outputs

- Parquet cache: `cache/tables/`
- Data catalog: `cache/data_catalog.json`
- HTML and Excel reports: `reports/`
- Evaluation: `artifacts/evaluation_results.json`
- Latency benchmark: `artifacts/latency_benchmark.csv`
- Progress report: `docs/PROGRESS_EVALUATION.md`
- Data profile: `docs/DATA_PROFILE.md`

## Privacy and Offline Guarantee

Runtime data stays local. The app does not call OpenAI, cloud LLM APIs, vector databases, or third-party services. Ollama must run locally. The prompt contains schema/catalog metadata and small samples, not full DataFrames.

## Troubleshooting

- If `duckdb` is missing, run `python -m pip install -r requirements.txt`.
- If Ollama is unavailable, start Ollama and check `http://localhost:11434`.
- If `qwen3.5:9b` is not listed, run `ollama pull qwen3.5:9b`.
- If Streamlit cannot start, verify the virtual environment was created with Python 3.11.

