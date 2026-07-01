from src.application.schemas import (
    ArtifactPayload,
    ChartPayload,
    ChatMessageRequest,
    ChatResponse,
    ConversationDetail,
    ConversationPayload,
    DataStatus,
    DownloadPayload,
    HealthStatus,
    SourcePayload,
    TablePayload,
)


def __getattr__(name: str):
    if name == "ChatApplicationService":
        from src.application.chat_service import ChatApplicationService

        return ChatApplicationService
    raise AttributeError(name)

__all__ = [
    "ArtifactPayload",
    "ChartPayload",
    "ChatApplicationService",
    "ChatMessageRequest",
    "ChatResponse",
    "ConversationDetail",
    "ConversationPayload",
    "DataStatus",
    "DownloadPayload",
    "HealthStatus",
    "SourcePayload",
    "TablePayload",
]
