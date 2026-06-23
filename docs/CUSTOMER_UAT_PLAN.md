# Customer UAT Plan

## Scope

Validate the customer demo flow against the React frontend and FastAPI backend with the three production Excel workbooks loaded:

- EntryTransaction_20260203_164943.xlsx
- Loss_Assignment_20260203_100840.xlsx
- Machine_Downtime_20260203_100753.xlsx

## Critical Flows

1. Open the web app and confirm backend health is OK.
2. Select each workbook and verify the active file state is visible.
3. Ask overview, schema, and sample-row questions for the selected file.
4. Ask scoped analytical questions:
   - `Top 5 may theo tong downtime`
   - `Top 5 nguyen nhan ton that`
   - `Tong gia tri can theo cong`
5. Switch file A -> B -> C -> A and verify answers stay scoped to the selected file.
6. Restart backend and confirm conversation/file context still works.
7. Upload a new workbook, select it, query it, and delete it.

## Exit Criteria

- Black-box UAT has zero critical failures.
- No query returns rows from a non-active workbook.
- Upload lifecycle leaves no stale metadata, parquet, or catalog references.
- Clarification/refusal responses are acceptable for unsupported or ambiguous asks.

Latest automated UAT artifact: `artifacts/black_box_customer_uat.json`.
