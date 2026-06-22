from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pandas as pd

from src.conversation.schemas import ResultCacheRecord


class ResultCache:
    def __init__(self, root: Path):
        self.root = Path(root)

    def save_dataframe(self, conversation_id: str, turn_id: str, df: pd.DataFrame) -> ResultCacheRecord | None:
        if df is None or df.empty:
            return None
        cache_id = str(uuid4())
        folder = self.root / "conversations" / conversation_id
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{turn_id}.parquet"
        df.to_parquet(path, index=False)
        return ResultCacheRecord(
            id=cache_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
            parquet_path=str(path),
            row_count=int(len(df)),
            result_schema_json=df.dtypes.astype(str).to_json(),
        )

    def load_dataframe(self, parquet_path: str | None) -> pd.DataFrame | None:
        if not parquet_path:
            return None
        path = Path(parquet_path)
        if not path.exists():
            return None
        return pd.read_parquet(path)
