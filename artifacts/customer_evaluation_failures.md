# Customer Evaluation Failures

Total failures: 8

## CUST-085 - ANALYTICAL_FAILURE

- Set: development
- Category: semantic_matching
- Question: kiểm tra chất lượng gây tổn thất nào
- Expected: ANALYTICAL_QUERY
- Actual: CLARIFICATION / clarification
- SQL: ``

## CUST-096 - ANALYTICAL_FAILURE

- Set: development
- Category: long_combined
- Question: Tạo báo cáo HTML gồm top máy, top nguyên nhân và xu hướng theo ngày.
- Expected: ANALYTICAL_QUERY
- Actual: SAFE_FAILURE / error
- SQL: ``

## CUST-018 - METADATA_SQL_OR_WRONG_INTENT

- Set: holdout
- Category: schema_metadata
- Question: có quan hệ nào giữa các bảng
- Expected: SCHEMA_INSPECTION
- Actual: CLARIFICATION / clarification
- SQL: ``

## CUST-043 - ANALYTICAL_FAILURE

- Set: holdout
- Category: aggregation
- Question: Tổng giá trị cân là bao nhiêu?
- Expected: ANALYTICAL_QUERY
- Actual: SAFE_FAILURE / error
- SQL: ``

## CUST-044 - ANALYTICAL_FAILURE

- Set: holdout
- Category: aggregation
- Question: Số cổng khác nhau là bao nhiêu?
- Expected: ANALYTICAL_QUERY
- Actual: CLARIFICATION / clarification
- SQL: ``

## CUST-089 - ANALYTICAL_FAILURE

- Set: holdout
- Category: semantic_matching
- Question: nhóm sản xuất có lỗi nào
- Expected: ANALYTICAL_QUERY
- Actual: CLARIFICATION / clarification
- SQL: ``

## CUST-099 - ANALYTICAL_FAILURE

- Set: holdout
- Category: long_combined
- Question: Trong hai tháng gần nhất, máy nào có tổng downtime cao nhất và nguyên nhân đứng đầu là gì?
- Expected: ANALYTICAL_QUERY
- Actual: CLARIFICATION / clarification
- SQL: ``

## CUST-129 - MULTITURN_FAILURE

- Set: holdout
- Category: multi_turn
- Question: Top 3 máy trong số đó theo downtime.
- Expected: CONVERSATION_FOLLOWUP
- Actual: SAFE_FAILURE / error
- SQL: ``
