import json

from src.conversation.state import ConversationState
from src.llm.ollama_client import LLMResponse
from src.llm.semantic_contracts import SemanticIntent, TurnRelationship
from src.llm.semantic_resolver import SemanticResolver, build_resolver_input


class _RetryClient:
    def __init__(self):
        self.calls = 0

    def chat(self, messages, format_schema=None):
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                text=json.dumps(
                    {
                        "schema_version": "semantic_resolution.v1",
                        "intent": "The user wants a number",
                        "turn_relationship": "NEW_REQUEST",
                        "confidence": 0.5,
                    }
                ),
                latency_ms=1,
            )
        return LLMResponse(
            text=json.dumps(
                {
                    "schema_version": "semantic_resolution.v1",
                    "intent": "AGGREGATION",
                    "turn_relationship": "NEW_REQUEST",
                    "metrics": ["total_downtime"],
                    "confidence": 0.9,
                }
            ),
            latency_ms=1,
        )


def test_semantic_resolver_retries_once_and_accepts_valid_enum_response():
    client = _RetryClient()
    state = ConversationState(active_file_id="downtime")
    resolver_input = build_resolver_input("Tong downtime", state, {"fields": ["total_downtime"]})
    resolver = SemanticResolver(client, "qwen3.5:9b", "split_roles_same_model")

    result = resolver.resolve(resolver_input)

    assert client.calls == 2
    assert result.trace.resolver_retry_count == 1
    assert result.resolution is not None
    assert result.resolution.intent is SemanticIntent.AGGREGATION
    assert result.resolution.turn_relationship is TurnRelationship.NEW_REQUEST
