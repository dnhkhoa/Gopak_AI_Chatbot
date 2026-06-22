# Hybrid Evaluation Summary

## Overall

- Cases: 85
- Passed: 69
- Failed: 1
- Manual review: 15
- Accuracy: 81.18%
- P50 latency: 87.1 ms
- P95 latency: 118.8 ms
- LLM usage rate: 0.0%

## By Execution Mode

| Mode | Cases | Passed | Failed | Manual | Accuracy | P50 ms | P95 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| CLARIFICATION | 4 | 4 | 0 | 0 | 100.0% | 0.5 | 0.6 |
| DETERMINISTIC | 72 | 56 | 1 | 15 | 77.8% | 89.4 | 120.0 |
| REFUSAL | 9 | 9 | 0 | 0 | 100.0% | 0.4 | 0.7 |

## By Category

| Category | Total | Passed | Failed | Manual | Accuracy |
| --- | ---: | ---: | ---: | ---: | ---: |
| aggregation | 9 | 9 | 0 | 0 | 100.0% |
| ambiguity | 4 | 4 | 0 | 0 | 100.0% |
| artifact | 6 | 6 | 0 | 0 | 100.0% |
| boundary | 4 | 4 | 0 | 0 | 100.0% |
| filter | 6 | 6 | 0 | 0 | 100.0% |
| join | 5 | 5 | 0 | 0 | 100.0% |
| multi_turn | 15 | 0 | 0 | 15 | 0.0% |
| out_of_domain | 4 | 4 | 0 | 0 | 100.0% |
| paraphrase | 6 | 6 | 0 | 0 | 100.0% |
| semantic | 5 | 5 | 0 | 0 | 100.0% |
| time | 9 | 9 | 0 | 0 | 100.0% |
| top_n | 8 | 8 | 0 | 0 | 100.0% |
| typo | 4 | 3 | 1 | 0 | 75.0% |