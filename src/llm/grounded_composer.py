from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.application.grounding import AllowedNumericFact, GroundedComposerValidator
from src.application.public_response import is_valid_customer_narrative
from src.llm.ollama_client import OllamaClient


class NumericFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fact_id: str
    label: str
    value: int | float
    formatted_value: str
    unit: str | None = None
    source_result_id: str


class ComparisonFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comparison_id: str
    subject: str
    relation: str
    object: str
    evidence_fact_ids: list[str] = Field(default_factory=list)


class AnswerBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_summary: str
    response_type: str
    numeric_facts: list[NumericFact] = Field(default_factory=list)
    comparison_facts: list[ComparisonFact] = Field(default_factory=list)
    allowed_claims: list[str] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    required_sections: list[str] = Field(default_factory=list)
    requested_insight_count: int | None = None


class GroundedInsight(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding: str
    evidence_fact_ids: list[str]
    management_meaning: str


class ComposerOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    insights: list[GroundedInsight] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ComposerValidationResult(BaseModel):
    passed: bool
    errors: list[str] = Field(default_factory=list)
    failure_classification: list[str] = Field(default_factory=list)


class ComposerTrace(BaseModel):
    architecture_mode: str
    composer_model: str | None = None
    composer_started: bool = False
    composer_completed: bool = False
    composer_retry_count: int = 0
    composer_output_valid: bool = False
    grounding_valid: bool = False
    deterministic_recovery_used: bool = False
    recovery_reason: str | None = None
    raw_response: str | None = None
    repaired_response: str | None = None
    validation: ComposerValidationResult | None = None
    latency_ms: float | None = None


@dataclass(frozen=True)
class GroundedComposerResult:
    output: ComposerOutput
    trace: ComposerTrace


class GroundedComposer:
    def __init__(self, client: OllamaClient | None, model_name: str | None, architecture_mode: str) -> None:
        self.client = client
        self.model_name = model_name
        self.architecture_mode = architecture_mode

    def compose(self, brief: AnswerBrief) -> GroundedComposerResult:
        trace = ComposerTrace(architecture_mode=self.architecture_mode, composer_model=self.model_name, composer_started=True)
        start = time.perf_counter()
        if self.client is None:
            output = deterministic_recovery_output(brief)
            trace.deterministic_recovery_used = True
            trace.recovery_reason = "MODEL_UNAVAILABLE"
            trace.validation = validate_composer_output(output, brief)
            trace.composer_output_valid = trace.validation.passed
            trace.grounding_valid = trace.validation.passed
            trace.latency_ms = round((time.perf_counter() - start) * 1000, 2)
            return GroundedComposerResult(output, trace)

        raw = None
        for attempt in range(2):
            if attempt:
                trace.composer_retry_count += 1
            try:
                response = self.client.chat(
                    self._messages(brief, raw if attempt else None),
                    format_schema=ComposerOutput.model_json_schema(),
                )
                raw = response.text
                if attempt:
                    trace.repaired_response = raw
                else:
                    trace.raw_response = raw
                output = ComposerOutput.model_validate_json(raw)
                validation = validate_composer_output(output, brief)
                trace.validation = validation
                if validation.passed:
                    trace.composer_completed = True
                    trace.composer_output_valid = True
                    trace.grounding_valid = True
                    trace.latency_ms = round((time.perf_counter() - start) * 1000, 2)
                    return GroundedComposerResult(output, trace)
            except (ValidationError, ValueError, RuntimeError) as exc:
                trace.validation = ComposerValidationResult(passed=False, errors=[str(exc)], failure_classification=["COMPOSER_QUALITY_FAILED"])
        output = deterministic_recovery_output(brief)
        trace.deterministic_recovery_used = True
        trace.recovery_reason = ",".join(trace.validation.failure_classification if trace.validation else ["COMPOSER_GROUNDING_FAILED"])
        trace.validation = validate_composer_output(output, brief)
        trace.composer_output_valid = trace.validation.passed
        trace.grounding_valid = trace.validation.passed
        trace.latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return GroundedComposerResult(output, trace)

    def _messages(self, brief: AnswerBrief, previous_invalid: str | None = None) -> list[dict[str, str]]:
        payload = {
            "answer_brief": brief.model_dump(mode="json"),
            "rules": [
                "Use only numeric_facts and allowed_claims.",
                "Each insight must include finding, evidence_fact_ids, and management_meaning.",
                "Do not invent numbers, dates, percentages, ranking, filters, or causal claims.",
                "Do not mention SQL, JSON, planner, model, fallback, or internal keys.",
            ],
        }
        if previous_invalid:
            payload["previous_invalid_response"] = previous_invalid[:4000]
            payload["retry_instruction"] = "Fix structure and grounding only. Do not add new claims."
        return [
            {"role": "system", "content": "You are a grounded Vietnamese analytics composer. Return only valid JSON."},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
        ]


def validate_composer_output(output: ComposerOutput, brief: AnswerBrief) -> ComposerValidationResult:
    errors: list[str] = []
    classes: list[str] = []
    allowed_fact_ids = {fact.fact_id for fact in brief.numeric_facts}
    allowed_numbers = [
        AllowedNumericFact(fact.fact_id, float(fact.value), fact.formatted_value, tuple(filter(None, [fact.unit])))
        for fact in brief.numeric_facts
    ]
    text = " ".join(
        [output.summary]
        + [insight.finding for insight in output.insights]
        + [insight.management_meaning for insight in output.insights]
        + output.limitations
    )
    grounding = GroundedComposerValidator(allowed_numbers).validate(text)
    if not grounding.passed:
        errors.extend(grounding.errors)
        classes.append("COMPOSER_GROUNDING_FAILED")
    if not is_valid_customer_narrative(output.summary):
        errors.append("invalid_summary_narrative")
        classes.append("COMPOSER_QUALITY_FAILED")
    for idx, insight in enumerate(output.insights):
        if not insight.evidence_fact_ids:
            errors.append(f"insight[{idx}] missing evidence")
            classes.append("COMPOSER_GROUNDING_FAILED")
        if any(fact_id not in allowed_fact_ids for fact_id in insight.evidence_fact_ids):
            errors.append(f"insight[{idx}] references unknown evidence")
            classes.append("COMPOSER_GROUNDING_FAILED")
        if not is_valid_customer_narrative(insight.finding) or not is_valid_customer_narrative(insight.management_meaning):
            errors.append(f"insight[{idx}] invalid narrative")
            classes.append("COMPOSER_QUALITY_FAILED")
    for section in brief.required_sections:
        if section and section.lower() not in text.lower():
            errors.append(f"missing_required_section:{section}")
            classes.append("COMPOSER_QUALITY_FAILED")
    if any(term in text.lower() for term in ["answerbrief", "query_plan", "planner", "machine_total_downtime", "executive summary"]):
        errors.append("internal_or_english_leakage")
        classes.append("COMPOSER_QUALITY_FAILED")
    return ComposerValidationResult(passed=not errors, errors=errors, failure_classification=sorted(set(classes)))


def deterministic_recovery_output(brief: AnswerBrief) -> ComposerOutput:
    first_fact = brief.numeric_facts[0] if brief.numeric_facts else None
    summary = brief.allowed_claims[0] if brief.allowed_claims else "Kết quả đã được tổng hợp từ các số liệu đã kiểm chứng trong file đang chọn."
    if first_fact and first_fact.formatted_value not in summary:
        summary = f"{summary} Số liệu tham chiếu chính là {first_fact.formatted_value}."
    insights = []
    if first_fact:
        insights.append(
            GroundedInsight(
                finding=summary,
                evidence_fact_ids=[first_fact.fact_id],
                management_meaning="Nên dùng chỉ số này làm điểm neo khi so sánh các nhóm hoặc theo dõi thay đổi tiếp theo.",
            )
        )
    return ComposerOutput(summary=summary, insights=insights, limitations=brief.limitations[:2])
