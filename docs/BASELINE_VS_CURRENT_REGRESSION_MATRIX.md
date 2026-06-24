# Baseline vs Current Regression Matrix

Generated: 2026-06-24T03:21:33.516456+00:00

## Commits

- Baseline: `919adb0`
- Current before fixes: `1c71f28`
- Fix branch: `feature/demo-conversation-seeding`

## A/B Result

| Area | Baseline | Current before fix | Post-fix current | Classification |
| --- | --- | --- | --- | --- |
| compileall + pytest by file | {'total': 26, 'passed': 24, 'failed': 0, 'timeout': 2} | same harness | `78 passed` full local pytest | pass |
| complex analytics | full file timed out; sharded passed | full file timed out; sharded passed | full pytest passed | harness timeout, not product regression |
| file-scoped benchmark | 320/320 | 267/320 | 320/320 | fixed regression |
| LLM invocation benchmark | 12/12 | 10/12 | 12/12 | fixed regression |
| chart fulfillment | n/a | n/a | passed | pass |
| report orchestration | n/a | n/a | passed | pass |
| conversation-state contamination | n/a | n/a | passed | pass |
| manual 8-turn UAT | n/a | n/a | passed | pass |
| persistence restart UAT | n/a | n/a | passed | pass |
| export validation | n/a | n/a | passed | pass |
| clean environment smoke | n/a | n/a | passed | pass |

## Regressions Fixed

1. Short refinement turns (`Chi lay thang gan nhat`, `Ve bieu do cot`, `Doi thanh top 3`, `Quay lai cau dau tien`) were being classified as new requests and losing previous plan context.
2. EntryTransaction insight questions containing Vietnamese `ve` as "about" were misclassified as chart requests.
3. Open-ended dataset analysis and negated chart phrases were protected with regression tests from the earlier pass.

## Remaining Limitations

- Browser screenshot capture timed out in the Codex desktop environment; DOM/API/build/UAT evidence is available.
- Vite emits a chunk-size warning after build.
- FastAPI tests show deprecation warnings only.
