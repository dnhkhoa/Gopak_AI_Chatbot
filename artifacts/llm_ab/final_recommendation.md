# LLM Architecture Benchmark Recommendation

Baseline commit: `ade9f9906970dd0d7207f69bd823996b733ab056`
Current branch: `feature/demo-conversation-seeding`
Manifest hash: `5c55c12372493af4935907e88217f6b7a0693490c8cb8f0b4ee54cccc4e5b782`

## Local Models
- qwen3-vl:8b (6.1 GB)
- qwen3.5:9b (6.6 GB)

## Candidate Fast Model
No suitable local fast structured text model was selected. `qwen3-vl:8b` is installed but is a vision-language model, so it is not chosen only because it is smaller.
Suggested candidates to install later, after approval: `qwen2.5:3b-instruct`, `llama3.2:3b`, or another local text model with strong JSON compliance and Vietnamese understanding.

## Blind Review
PENDING_BLIND_HUMAN_REVIEW. LLM judge, if added later, must remain a secondary metric only.

## Release Gate
{
  "same_test_manifest": true,
  "same_state_snapshots": true,
  "same_deterministic_analytics_results": true,
  "same_hardware": true,
  "same_validators": true,
  "all_failed_cases_retained": true,
  "holdout_not_tuned_on": true
}

## Dashboard
[
  {
    "Metric": "Intent accuracy",
    "Legacy single model": 0.3529,
    "Split roles same model": 0.4118,
    "Dual model": null,
    "Best": "split_roles_same_model",
    "Delta": {
      "B_minus_A": 0.0589,
      "C_minus_A": null
    },
    "Confidence": "low"
  },
  {
    "Metric": "Turn relationship accuracy",
    "Legacy single model": 0.9412,
    "Split roles same model": 0.4706,
    "Dual model": null,
    "Best": "legacy_single_model",
    "Delta": {
      "B_minus_A": -0.4706,
      "C_minus_A": null
    },
    "Confidence": "low"
  },
  {
    "Metric": "RequestContract validity",
    "Legacy single model": 0.9412,
    "Split roles same model": 0.5294,
    "Dual model": null,
    "Best": "legacy_single_model",
    "Delta": {
      "B_minus_A": -0.4118,
      "C_minus_A": null
    },
    "Confidence": "low"
  },
  {
    "Metric": "Typo recovery",
    "Legacy single model": 0.25,
    "Split roles same model": 0.0,
    "Dual model": null,
    "Best": "legacy_single_model",
    "Delta": {
      "B_minus_A": -0.25,
      "C_minus_A": null
    },
    "Confidence": "low"
  },
  {
    "Metric": "Unnecessary clarification rate",
    "Legacy single model": 0.0,
    "Split roles same model": 0.0,
    "Dual model": null,
    "Best": "legacy_single_model",
    "Delta": {
      "B_minus_A": 0.0,
      "C_minus_A": null
    },
    "Confidence": "low"
  },
  {
    "Metric": "Context replay pass rate",
    "Legacy single model": 0.75,
    "Split roles same model": 0.75,
    "Dual model": null,
    "Best": "legacy_single_model",
    "Delta": {
      "B_minus_A": 0.0,
      "C_minus_A": null
    },
    "Confidence": "low"
  },
  {
    "Metric": "Numeric grounding pass rate",
    "Legacy single model": 0.8,
    "Split roles same model": 0.0,
    "Dual model": null,
    "Best": "legacy_single_model",
    "Delta": {
      "B_minus_A": -0.8,
      "C_minus_A": null
    },
    "Confidence": "low"
  },
  {
    "Metric": "Invalid narrative rate",
    "Legacy single model": 0.0,
    "Split roles same model": 0.0,
    "Dual model": null,
    "Best": "legacy_single_model",
    "Delta": {
      "B_minus_A": 0.0,
      "C_minus_A": null
    },
    "Confidence": "low"
  },
  {
    "Metric": "Report completeness",
    "Legacy single model": 0.8,
    "Split roles same model": 0.8,
    "Dual model": null,
    "Best": "legacy_single_model",
    "Delta": {
      "B_minus_A": 0.0,
      "C_minus_A": null
    },
    "Confidence": "low"
  },
  {
    "Metric": "Warm p50 latency",
    "Legacy single model": 0.14,
    "Split roles same model": 0.22,
    "Dual model": null,
    "Best": "legacy_single_model",
    "Delta": {
      "B_minus_A": 0.08,
      "C_minus_A": null
    },
    "Confidence": "low"
  },
  {
    "Metric": "Warm p95 latency",
    "Legacy single model": 0.18,
    "Split roles same model": 0.3,
    "Dual model": null,
    "Best": "legacy_single_model",
    "Delta": {
      "B_minus_A": 0.12,
      "C_minus_A": null
    },
    "Confidence": "low"
  },
  {
    "Metric": "Peak RAM",
    "Legacy single model": null,
    "Split roles same model": null,
    "Dual model": null,
    "Best": null,
    "Delta": null,
    "Confidence": "low"
  },
  {
    "Metric": "Peak VRAM",
    "Legacy single model": null,
    "Split roles same model": null,
    "Dual model": null,
    "Best": null,
    "Delta": null,
    "Confidence": "low"
  },
  {
    "Metric": "Timeout rate",
    "Legacy single model": 0,
    "Split roles same model": 0,
    "Dual model": null,
    "Best": "legacy_single_model",
    "Delta": {
      "B_minus_A": 0,
      "C_minus_A": null
    },
    "Confidence": "low"
  }
]

## Limitations
- Dual model results are unavailable until a suitable local fast structured text model is installed.
- Human blind review is pending.
- Raw model logs are not committed; artifacts retain scores and failure categories only.

## Final Conclusion
INSUFFICIENT_EVIDENCE