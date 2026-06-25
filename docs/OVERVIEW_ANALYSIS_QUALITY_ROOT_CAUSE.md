# Overview Analysis Quality Root Cause

## Problem

The open-ended overview flow for prompts such as `Phân tích data này.` was grounded, but it often selected low-value facts such as the mode or completeness of `No.`, `STT`, row numbers, IDs, or constant columns. The answer was technically traceable to the file, but it was not useful for a business user.

Example failure pattern:

```text
Generic overview request
-> profile every column
-> choose easy-to-compute column facts
-> promote row index / ID / 100% completeness
-> LLM paraphrases the weak insight
```

## Root Causes

1. Column profiling did not separate technical roles from business roles strongly enough.
2. Sequential row numbers and high-cardinality identifiers were eligible for insight ranking.
3. Constant columns were treated as ordinary categorical dimensions.
4. Domain selection was too eager when generic names such as `category` or `amount` appeared.
5. Insight ranking favored simple mode/completeness facts over business-value metrics.
6. Data-quality findings could displace core domain insights in the top results.
7. The LLM composer received raw or weak overview facts and could make them sound more important than they were.
8. Validators checked grounding, but not business usefulness, diversity, or triviality.

## Implemented Fix

The overview flow now uses a domain-aware pipeline:

```text
schema profiling
-> semantic column role classification
-> dataset capability profile
-> domain-aware insight candidates
-> trivial insight filter
-> business-value scoring
-> diversity gate
-> overview AnswerBrief
-> constrained composer payload
-> response quality validator
```

## Semantic Column Roles

`ColumnSemanticProfile` classifies each column into roles such as:

- `ROW_INDEX`
- `IDENTIFIER`
- `TECHNICAL_METADATA`
- `DATETIME`
- `DURATION`
- `NUMERIC_MEASURE`
- `CATEGORICAL_DIMENSION`
- `TEXT_DESCRIPTION`
- `BOOLEAN_FLAG`
- `UNKNOWN`

It also assigns business roles such as `machine`, `downtime_duration`, `loss_group`, `loss_reason`, `transaction_value`, `transaction_date`, `gate`, `vehicle`, `quantity`, and `category`.

The classifier now excludes:

- Names like `No.`, `STT`, `Index`, `Row`, `Unnamed`, `UUID`, `GUID`, `internal_id`, `source_row`, `sheet_row`.
- Sequential values such as `1, 2, 3, ...`.
- High-uniqueness identifiers.
- Technical metadata and duplicate grouping fields.
- Near-constant columns for insight selection.

Datetime detection is prioritized before identifier detection so unique timestamps are still usable for date range and trend analysis.

## Domain Capability Profile

`DatasetCapabilityProfile` infers the best supported domain from semantic roles and source metadata:

- `machine_downtime`
- `loss_assignment`
- `entry_transaction`
- `generic_tabular`

The classifier no longer treats a generic `category` column as loss data by default, and no longer treats a generic `amount` or `sales` measure as an entry transaction unless there is additional transaction evidence such as a transaction date, gate, vehicle, or source metadata.

## Overview Planner

The planner produces domain-specific candidates:

- Machine downtime: total downtime, top machine, top cause/group, event count, trend over time.
- Loss assignment: loss duration, group/type distribution, concentration of top categories.
- Entry transaction: transaction count over time, total/average value, top gate/entity/group.
- Generic tabular: business dimension distribution, numeric measure summary, time coverage when available.

## Business-Value Scoring

Insight candidates are scored with:

```text
0.25 * domain relevance
+ 0.20 * magnitude
+ 0.20 * actionability
+ 0.15 * evidence strength
+ 0.10 * novelty
+ 0.10 * user relevance
- triviality penalty
```

Technical columns are removed before scoring. Data-quality findings remain available, but their score is lower than core business insights so they do not crowd out the main analysis.

## Trivial Insight Filter

`TrivialInsightFilter` rejects insights such as:

- A row number appears once.
- A unique ID has 100% distinct values.
- A column is 100% complete.
- A constant column has the same value.
- A technical metadata column is the primary dimension.

Completeness is only promoted when missingness is material and affects a business column.

## Diversity Gate

`select_diverse_insights` limits repetition by insight type, metric, and entity. Machine downtime insight metrics are separated into `machine_total_downtime`, `cause_total_downtime`, and `daily_total_downtime` so the selected set reflects genuinely different views.

## Composer Policy

The open-ended composer receives an `OverviewAnswerBrief` instead of raw schema exploration. It may only express selected insights, evidence, comparisons, and limitations. It is instructed not to select new columns, invent metrics, use technical columns, or add generic filler.

The validator rejects filler-only phrasing such as:

- `mỗi góc nhìn đo một lát cắt khác nhau`
- `dữ liệu cho thấy nhiều thông tin hữu ích`
- `kết quả có thể hỗ trợ ra quyết định`
- `cần xem xét thêm để có kết luận chính xác`

## Evaluation Coverage

Added benchmarks:

- `evaluation/run_column_semantic_role_benchmark.py`
- `evaluation/run_overview_business_value_benchmark.py`
- `evaluation/run_insight_diversity_benchmark.py`

Artifacts:

- `artifacts/column_semantic_role_results.json`
- `artifacts/overview_business_value_results.json`
- `artifacts/insight_diversity_results.json`
- `artifacts/trivial_insight_rejections.json`
- `artifacts/manual_overview_quality_uat.json`

## Manual UAT Result

The real Excel files were tested with `Phân tích data này.`:

- `Machine_Downtime_20260203_100753.xlsx`: selected machine downtime, cause/group downtime, and daily trend.
- `Loss_Assignment_20260203_100840.xlsx`: selected loss duration, group distribution, and concentration.
- `EntryTransaction_20260203_164943.xlsx`: selected transaction trend, total value, and gate/group distribution.

No selected insight used `No.`, `STT`, row number, identifier, UUID/GUID, or duplicate metadata as the primary insight.

## Remaining Limitations

- The classifier is rule-based and conservative. It is safer for production guardrails, but ambiguous schemas can still fall back to generic tabular analysis.
- Domain detection uses semantic roles and metadata, not exact filenames, but richer customer-specific aliases would improve recall.
- The composer is constrained by the selected `AnswerBrief`; if upstream ingestion misses a header or role, the answer will not invent missing business context.
