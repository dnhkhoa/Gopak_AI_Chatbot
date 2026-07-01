from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

import duckdb
import pandas as pd

from src.query.schemas import QueryPlan
from src.query.result_validator import ResultValidator
from src.query.sql_builder import SQLBuilder
from src.query.validator import PlanValidator


@dataclass
class QueryResult:
    dataframe: pd.DataFrame
    sql: str
    params: list
    latency_ms: float


class SafeQueryExecutor:
    def __init__(self, catalog: dict):
        self.catalog = catalog
        self.validator = PlanValidator(catalog)
        self.builder = SQLBuilder(catalog)
        self.result_validator = ResultValidator()
        self.query_timeout_seconds = int(catalog.get("query_timeout_seconds") or 30)
        self.query_memory_limit = str(catalog.get("query_memory_limit") or "512MB")

    def execute(self, plan: QueryPlan) -> QueryResult:
        self.validator.validate(plan)
        sql, params = self.builder.build(plan)
        normalized_sql = sql.lstrip().upper()
        if not (normalized_sql.startswith("SELECT ") or normalized_sql.startswith("WITH ")):
            raise ValueError("Only SELECT queries are allowed.")
        start = perf_counter()
        with duckdb.connect(database=":memory:") as con:
            con.execute(f"SET memory_limit='{self.query_memory_limit}'")
            con.execute(f"SET enable_progress_bar=false")
            con.execute(f"SET threads=2")
            df = con.execute(sql, params).fetchdf()
        self.result_validator.validate(df, plan)
        latency_ms = (perf_counter() - start) * 1000
        return QueryResult(dataframe=df, sql=sql, params=params, latency_ms=latency_ms)
