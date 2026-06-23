from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.config import Settings
from src.conversation.state import ConversationState
from src.query.schemas import HavingCondition, MetricSpec, QueryPlan, RankingSpec, SortSpec
from src.query_understanding.catalog_utils import business_columns, find_table, role_column
from src.query_understanding.dimension_detector import detect_dimension
from src.query_understanding.entity_matcher import EntityMatcher
from src.query_understanding.filter_parser import parse_filters
from src.query_understanding.metric_detector import detect_metric
from src.query_understanding.operation_detector import detect_operation
from src.query_understanding.output_detector import detect_output
from src.query_understanding.text import normalize_text
from src.query_understanding.time_resolver import resolve_time
from src.query_understanding.topn_detector import detect_topn
from src.routing.confidence import clamp_confidence


@dataclass
class DeterministicParse:
    plan: QueryPlan | None
    confidence: float
    reason: str
    evidence: list[str] = field(default_factory=list)
    unresolved_terms: list[str] = field(default_factory=list)


class DeterministicPlanner:
    def __init__(self, catalog: dict, settings: Settings):
        self.catalog = catalog
        self.settings = settings
        self.matcher = EntityMatcher(catalog, settings.artifacts_dir)

    def parse(self, question: str, state: ConversationState) -> DeterministicParse:
        q = normalize_text(question)
        table = self._select_table(q, state)
        if not table:
            return DeterministicParse(None, 0.0, "No supported table matched.")

        duration = role_column(table, "duration_seconds")
        machine = role_column(table, "machine")
        start_time = role_column(table, "start_time")
        loss_name = role_column(table, "loss_name")
        loss_group = role_column(table, "loss_group")

        generic_entry = self._entrytransaction_plan(q, table)
        if generic_entry is not None:
            return generic_entry
        freeform_insight = self._freeform_insight_plan(q, table, duration, machine, loss_name, loss_group)
        if freeform_insight is not None:
            return freeform_insight

        operation = detect_operation(question)
        output = detect_output(question)
        metric = detect_metric(question, duration, machine, loss_name)
        dimensions = detect_dimension(question, machine, loss_name, loss_group, start_time)
        topn = detect_topn(question)
        time = resolve_time(question, table, start_time)
        filters = parse_filters(question, table, machine, loss_group, loss_name, duration, self.matcher)
        group_by_requested = any(term in q for term in ["theo", "thep", "moi", "tung", "so sanh"]) or ("nao" in q and bool(dimensions.value))
        ranking_requested = topn.value is not None or (
            bool(dimensions.value)
            and any(term in q for term in ["nhat", "te nhat", "can chu y", "hay bi", "dang ke", "chiem nhieu", "tao ra"])
        )
        chart_requested = operation.value == "chart"
        complex_requested = any(term in q for term in ["dong thoi", "hien thi them", "ty le", "t? l?", "ty trong", "phan tram", "ph?n tr?m", "cao hon muc trung binh", "cao h?n m?c trung b?nh", "voi moi"])
        having = []
        ranking = None

        if any(term in q for term in ["phan tram", "ph?n tr?m", "ty le", "t? l?", "ty trong"]):
            dim = loss_name if any(term in q for term in ["nguyen nhan", "nguy?n nh?n", "loi", "su co"]) else loss_group if any(term in q for term in ["nhom", "nh?m"]) else machine
            metric_payloads = [{"aggregation": "count", "column": None, "name": "row_count", "percentage_of_total": True}]
            dims = [dim] if dim else list(dimensions.value or [])
            confidence = 0.93 if dims else 0.60
        elif any(term in q for term in ["cao hon muc trung binh", "cao h?n m?c trung b?nh"]) and duration:
            dim = machine if any(term in q for term in ["may", "m?y"]) else loss_group if any(term in q for term in ["nhom", "nh?m"]) else loss_name
            metric_payloads = [{"aggregation": "sum", "column": duration, "name": "total_duration_seconds"}]
            dims = [dim] if dim else list(dimensions.value or [])
            having = [HavingCondition(metric_alias="total_duration_seconds", operator="greater_than", comparison="group_average")]
            confidence = 0.94 if dims else 0.55
        elif self._asks_multiple_metrics(q):
            metric_payloads = [
                {"aggregation": "sum", "column": duration, "name": "total_duration_seconds"},
                {"aggregation": "count", "column": None, "name": "row_count"},
                {"aggregation": "avg", "column": duration, "name": "avg_duration_seconds"},
            ]
            dims = list(dimensions.value or [])
            confidence = 0.94 if duration else 0.60
        elif operation.value in {"dashboard", "report"}:
            metric_payloads = [
                {"aggregation": "sum", "column": duration, "name": "total_duration_seconds"},
                {"aggregation": "count", "column": None, "name": "row_count"},
            ]
            dims = [machine] if machine else []
            confidence = 0.90 if duration and machine else 0.70
        elif metric.value:
            metric_payloads = [metric.value]
            dims = list(dimensions.value or [])
            confidence = metric.confidence
        elif (ranking_requested or chart_requested) and dimensions.value and duration:
            metric_payloads = [{"aggregation": "sum", "column": duration, "name": "total_duration_seconds"}]
            dims = list(dimensions.value or [])
            confidence = 0.88
        elif dimensions.value and any(term in q for term in ["la gi", "cac ", "nhung ", "truong hop", "du lieu"]):
            metric_payloads = []
            dims = list(dimensions.value or [])
            confidence = 0.88
        else:
            return DeterministicParse(None, 0.35, "Metric is unresolved.", unresolved_terms=["metric"])

        if time.granularity and start_time and start_time not in dims:
            dims.insert(0, start_time)

        if metric_payloads and not (group_by_requested or ranking_requested or chart_requested or time.granularity or having or any(payload.get("percentage_of_total") for payload in metric_payloads)):
            dims = []

        if filters.value and metric_payloads and not group_by_requested and not ranking_requested and not chart_requested:
            dims = []

        if ranking_requested and not dims:
            inferred = self._ranking_dimension(q, machine, loss_name, loss_group, start_time)
            if inferred:
                dims = [inferred]
        if any(term in q for term in ["theo", "moi", "tung", "so sanh"]) and not dims and not time.granularity:
            confidence -= 0.25

        metrics = [MetricSpec(**payload) for payload in metric_payloads]
        sort = []
        limit = 20
        if filters.value and "co" in q and "nao" in q and any(flt.column == duration for flt in filters.value):
            metrics = []

        if topn.value and dims:
            limit = int(topn.value["limit"])
            sort_col = metrics[0].name or "row_count"
            sort = [SortSpec(column=sort_col, direction=topn.value["direction"])]
            if time.granularity and len(dims) >= 2:
                ranking = RankingSpec(partition_by=[dims[0]], order_by=sort_col, direction=topn.value["direction"], top_n=None if topn.value["limit"] == 20 else int(topn.value["limit"]))
                limit = 500
        elif ranking_requested and dims and metrics:
            limit = 5
            sort = [SortSpec(column=metrics[0].name or "row_count", direction="desc")]
        elif dims and not time.granularity and metrics:
            # Analytical grouped tables should be deterministic and useful.
            sort = [SortSpec(column=metrics[0].name or "row_count", direction="desc")]
        elif time.granularity and dims and metrics:
            sort = [SortSpec(column=dims[0], direction="asc"), SortSpec(column=metrics[0].name or "row_count", direction="desc")]
        elif dims and not metrics:
            sort = [SortSpec(column=dims[0], direction="asc")]
        elif time.granularity and start_time:
            sort = [SortSpec(column=start_time, direction="asc")]

        intent = operation.value if operation.value in {"chart", "dashboard", "report"} else "query"
        plan = QueryPlan(
            intent=intent,
            tables=[table["table_name"]],
            filters=[*filters.value, *time.filters],
            dimensions=[dim for dim in dims if dim],
            metrics=metrics,
            having=having,
            ranking=ranking,
            time_granularity=time.granularity,
            sort=sort,
            limit=limit,
            output=output.value,
            query_complexity="complex" if complex_requested or having or ranking or len(metrics) > 1 else "simple",
        )
        confidence = self._score_confidence(confidence, operation, output, dimensions, topn, time, filters, plan, q)
        evidence = operation.evidence + output.evidence + metric.evidence + dimensions.evidence + topn.evidence + time.evidence + filters.evidence
        return DeterministicParse(plan, confidence, "Deterministic detectors produced a validated analytical plan candidate.", evidence=evidence)

    def _asks_multiple_metrics(self, q: str) -> bool:
        metric_terms = 0
        metric_terms += int(any(term in q for term in ["tong downtime", "tong thoi gian", "tong thoi luong"]))
        metric_terms += int(any(term in q for term in ["so lan", "dem so lan", "lan dung"]))
        metric_terms += int(any(term in q for term in ["trung binh", "thoi luong trung binh"]))
        return metric_terms >= 2 or ("hien thi them" in q and metric_terms >= 1)

    def _entrytransaction_plan(self, q: str, table: dict) -> DeterministicParse | None:
        table_text = f"{table.get('table_name', '')} {table.get('source', '')}".lower()
        if "entrytransaction" not in table_text:
            return None
        table_name = table["table_name"]
        cols = {col.get("normalized_name") for col in table.get("columns", [])}
        if any(term in q for term in ["insight", "nhan xet", "luong xe", "ra vao cong", "tom tat"]) and {"cong", "loai_truy_cap"} & cols:
            dimension = "cong" if "cong" in cols else "loai_truy_cap"
            plan = QueryPlan(
                intent="query",
                tables=[table_name],
                dimensions=[dimension],
                metrics=[MetricSpec(aggregation="count", column=None, name="row_count")],
                sort=[SortSpec(column="row_count", direction="desc")],
                limit=5,
                output="table",
            )
            return DeterministicParse(plan, 0.92, "EntryTransaction freeform insight mapped to scoped gate/access volume.", evidence=["entry_insight"])
        if ("gia_tri_can" in q or "gia tri can" in q) and "gia_tri_can" in cols:
            plan = QueryPlan(
                intent="query",
                tables=[table_name],
                metrics=[MetricSpec(aggregation="sum", column="gia_tri_can", name="total_gia_tri_can")],
                output="text",
            )
            return DeterministicParse(plan, 0.96, "EntryTransaction numeric weight total detected.", evidence=["gia_tri_can"])
        if "cong" in q and any(term in q for term in ["bao nhieu", "khac nhau", "so cong"]) and "cong" in cols:
            plan = QueryPlan(
                intent="query",
                tables=[table_name],
                metrics=[MetricSpec(aggregation="count_distinct", column="cong", name="gate_count")],
                output="text",
            )
            return DeterministicParse(plan, 0.96, "EntryTransaction distinct gate count detected.", evidence=["cong"])
        return None

    def _freeform_insight_plan(
        self,
        q: str,
        table: dict,
        duration: str | None,
        machine: str | None,
        loss_name: str | None,
        loss_group: str | None,
    ) -> DeterministicParse | None:
        if not any(term in q for term in ["bat thuong", "nhan xet", "insight", "quan trong", "tom tat", "phan tich"]):
            return None
        if not duration:
            return None
        dimension = None
        if any(term in q for term in ["nhom", "bao tri", "san xuat"]):
            dimension = loss_group
        elif any(term in q for term in ["nguyen nhan", "ton that", "loi", "su co"]):
            dimension = loss_name
        elif machine:
            dimension = machine
        elif loss_group:
            dimension = loss_group
        elif loss_name:
            dimension = loss_name
        if not dimension:
            return None
        import re

        number = re.search(r"\b(\d{1,2})\b", q)
        limit = max(1, min(int(number.group(1)), 20)) if number else 5
        plan = QueryPlan(
            intent="query",
            tables=[table["table_name"]],
            dimensions=[dimension],
            metrics=[MetricSpec(aggregation="sum", column=duration, name="total_duration_seconds")],
            sort=[SortSpec(column="total_duration_seconds", direction="desc")],
            limit=limit,
            output="table",
        )
        return DeterministicParse(plan, 0.91, "Freeform scoped insight mapped to top duration contribution.", evidence=["freeform_insight"])

    def _select_table(self, q: str, state: ConversationState) -> dict | None:
        scoped_tables = self.catalog.get("tables", [])
        if len(scoped_tables) == 1:
            return scoped_tables[0]
        if state.active_tables and any(term in q for term in ["tren", "do", "ket qua", "chi lay", "ve top", "giu"]):
            active = next((table for table in scoped_tables if table["table_name"] == state.active_tables[0]), None)
            if active:
                return active
        if any(term in q for term in ["truy cap", "cong ra", "cong vao", "ra vao cong", "gia tri can", "bien so", "loai xe"]):
            return find_table(self.catalog, "entrytransaction")
        if any(term in q for term in ["setup", "vat tu", "cho vat tu", "chinh may", "gan voi"]):
            return find_table(self.catalog, "loss_assignment") or find_table(self.catalog, "machine_downtime")
        return find_table(self.catalog, "machine_downtime") or (scoped_tables[0] if scoped_tables else None)

    def _ranking_dimension(self, q: str, machine: str | None, loss_name: str | None, loss_group: str | None, start_time: str | None) -> str | None:
        if "may" in q:
            return machine
        if any(term in q for term in ["nguyen nhan", "loi", "su co"]):
            return loss_name
        if "nhom" in q:
            return loss_group
        if any(term in q for term in ["ngay", "tuan", "thang"]):
            return start_time
        return None

    def _score_confidence(
        self,
        base: float,
        operation,
        output,
        dimensions,
        topn,
        time,
        filters,
        plan: QueryPlan,
        q: str,
    ) -> float:
        confidence = base
        confidence += 0.02 if operation.confidence >= 0.90 else 0.0
        confidence += 0.02 if output.confidence >= 0.90 else 0.0
        confidence += 0.03 if filters.evidence else 0.0
        confidence += 0.03 if time.evidence else 0.0
        confidence += 0.03 if dimensions.evidence else 0.0
        if topn.value and plan.dimensions and plan.sort:
            confidence += 0.04
        if any(term in q for term in ["lien quan", "giong", "gan voi"]) and not filters.evidence:
            confidence -= 0.25
        if any(term in q for term in ["la gi", "cac ", "nhung "]) and plan.dimensions:
            confidence += 0.04
        if any(term in q for term in ["phan tram", "ph?n tr?m", "cao hon muc trung binh", "cao h?n m?c trung b?nh"]) and not (plan.having or any(metric.percentage_of_total for metric in plan.metrics)):
            confidence -= 0.35
        if plan.metrics and any(metric.column is None and metric.aggregation != "count" for metric in plan.metrics):
            confidence -= 0.35
        if plan.tables and plan.tables[0].startswith("entrytransaction") and any(term in q for term in ["downtime", "dung", "may"]):
            confidence -= 0.40
        return clamp_confidence(confidence)
