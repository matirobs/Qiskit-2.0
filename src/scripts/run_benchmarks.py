"""Run the reproducible Task 6 benchmark suite on real/derived-real input."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from repackq.benchmark import (
    execute_benchmark,
    load_benchmark_config,
    write_results_markdown,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run/resume the fixed Task 6 retrospective benchmark. Input may be "
            "canonical trajectories or a matching candidate-pool export."
        )
    )
    parser.add_argument("--input", required=True, help="derived-real trajectory JSON or candidate-pool export")
    parser.add_argument(
        "--config", default="configs/task6_benchmark.json",
        help="fixed benchmark seed/config JSON",
    )
    parser.add_argument(
        "--output-dir", default="data/processed/benchmark",
        help="directory for incremental checkpoint and aggregate exports",
    )
    parser.add_argument(
        "--web-output-dir", default="web/data/benchmark",
        help="directory for the small precomputed UI replay summary and trials",
    )
    parser.add_argument("--checkpoint", help="override the JSONL incremental checkpoint path")
    parser.add_argument("--fresh", action="store_true", help="start a new checkpoint and discard its previous trials")
    parser.add_argument(
        "--results-markdown", default="docs/RESULTS.md",
        help="generated scientific narrative output path (default: docs/RESULTS.md)",
    )
    parser.add_argument(
        "--predictor-evaluation", help="matching predictor_evaluation.json; defaults to a sibling file",
    )
    parser.add_argument(
        "--backend-factory", help="optional module.path:function returning an injected Qiskit-compatible backend",
    )
    parser.add_argument(
        "--backend-seed", type=int,
        help="run one selected backend sample for this predeclared seed; requires --backend-factory",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        config = load_benchmark_config(args.config)
        summary, _ = execute_benchmark(
            args.input,
            config,
            output_dir=args.output_dir,
            web_output_dir=args.web_output_dir,
            checkpoint_path=args.checkpoint,
            resume=not args.fresh,
            backend_factory=args.backend_factory,
            backend_trial_seed=args.backend_seed,
            predictor_evaluation_path=args.predictor_evaluation,
        )
        if args.results_markdown:
            write_results_markdown(args.results_markdown, summary)
    except (OSError, KeyError, TypeError, ValueError, RuntimeError, ImportError) as error:
        parser.exit(2, f"run_benchmarks: error: {error}\n")
    print(json.dumps({
        "trial_count": summary["trial_count"],
        "candidate_sizes": summary["candidate_sizes"],
        "data_classification": summary["data_classification"],
        "output_dir": args.output_dir,
        "qaoa_optimum_sample_rate": summary["qaoa_quality"]["optimum_sample_rate"],
        "objective_ablation_mean_opd_improvement": summary["objective_ablation"]["mean_opd_improvement"],
    }, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
