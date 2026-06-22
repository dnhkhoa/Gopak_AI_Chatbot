from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.catalog.profiler import load_catalog
from src.config import get_settings


def table_names(catalog: dict) -> dict[str, str]:
    names = {}
    for table in catalog["tables"]:
        if table["table_name"].startswith("machine_downtime"):
            names["machine"] = table["table_name"]
        elif table["table_name"].startswith("loss_assignment"):
            names["loss"] = table["table_name"]
        elif table["table_name"].startswith("entrytransaction"):
            names["entry"] = table["table_name"]
    return names


def make_case(idx: int, category: str, question: str, oracle_sql: str = "", comparison_type: str = "manual", expected_intent: str = "query", expected_behavior: str = "", tags: list[str] | None = None, turn: int = 1, conversation_id: str | None = None) -> dict:
    return {
        "id": f"EVAL-{idx:03d}",
        "category": category,
        "question": question,
        "conversation_id": conversation_id,
        "turn": turn,
        "expected_intent": expected_intent,
        "expected_tables": [],
        "oracle_sql": oracle_sql,
        "comparison_type": comparison_type,
        "tolerance": 0.01,
        "expected_behavior": expected_behavior,
        "tags": tags or [],
    }


def main() -> None:
    settings = get_settings()
    catalog = load_catalog(settings.cache_dir)
    tables = table_names(catalog)
    m = tables["machine"]
    l = tables["loss"]
    e = tables["entry"]
    cases = []
    i = 1

    def add(*args, **kwargs):
        nonlocal i
        cases.append(make_case(i, *args, **kwargs))
        i += 1

    # A. Basic aggregation
    add("aggregation", "Tổng số bản ghi downtime là bao nhiêu?", f"SELECT count(*) AS row_count FROM {m}", "numeric")
    add("aggregation", "Tổng thời gian downtime là bao nhiêu?", f"SELECT sum(thoi_luong_seconds) AS total_duration_seconds FROM {m}", "numeric")
    add("aggregation", "Thời gian downtime trung bình là bao nhiêu?", f"SELECT avg(thoi_luong_seconds) AS avg_duration_seconds FROM {m}", "numeric")
    add("aggregation", "Downtime lớn nhất là bao nhiêu?", f"SELECT max(thoi_luong_seconds) AS max_duration_seconds FROM {m}", "numeric")
    add("aggregation", "Downtime nhỏ nhất là bao nhiêu?", f"SELECT min(thoi_luong_seconds) AS min_duration_seconds FROM {m}", "numeric")
    add("aggregation", "Có bao nhiêu máy khác nhau trong downtime?", f"SELECT count(DISTINCT may) AS machine_count FROM {m}", "numeric")
    add("aggregation", "Có bao nhiêu nguyên nhân tổn thất khác nhau?", f"SELECT count(DISTINCT ten_ton_that) AS reason_count FROM {m}", "numeric")
    add("aggregation", "Tổng downtime theo nhóm tổn thất.", f"SELECT nhom_ton_that, sum(thoi_luong_seconds) AS total_duration_seconds FROM {m} GROUP BY 1 ORDER BY 2 DESC", "table")
    add("aggregation", "Đếm số lần dừng theo máy.", f"SELECT may, count(*) AS row_count FROM {m} GROUP BY 1 ORDER BY 2 DESC", "table")

    # B. Group/top-N
    add("top_n", "Top 5 máy theo tổng downtime.", f"SELECT may, sum(thoi_luong_seconds) AS total_duration_seconds FROM {m} GROUP BY 1 ORDER BY 2 DESC LIMIT 5", "table", tags=["top5"])
    add("top_n", "Top 10 nguyên nhân theo số lần xuất hiện.", f"SELECT ten_ton_that, count(*) AS row_count FROM {m} GROUP BY 1 ORDER BY 2 DESC LIMIT 10", "table")
    add("top_n", "Máy có downtime trung bình cao nhất.", f"SELECT may, avg(thoi_luong_seconds) AS avg_duration_seconds FROM {m} GROUP BY 1 ORDER BY 2 DESC LIMIT 1", "table")
    add("top_n", "Nhóm tổn thất có tổng thời gian lớn nhất.", f"SELECT nhom_ton_that, sum(thoi_luong_seconds) AS total_duration_seconds FROM {m} GROUP BY 1 ORDER BY 2 DESC LIMIT 1", "table")
    add("top_n", "Top máy theo từng tháng.", f"SELECT date_trunc('month', thoi_gian_bat_dau) AS month, may, sum(thoi_luong_seconds) AS total_duration_seconds FROM {m} GROUP BY 1,2 ORDER BY 1,3 DESC", "table")
    add("top_n", "Các máy có tổng downtime cao hơn mức trung bình theo máy.", f"WITH x AS (SELECT may, sum(thoi_luong_seconds) v FROM {m} GROUP BY 1) SELECT may, v AS total_duration_seconds FROM x WHERE v > (SELECT avg(v) FROM x) ORDER BY v DESC", "table")
    add("top_n", "Bottom 5 máy theo tổng downtime.", f"SELECT may, sum(thoi_luong_seconds) AS total_duration_seconds FROM {m} GROUP BY 1 ORDER BY 2 ASC LIMIT 5", "table")
    add("top_n", "Xếp hạng nguyên nhân theo tỷ lệ phần trăm số lần dừng.", f"SELECT ten_ton_that, count(*) AS row_count, count(*) * 100.0 / sum(count(*)) OVER () AS percentage FROM {m} GROUP BY 1 ORDER BY 2 DESC", "table")

    # C. Time
    add("time", "Tổng downtime tháng đầu tiên trong dữ liệu.", f"SELECT sum(thoi_luong_seconds) AS total_duration_seconds FROM {m} WHERE thoi_gian_bat_dau >= DATE '2025-11-01' AND thoi_gian_bat_dau < DATE '2025-12-01'", "numeric")
    add("time", "Tổng downtime tháng gần nhất trong dữ liệu.", f"SELECT sum(thoi_luong_seconds) AS total_duration_seconds FROM {m} WHERE thoi_gian_bat_dau >= DATE '2026-02-01' AND thoi_gian_bat_dau < DATE '2026-03-01'", "numeric")
    add("time", "Downtime theo ngày.", f"SELECT date_trunc('day', thoi_gian_bat_dau) AS day, sum(thoi_luong_seconds) AS total_duration_seconds FROM {m} GROUP BY 1 ORDER BY 1", "table")
    add("time", "Downtime theo tuần.", f"SELECT date_trunc('week', thoi_gian_bat_dau) AS week, sum(thoi_luong_seconds) AS total_duration_seconds FROM {m} GROUP BY 1 ORDER BY 1", "table")
    add("time", "Downtime theo tháng.", f"SELECT date_trunc('month', thoi_gian_bat_dau) AS month, sum(thoi_luong_seconds) AS total_duration_seconds FROM {m} GROUP BY 1 ORDER BY 1", "table")
    add("time", "Ngày có downtime cao nhất.", f"SELECT date_trunc('day', thoi_gian_bat_dau) AS day, sum(thoi_luong_seconds) AS total_duration_seconds FROM {m} GROUP BY 1 ORDER BY 2 DESC LIMIT 1", "table")
    add("time", "Tổng downtime từ 2025-12-01 đến 2025-12-31.", f"SELECT sum(thoi_luong_seconds) AS total_duration_seconds FROM {m} WHERE thoi_gian_bat_dau >= DATE '2025-12-01' AND thoi_gian_bat_dau < DATE '2026-01-01'", "numeric")
    add("time", "Các lần dừng trên 30 phút.", f"SELECT count(*) AS row_count FROM {m} WHERE thoi_luong_seconds > 1800", "numeric")
    add("time", "Các lần dừng trên 2 giờ.", f"SELECT count(*) AS row_count FROM {m} WHERE thoi_luong_seconds > 7200", "numeric")

    # D. Multi-filter
    add("filter", "Tổng downtime của Máy 29 trong tháng 12/2025.", f"SELECT sum(thoi_luong_seconds) AS total_duration_seconds FROM {m} WHERE may='Máy 29' AND thoi_gian_bat_dau >= DATE '2025-12-01' AND thoi_gian_bat_dau < DATE '2026-01-01'", "numeric")
    add("filter", "Nhóm Bảo trì trên Máy 11 có bao nhiêu lần dừng?", f"SELECT count(*) AS row_count FROM {m} WHERE may='Máy 11' AND nhom_ton_that='Bảo trì'", "numeric")
    add("filter", "Đếm các lần downtime lớn hơn 1 giờ.", f"SELECT count(*) AS row_count FROM {m} WHERE thoi_luong_seconds > 3600", "numeric")
    add("filter", "Máy 29 bị MÁY LỖI PHẦN CƠ trong tháng 1/2026 bao lâu?", f"SELECT sum(thoi_luong_seconds) AS total_duration_seconds FROM {m} WHERE may='Máy 29' AND ten_ton_that='MÁY LỖI PHẦN CƠ' AND thoi_gian_bat_dau >= DATE '2026-01-01' AND thoi_gian_bat_dau < DATE '2026-02-01'", "numeric")
    add("filter", "Tổng downtime không thuộc nhóm Bảo trì.", f"SELECT sum(thoi_luong_seconds) AS total_duration_seconds FROM {m} WHERE nhom_ton_that <> 'Bảo trì'", "numeric")
    add("filter", "Tổng downtime của Máy 11 và Máy 29.", f"SELECT sum(thoi_luong_seconds) AS total_duration_seconds FROM {m} WHERE may IN ('Máy 11','Máy 29')", "numeric")

    # E. Paraphrases
    paraphrases = [
        "Cộng toàn bộ thời gian máy bị dừng.",
        "Tất cả các lần dừng máy chiếm bao nhiêu giờ?",
        "Tổng thời lượng ngưng hoạt động là bao lâu?",
        "Máy móc đã dừng tổng cộng bao lâu?",
        "Cho tôi tổng downtime.",
        "Tổng DT là bao nhiêu?",
    ]
    for q in paraphrases:
        add("paraphrase", q, f"SELECT sum(thoi_luong_seconds) AS total_duration_seconds FROM {m}", "numeric", tags=["paraphrase_total_duration"])

    # F. Typos/natural writing
    typo_questions = ["Tong dowtime la bao nhieu?", "thơi gian dừng tổng cộng?", "may nao downtime cao nhat", "DT của máy sx là bao nhiêu?"]
    for q in typo_questions:
        add("typo", q, f"SELECT sum(thoi_luong_seconds) AS total_duration_seconds FROM {m}", "numeric")

    # G. Semantic categories
    add("semantic", "Các nguyên nhân liên quan đến QC là gì?", f"SELECT DISTINCT ten_ton_that FROM {m} WHERE lower(ten_ton_that) LIKE '%qc%' OR lower(nhom_ton_that) LIKE '%qc%' ORDER BY 1", "table")
    add("semantic", "Những lỗi liên quan đến chỉnh máy.", f"SELECT DISTINCT ten_ton_that FROM {l} WHERE lower(ten_ton_that) LIKE '%chỉnh%' OR lower(ten_ton_that) LIKE '%setup%' ORDER BY 1", "table")
    add("semantic", "Các trường hợp liên quan đến bảo trì.", f"SELECT DISTINCT ten_ton_that FROM {m} WHERE nhom_ton_that='Bảo trì' ORDER BY 1", "table")
    add("semantic", "Những nguyên nhân giống chờ vật tư.", f"SELECT DISTINCT ten_ton_that FROM {l} WHERE lower(ten_ton_that) LIKE '%vật tư%' OR lower(ten_ton_that) LIKE '%cho%' OR lower(ten_ton_that) LIKE '%chờ%' ORDER BY 1", "table")
    add("semantic", "Các sự cố có ý nghĩa gần với setup.", f"SELECT DISTINCT ten_ton_that FROM {l} WHERE lower(ten_ton_that) LIKE '%setup%' ORDER BY 1", "table")

    # H. Multi-table expected clarification/refusal
    for q in [
        "So sánh downtime với loss assignment theo từng dòng.",
        "Tìm transaction liên quan đến machine downtime.",
        "Tổng hợp theo thuộc tính từ downtime và ra vào cổng.",
        "Join loss assignment với machine downtime bằng số thứ tự.",
        "Ghép transaction với máy downtime theo người vận hành.",
    ]:
        add("join", q, "", "behavior", expected_intent="clarification", expected_behavior="Không tự join khi không có row-level foreign key được chứng minh.", tags=["join_refusal"])

    # I. Multi-turn 5 chains x 3
    conversations = [
        ["Máy nào có downtime cao nhất?", "Vẽ top 5 máy.", "Chỉ lấy tháng gần nhất."],
        ["Top 5 nguyên nhân tổn thất là gì?", "Nguyên nhân đứng đầu xảy ra nhiều nhất trên máy nào?", "Xuất kết quả thành biểu đồ."],
        ["So sánh downtime giữa các tháng.", "Chỉ giữ hai tháng gần nhất.", "Tháng nào cao hơn và cao hơn bao nhiêu phần trăm?"],
        ["Tìm máy có downtime trung bình cao nhất.", "Cho tôi các bản ghi của máy đó.", "Chỉ giữ các lần trên 1 giờ."],
        ["Tổng hợp theo nhóm tổn thất.", "Chọn nhóm đứng đầu.", "Phân tích top nguyên nhân bên trong nhóm đó."],
    ]
    for cidx, chain in enumerate(conversations, start=1):
        for turn, q in enumerate(chain, start=1):
            add("multi_turn", q, "", "manual", expected_behavior="Conversation state should remain coherent.", tags=["multi_turn"], turn=turn, conversation_id=f"CONV-{cidx:02d}")

    # J. Chart/dashboard/report
    add("artifact", "Vẽ bar chart top 5 máy theo downtime.", f"SELECT may, sum(thoi_luong_seconds) AS total_duration_seconds FROM {m} GROUP BY 1 ORDER BY 2 DESC LIMIT 5", "chart", expected_intent="chart")
    add("artifact", "Vẽ line chart downtime theo ngày.", f"SELECT date_trunc('day', thoi_gian_bat_dau) AS day, sum(thoi_luong_seconds) AS total_duration_seconds FROM {m} GROUP BY 1 ORDER BY 1", "chart", expected_intent="chart")
    add("artifact", "Vẽ pie chart theo nhóm tổn thất.", f"SELECT nhom_ton_that, sum(thoi_luong_seconds) AS total_duration_seconds FROM {m} GROUP BY 1 ORDER BY 2 DESC", "chart", expected_intent="chart")
    add("artifact", "Tạo dashboard tổng quan.", "", "manual", expected_intent="dashboard")
    add("artifact", "Tạo report HTML downtime.", "", "manual", expected_intent="report")
    add("artifact", "Xuất kết quả Excel top máy.", f"SELECT may, sum(thoi_luong_seconds) AS total_duration_seconds FROM {m} GROUP BY 1 ORDER BY 2 DESC LIMIT 20", "table", expected_intent="report")

    # K/L/M behavior
    for q in ["Máy nào tốt nhất?", "Tổn thất nào nghiêm trọng nhất?", "Cho tôi báo cáo tháng này.", "So sánh hai nhóm chính."]:
        add("ambiguity", q, "", "behavior", expected_intent="clarification", expected_behavior="Ask for metric/time/group clarification.", tags=["clarification"])
    for q in ["Doanh thu năm 2024 là bao nhiêu?", "Nhân viên nào có hiệu suất tốt nhất?", "Dự báo giá cổ phiếu ngày mai.", "Máy nào sẽ hỏng vào tuần sau?"]:
        add("out_of_domain", q, "", "behavior", expected_intent="clarification", expected_behavior="Current data is insufficient; do not hallucinate numbers.", tags=["refusal"])
    add("boundary", "Dữ liệu của máy KHÔNG_TỒN_TẠI là gì?", f"SELECT * FROM {m} WHERE may='KHÔNG_TỒN_TẠI'", "empty")
    add("boundary", "Downtime trong năm 2030 là bao nhiêu?", f"SELECT sum(thoi_luong_seconds) AS total_duration_seconds FROM {m} WHERE thoi_gian_bat_dau >= DATE '2030-01-01' AND thoi_gian_bat_dau < DATE '2031-01-01'", "empty")
    add("boundary", "Các nguyên nhân liên quan đến QC là gì?", f"SELECT DISTINCT ten_ton_that FROM {m} WHERE lower(ten_ton_that) LIKE '%qc%'", "empty")
    add("boundary", "Có lần dừng nào trên 100 giờ không?", f"SELECT * FROM {m} WHERE thoi_luong_seconds > 360000", "empty")

    Path("evaluation/evaluation_cases.json").write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(cases)} cases to evaluation/evaluation_cases.json")


if __name__ == "__main__":
    main()
