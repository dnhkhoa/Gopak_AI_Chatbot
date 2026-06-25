from __future__ import annotations

from llm_architecture_benchmark import parse_args, main


if __name__ == "__main__":
    args = parse_args()
    raise SystemExit(main("stability", live_model=args.live_model, max_cases=args.max_cases, repetitions=args.repetitions))
