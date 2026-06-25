"""Error taxonomy and customer-facing (Vietnamese) error policy (P0-C).

A single place that (a) enumerates every failure class, (b) maps internal
exceptions to a stable ``ErrorCode``, and (c) renders a customer-safe Vietnamese
message with a next action. Internal traces never reach the customer payload.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel


class ErrorCode(str, Enum):
    UNSUPPORTED_BY_ACTIVE_FILE = "UNSUPPORTED_BY_ACTIVE_FILE"
    FILE_NOT_READY = "FILE_NOT_READY"
    FILE_MISSING = "FILE_MISSING"
    CATALOG_UNAVAILABLE = "CATALOG_UNAVAILABLE"
    QUERY_VALIDATION_FAILED = "QUERY_VALIDATION_FAILED"
    QUERY_TIMEOUT = "QUERY_TIMEOUT"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    MODEL_TIMEOUT = "MODEL_TIMEOUT"
    MODEL_INVALID_OUTPUT = "MODEL_INVALID_OUTPUT"
    REPORT_GENERATION_FAILED = "REPORT_GENERATION_FAILED"
    EXPORT_FAILED = "EXPORT_FAILED"
    PERSISTENCE_FAILED = "PERSISTENCE_FAILED"
    UNKNOWN_INTERNAL_ERROR = "UNKNOWN_INTERNAL_ERROR"


# Which error codes represent infrastructure faults (drive the health banner)
# vs. business-level rejections (must NOT change service health).
INFRASTRUCTURE_CODES: set[ErrorCode] = {
    ErrorCode.CATALOG_UNAVAILABLE,
    ErrorCode.PERSISTENCE_FAILED,
    ErrorCode.MODEL_UNAVAILABLE,
    ErrorCode.MODEL_TIMEOUT,
}

BUSINESS_CODES: set[ErrorCode] = {
    ErrorCode.UNSUPPORTED_BY_ACTIVE_FILE,
    ErrorCode.FILE_NOT_READY,
    ErrorCode.QUERY_VALIDATION_FAILED,
}


class GopakError(Exception):
    """Base class for classified internal errors."""

    code: ErrorCode = ErrorCode.UNKNOWN_INTERNAL_ERROR

    def __init__(self, message: str = "", *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message or self.code.value)
        self.details = details or {}


class UnsupportedByActiveFileError(GopakError):
    code = ErrorCode.UNSUPPORTED_BY_ACTIVE_FILE


class FileNotReadyError(GopakError):
    code = ErrorCode.FILE_NOT_READY


class CatalogUnavailableError(GopakError):
    code = ErrorCode.CATALOG_UNAVAILABLE


class QueryValidationError(GopakError):
    code = ErrorCode.QUERY_VALIDATION_FAILED


class QueryTimeoutError(GopakError):
    code = ErrorCode.QUERY_TIMEOUT


class ModelUnavailableError(GopakError):
    code = ErrorCode.MODEL_UNAVAILABLE


class ReportGenerationError(GopakError):
    code = ErrorCode.REPORT_GENERATION_FAILED


# Customer-facing Vietnamese messages. Each is specific and ends with a next step.
_CUSTOMER_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.UNSUPPORTED_BY_ACTIVE_FILE: (
        "File hiện tại không chứa các cột cần thiết cho yêu cầu này. "
        "Hãy chọn file dữ liệu phù hợp rồi tạo một cuộc trò chuyện mới để thực hiện."
    ),
    ErrorCode.FILE_NOT_READY: (
        "File đang được chuẩn bị. Hãy đợi trạng thái chuyển sang Sẵn sàng rồi thử lại."
    ),
    ErrorCode.FILE_MISSING: (
        "Không tìm thấy file nguồn của cuộc trò chuyện này. "
        "Hãy chọn một file khác và bắt đầu cuộc trò chuyện mới."
    ),
    ErrorCode.CATALOG_UNAVAILABLE: (
        "Hệ thống dữ liệu tạm thời không khả dụng. Vui lòng thử lại sau giây lát."
    ),
    ErrorCode.QUERY_VALIDATION_FAILED: (
        "Mình chưa dựng được truy vấn an toàn cho yêu cầu này. "
        "Hãy diễn đạt cụ thể hơn về cột, chỉ số hoặc khoảng thời gian."
    ),
    ErrorCode.QUERY_TIMEOUT: (
        "Yêu cầu cần xử lý quá nhiều dữ liệu và chưa hoàn tất trong thời gian cho phép. "
        "Hãy thu hẹp khoảng thời gian hoặc số nhóm cần phân tích."
    ),
    ErrorCode.MODEL_UNAVAILABLE: (
        "Tính năng phân tích ngôn ngữ đang tạm thời không khả dụng. "
        "Các câu hỏi thống kê trực tiếp vẫn có thể tiếp tục sử dụng."
    ),
    ErrorCode.MODEL_TIMEOUT: (
        "Tính năng phân tích ngôn ngữ phản hồi quá lâu. "
        "Hãy thử lại hoặc dùng câu hỏi thống kê trực tiếp."
    ),
    ErrorCode.MODEL_INVALID_OUTPUT: (
        "Mình chưa hiểu rõ yêu cầu phân tích này. Hãy diễn đạt theo cách cụ thể hơn."
    ),
    ErrorCode.REPORT_GENERATION_FAILED: (
        "Không tạo được báo cáo cho yêu cầu này. Hãy thử lại hoặc thu hẹp phạm vi báo cáo."
    ),
    ErrorCode.EXPORT_FAILED: (
        "Không xuất được tệp kết quả. Hãy thử lại sau giây lát."
    ),
    ErrorCode.PERSISTENCE_FAILED: (
        "Hệ thống lưu lịch sử tạm thời gặp sự cố. Câu trả lời vẫn hiển thị nhưng có thể không được lưu."
    ),
    ErrorCode.UNKNOWN_INTERNAL_ERROR: (
        "Không thể hoàn tất yêu cầu này. Vui lòng thử lại hoặc diễn đạt yêu cầu theo cách cụ thể hơn."
    ),
}

_CUSTOMER_TITLES: dict[ErrorCode, str] = {
    ErrorCode.UNSUPPORTED_BY_ACTIVE_FILE: "File hiện tại không hỗ trợ yêu cầu này",
    ErrorCode.FILE_NOT_READY: "File chưa sẵn sàng",
    ErrorCode.FILE_MISSING: "Không tìm thấy file nguồn",
    ErrorCode.CATALOG_UNAVAILABLE: "Dữ liệu tạm thời không khả dụng",
    ErrorCode.QUERY_VALIDATION_FAILED: "Cần làm rõ yêu cầu",
    ErrorCode.QUERY_TIMEOUT: "Yêu cầu quá lớn",
    ErrorCode.MODEL_UNAVAILABLE: "Phân tích ngôn ngữ tạm gián đoạn",
    ErrorCode.MODEL_TIMEOUT: "Phân tích ngôn ngữ phản hồi chậm",
    ErrorCode.MODEL_INVALID_OUTPUT: "Cần làm rõ yêu cầu",
    ErrorCode.REPORT_GENERATION_FAILED: "Không tạo được báo cáo",
    ErrorCode.EXPORT_FAILED: "Không xuất được tệp",
    ErrorCode.PERSISTENCE_FAILED: "Sự cố lưu lịch sử",
    ErrorCode.UNKNOWN_INTERNAL_ERROR: "Không thể hoàn tất yêu cầu",
}


class CustomerError(BaseModel):
    code: str
    title: str
    message: str
    next_action: str | None = None
    recommended_file: str | None = None
    missing_dimensions: list[str] = []
    missing_metrics: list[str] = []


class CustomerErrorMessagePolicy:
    """Renders a customer-safe Vietnamese error for an ErrorCode."""

    @staticmethod
    def message(code: ErrorCode) -> str:
        return _CUSTOMER_MESSAGES.get(code, _CUSTOMER_MESSAGES[ErrorCode.UNKNOWN_INTERNAL_ERROR])

    @staticmethod
    def title(code: ErrorCode) -> str:
        return _CUSTOMER_TITLES.get(code, _CUSTOMER_TITLES[ErrorCode.UNKNOWN_INTERNAL_ERROR])

    @classmethod
    def build(cls, code: ErrorCode, *, message: str | None = None, **extra: Any) -> CustomerError:
        return CustomerError(
            code=code.value,
            title=cls.title(code),
            message=message or cls.message(code),
            **{k: v for k, v in extra.items() if v is not None},
        )


def classify_exception(exc: BaseException) -> ErrorCode:
    """Map an arbitrary internal exception to a stable ErrorCode."""
    if isinstance(exc, GopakError):
        return exc.code
    name = type(exc).__name__
    text = str(exc).lower()
    if name in {"ValidationError", "MetricSpecError"} or "validation error" in text or "column is required" in text:
        return ErrorCode.QUERY_VALIDATION_FAILED
    if "timeout" in text or name in {"TimeoutError", "ReadTimeout"}:
        return ErrorCode.QUERY_TIMEOUT
    if "ollama" in text or "model" in text and "unavailable" in text:
        return ErrorCode.MODEL_UNAVAILABLE
    if "duckdb" in text or "catalog" in text or "no such table" in text:
        return ErrorCode.CATALOG_UNAVAILABLE
    if name in {"OperationalError", "DatabaseError"} or "sqlite" in text:
        return ErrorCode.PERSISTENCE_FAILED
    return ErrorCode.UNKNOWN_INTERNAL_ERROR


def is_infrastructure(code: ErrorCode) -> bool:
    return code in INFRASTRUCTURE_CODES
