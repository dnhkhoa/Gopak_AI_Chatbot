# Conversation Regression Analysis

## Baseline

Candidate A baseline was 140/240 with 20 repeated clarification loops, REAL_LLM calls 0, file-scoped benchmark 88/320, and row-level benchmark timing out.

## Root Causes

- Semantic routing was evaluated too late and too narrowly.
- Row-level shortcuts interpreted analytical phrases such as `thang gan nhat` as latest-record lookup.
- File-scoped planners defaulted to machine downtime instead of the single active scoped table.
- Clarification pending flows started even when the user had already provided complete slots.
- EntryTransaction generated table names did not preserve the `entrytransaction` prefix, so detectors needed to inspect source filename as well.
- Row-level benchmark forced catalog re-ingest with `force=True`.

## Current Results

- Conversation development: 240/240, loop 0, REAL_LLM calls 33.
- Conversation holdout: 120/120, loop 0, REAL_LLM calls 17.
- Conversation total: 360/360.
- Row-level benchmark: 81/81.
- File-scoped benchmark: 266/320.

## Residual File-Scoped Risk

File-scoped deterministic, file-scope metadata, clarification, refusal, and cross-file sequences now pass fully. Remaining file-scoped failures are concentrated in real-LLM-like freeform requests, multipart report expectations, safe-failure response type expectations, and context-sequence schema oracle mismatch.

## Release Gate

Conversation architecture is ready for controlled internal testing. Customer release remains blocked until file-scoped freeform/multipart behavior is raised above the release threshold and the response-type oracle is reconciled.
