# Semantic Routing Policy

## Deterministic First

Simple, high-confidence analytical queries stay deterministic: record lookup, schema/sample/data overview, explicit top-N, totals, counts, and scoped file metadata.

## REAL_LLM Required

REAL_LLM is required when the question asks for judgment or semantic interpretation, including:

- `co ve`, `gay van de`, `bat thuong`, `dang chu y`
- `hop ly`, `lo nhat`, `tuong tu`
- `lien quan`, `gan voi`, `giong`
- multipart requests with additional interpretation beyond known deterministic detectors

## Guardrails

REAL_LLM may not bypass file scope. Plans are validated against the active scoped catalog before SQL execution. If the LLM fails twice, the system may use a pre-existing deterministic candidate only after validating it and recording `semantic_fallback_after_llm_failure=true`.

## Non-LLM Paths

Clarification stays non-LLM for missing slots such as bare `top` or `ve bieu do tong quan`. Row-level lookup stays non-LLM for explicit record/source-row queries.
