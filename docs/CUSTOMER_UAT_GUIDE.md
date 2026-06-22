# Customer UAT Guide

## Scope

Use these 60 questions to validate the web chatbot from a customer perspective. The first priority is that overview/schema/sample/quality questions do not become fake downtime aggregations.

## How to Test

1. Open the React web app and create a fresh conversation.
2. Ask each question exactly as written.
3. Mark Pass when the behavior matches the expected behavior, even if wording is different.
4. Mark Fail when the app answers a different question, invents data, runs unsafe SQL, or defaults to total downtime for a metadata question.
5. Attach a screenshot for failures and note whether the debug SQL is empty or populated.

## 60 UAT Questions

| ID | Category | Question | Expected behavior |
|---|---|---|---|
| CUST-001 | data_overview | data có gì | Return catalog overview, no analytical SQL. |
| CUST-002 | data_overview | nội dung của data | Return catalog overview, no analytical SQL. |
| CUST-003 | data_overview | dữ liệu này nói về gì | Return catalog overview, no analytical SQL. |
| CUST-004 | data_overview | có những file nào | Return catalog overview, no analytical SQL. |
| CUST-005 | data_overview | tóm tắt dữ liệu đang có | Return catalog overview, no analytical SQL. |
| CUST-006 | data_overview | hệ thống đang đọc những bảng nào | Return catalog overview, no analytical SQL. |
| CUST-007 | data_overview | cho tôi xem tổng quan data | Return catalog overview, no analytical SQL. |
| CUST-008 | data_overview | data overview của hệ thống | Return catalog overview, no analytical SQL. |
| CUST-009 | data_overview | data? | Return catalog overview, no analytical SQL. |
| CUST-010 | data_overview | có gì? | Return catalog overview, no analytical SQL. |
| CUST-011 | schema_metadata | có những cột nào | Return schema/catalog metadata, no analytical SQL. |
| CUST-012 | schema_metadata | cho tôi xem schema | Return schema/catalog metadata, no analytical SQL. |
| CUST-013 | schema_metadata | kiểu dữ liệu của từng cột | Return schema/catalog metadata, no analytical SQL. |
| CUST-014 | schema_metadata | cột nào chứa thời gian | Return schema/catalog metadata, no analytical SQL. |
| CUST-015 | schema_metadata | cột nào là số | Return schema/catalog metadata, no analytical SQL. |
| CUST-016 | schema_metadata | file nào nhiều dòng nhất | Return schema/catalog metadata, no analytical SQL. |
| CUST-017 | schema_metadata | bảng nào chứa thông tin máy | Return schema/catalog metadata, no analytical SQL. |
| CUST-018 | schema_metadata | có quan hệ nào giữa các bảng | Return schema/catalog metadata, no analytical SQL. |
| CUST-019 | schema_metadata | columns của downtime là gì | Return schema/catalog metadata, no analytical SQL. |
| CUST-020 | schema_metadata | schema loss assignment | Return schema/catalog metadata, no analytical SQL. |
| CUST-021 | sample_data | xem 5 dòng đầu downtime | Return limited sample rows. |
| CUST-022 | sample_data | cho vài dòng mẫu | Return limited sample rows. |
| CUST-023 | sample_data | hiển thị 10 bản ghi mẫu downtime | Return limited sample rows. |
| CUST-024 | sample_data | sample rows của loss assignment | Return limited sample rows. |
| CUST-025 | sample_data | preview entry transaction | Return limited sample rows. |
| CUST-026 | sample_data | xem thử dữ liệu ra vào cổng | Return limited sample rows. |
| CUST-027 | data_quality | có null không | Return quality summary. |
| CUST-028 | data_quality | cột nào thiếu dữ liệu nhiều nhất | Return schema/catalog metadata, no analytical SQL. |
| CUST-029 | data_quality | có duplicate không | Return quality summary. |
| CUST-030 | data_quality | có duration âm không | Return quality summary. |
| CUST-031 | data_quality | có ngày kết thúc trước ngày bắt đầu không | Return quality summary. |
| CUST-032 | data_quality | data quality của downtime | Return quality summary. |
| CUST-033 | data_quality | bảng nào có nhiều null nhất | Return quality summary. |
| CUST-034 | aggregation | Tổng số bản ghi downtime là bao nhiêu? | Return validated aggregate result. |
| CUST-035 | aggregation | Tổng thời gian downtime là bao nhiêu? | Return validated aggregate result. |
| CUST-036 | aggregation | Downtime trung bình là bao nhiêu? | Return validated aggregate result. |
| CUST-037 | aggregation | Downtime lớn nhất là bao nhiêu? | Return validated aggregate result. |
| CUST-038 | aggregation | Downtime nhỏ nhất là bao nhiêu? | Return validated aggregate result. |
| CUST-039 | aggregation | median downtime là bao nhiêu? | Return validated aggregate result. |
| CUST-040 | aggregation | Có bao nhiêu máy khác nhau trong downtime? | Return validated aggregate result. |
| CUST-041 | aggregation | Có bao nhiêu nguyên nhân tổn thất khác nhau? | Return validated aggregate result. |
| CUST-042 | aggregation | Đếm số lần dừng máy | Return validated aggregate result. |
| CUST-043 | aggregation | Tổng giá trị cân là bao nhiêu? | Return validated aggregate result. |
| CUST-044 | aggregation | Số cổng khác nhau là bao nhiêu? | Return validated aggregate result. |
| CUST-045 | aggregation | Thời gian dừng tổng cộng? | Return validated aggregate result. |
| CUST-046 | group_ranking | Top 5 máy theo tổng downtime | Return grouped/ranked result. |
| CUST-047 | group_ranking | Bottom 5 máy theo tổng downtime | Return grouped/ranked result. |
| CUST-048 | group_ranking | Top 10 nguyên nhân theo số lần xuất hiện | Return grouped/ranked result. |
| CUST-049 | group_ranking | Nhóm tổn thất có tổng thời gian lớn nhất | Return grouped/ranked result. |
| CUST-050 | group_ranking | Đếm số lần dừng theo máy | Return grouped/ranked result. |
| CUST-051 | group_ranking | Tổng downtime theo nhóm tổn thất | Return grouped/ranked result. |
| CUST-052 | group_ranking | Máy có downtime trung bình cao nhất | Return grouped/ranked result. |
| CUST-053 | group_ranking | Nguyên nhân nào gây downtime lâu nhất | Return grouped/ranked result. |
| CUST-054 | group_ranking | Xếp hạng nguyên nhân theo số lần dừng | Return grouped/ranked result. |
| CUST-055 | group_ranking | Top máy theo từng tháng | Return grouped/ranked result. |
| CUST-056 | group_ranking | Top 3 nhóm tổn thất theo downtime | Return grouped/ranked result. |
| CUST-057 | group_ranking | Máy nào dừng nhiều lần nhất | Return grouped/ranked result. |
| CUST-058 | time_reasoning | Tổng downtime tháng đầu tiên trong dữ liệu | Handle time filters/granularity or return data range. |
| CUST-059 | time_reasoning | Tổng downtime tháng gần nhất trong dữ liệu | Handle time filters/granularity or return data range. |
| CUST-060 | time_reasoning | Downtime theo ngày | Handle time filters/granularity or return data range. |

## Mandatory Acceptance Checks

- `nội dung của data` returns a catalog/data overview, not total downtime.
- Metadata questions return no generated analytical SQL.
- Ambiguous questions ask for clarification.
- Unsafe database or local-path requests are refused.
- Follow-up turns keep context or fail safely with a focused clarification.