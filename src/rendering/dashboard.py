from __future__ import annotations

import pandas as pd


def kpi_cards(df: pd.DataFrame) -> list[dict]:
    cards = [{"label": "Rows", "value": int(len(df))}]
    for column in df.columns:
        if pd.api.types.is_numeric_dtype(df[column]):
            cards.append({"label": f"Sum {column}", "value": float(df[column].sum())})
            break
    return cards[:4]

