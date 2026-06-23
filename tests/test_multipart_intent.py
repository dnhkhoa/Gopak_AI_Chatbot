"""Unit tests for multi-part intent precedence helpers.

These lock in the fix that trailing commentary/output keywords ("nhận xét", "vẽ biểu đồ")
must not hijack a self-contained analytical request. Pure functions — no LLM, fast.
"""
from __future__ import annotations

from src.application.chat_service import (
    _ascii_text,
    _has_new_analytics_request,
    _references_prior_result,
    _requests_commentary,
)


def _n(text: str) -> str:
    return _ascii_text(text)


def test_commentary_detection():
    assert _requests_commentary(_n("Nhận xét bảng vừa rồi."))
    assert _requests_commentary(_n("Cho tôi top 5 nhóm và nhận xét."))
    assert _requests_commentary(_n("Giải thích kết quả này."))
    assert not _requests_commentary(_n("Top 5 máy theo tổng downtime."))


def test_new_analytics_request_detected_in_multipart():
    # Self-contained analytical requests, even with trailing commentary/output modifiers.
    assert _has_new_analytics_request(_n("Cho tôi top 5 nhóm có số lần ghi nhận cao nhất, thêm tỷ lệ phần trăm và nhận xét."))
    assert _has_new_analytics_request(_n("Nhận xét top 5 máy theo tổng downtime trong tháng gần nhất."))
    assert _has_new_analytics_request(_n("Vẽ biểu đồ top 5 máy có tổng downtime cao nhất."))
    assert _has_new_analytics_request(_n("Top 5 nguyên nhân theo số lần ghi nhận."))


def test_followup_only_commentary_is_not_a_new_request():
    assert not _has_new_analytics_request(_n("Nhận xét bảng vừa rồi."))
    assert not _has_new_analytics_request(_n("Giải thích bảng vừa rồi."))
    assert not _has_new_analytics_request(_n("Phân tích giúp tôi đi."))


def test_prior_result_reference():
    assert _references_prior_result(_n("Nhận xét bảng vừa rồi."))
    assert _references_prior_result(_n("Biểu đồ này nói lên điều gì?"))
    assert not _references_prior_result(_n("Cho tôi top 5 nhóm theo số lần ghi nhận."))


def test_precedence_guard_logic():
    # The semantic-followup guard returns None (defers to planner) exactly when there is a new
    # analytics request and no explicit reference to a prior result.
    multipart = _n("Cho tôi top 5 nhóm có số lần ghi nhận cao nhất, thêm tỷ lệ phần trăm và nhận xét.")
    assert _requests_commentary(multipart) and _has_new_analytics_request(multipart) and not _references_prior_result(multipart)

    followup = _n("Nhận xét bảng vừa rồi.")
    assert _requests_commentary(followup) and not _has_new_analytics_request(followup)
