from __future__ import annotations

from src.catalog.profiler import build_catalog
from src.config import get_settings
from src.ingestion.cache_manager import ParquetCache
from src.ingestion.workbook_scanner import find_excel_files
from src.production.ingestion import refresh_production_bundle


def main(force: bool = False) -> dict:
    settings = get_settings()
    if settings.customer_production_mode:
        return refresh_production_bundle(settings, force=force)
    files = find_excel_files(settings.root)
    cache = ParquetCache(settings.cache_dir)
    tables = cache.refresh(files, force=force)
    return build_catalog(tables, settings.cache_dir)


if __name__ == "__main__":
    catalog = main(force=False)
    print(f"Loaded {len(catalog.get('tables', []))} tables. Catalog: cache/data_catalog.json")
