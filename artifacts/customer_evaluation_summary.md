# Customer Evaluation Summary

Total cases: 180
Passed: 172/180 (95.6%)
Default downtime false positives: 0
LLM calls recorded: 0
P50 latency: 376.6 ms
P95 latency: 517.1 ms

## By Set

| Set | Passed | Total | Accuracy |
|---|---:|---:|---:|
| development | 128 | 130 | 98.5% |
| holdout | 44 | 50 | 88.0% |

## By Category

| Category | Passed | Total | Accuracy |
|---|---:|---:|---:|
| aggregation | 10 | 12 | 83.3% |
| ambiguous | 6 | 6 | 100.0% |
| artifact_visual | 10 | 10 | 100.0% |
| data_overview | 10 | 10 | 100.0% |
| data_quality | 7 | 7 | 100.0% |
| empty_result | 5 | 5 | 100.0% |
| group_ranking | 12 | 12 | 100.0% |
| long_combined | 8 | 10 | 80.0% |
| long_natural | 6 | 6 | 100.0% |
| mixed_language | 5 | 5 | 100.0% |
| multi_turn | 23 | 24 | 95.8% |
| multiple_filters | 10 | 10 | 100.0% |
| out_of_domain | 6 | 6 | 100.0% |
| sample_data | 6 | 6 | 100.0% |
| schema_metadata | 9 | 10 | 90.0% |
| security | 5 | 5 | 100.0% |
| semantic_matching | 8 | 10 | 80.0% |
| short_questions | 5 | 5 | 100.0% |
| time_reasoning | 12 | 12 | 100.0% |
| typo_no_accent | 9 | 9 | 100.0% |

## Failure Types

| Failure type | Count |
|---|---:|
| ANALYTICAL_FAILURE | 6 |
| METADATA_SQL_OR_WRONG_INTENT | 1 |
| MULTITURN_FAILURE | 1 |