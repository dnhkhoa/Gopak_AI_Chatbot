# Header Detection Design

Updated: 2026-06-22

## Candidate Scanning

The detector scans at least the first 200 rows. It scores each contiguous non-empty segment as a header candidate.

Candidate features:

- Non-empty cell count.
- Text-cell ratio.
- Unique header ratio.
- Contiguous column segment.
- Semantic column-name hits.
- Data density in following rows.
- Consecutive valid records below the header.

## Metadata Rejection

Rows are rejected when they look like report metadata:

- `Export time`
- `From time`
- `To time`
- `Reporter`
- `Total results`
- `Factory`
- `Workshop`
- `Line`
- `Machine`

Key/value rows with few cells and colon-like labels are not accepted as table headers.

## Boundary Detection

After a header is selected, ingestion:

- Determines first and last data rows.
- Ignores repeated headers in the body.
- Stops at footer/total rows.
- Keeps intermittent nulls inside records.
- Drops only blank/numeric artifact columns.
- Keeps business columns such as `Note` even when all values are null.

## Confidence And Evidence

Each profile stores:

- `header_confidence`
- `header_evidence`
- `first_column`
- `last_column`
- `last_data_row`
- `validation`

## Benchmark

`evaluation/run_header_detection_benchmark.py` creates 15 derived workbook fixtures covering:

- Header rows 1, 10, and 35.
- Metadata above the table.
- Leading empty columns.
- Trailing garbage columns.
- Repeated headers.
- Footer totals.
- Multiple sheets.
- Merged-title-like metadata.
- Vietnamese/English headers.
- Header extra/garbage columns.
- Non-sequential `No.` shape.
- Metadata rows that partially resemble headers.

Latest result:

- 15/15 passed.
- Accuracy: 100%.
