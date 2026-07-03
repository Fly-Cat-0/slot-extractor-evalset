#!/usr/bin/env python3
"""Evaluate multi-turn robustness on cases tagged with `多轮`.

Rule:
- only evaluate samples whose tags contain `多轮`
- each case must pass in all repeated runs to count as passed
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from evaluate_slot_extractor import evaluate_case, load_jsonl, load_predictions, pct, ratio, write_jsonl


def filter_multiturn_cases(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [case for case in cases if "多轮" in case.get("tags", [])]


def evaluate_runs(
    cases: list[dict[str, Any]], prediction_runs: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    run_results: list[dict[str, Any]] = []

    for case in cases:
        case_id = str(case["id"])
        per_run: list[dict[str, Any]] = []
        all_passed = True

        for run_index, predictions in enumerate(prediction_runs, start=1):
            payload = predictions.get(case_id)
            if payload is None:
                result = {
                    "id": case_id,
                    "task_type": case.get("task_type"),
                    "layer": case.get("layer"),
                    "json_valid": False,
                    "parse_error": "missing prediction",
                    "predicted_action": None,
                    "expected_action": case.get("expected", {}).get("action"),
                    "case_passed": False,
                    "assertions_passed": 0,
                    "assertions_total": len(case.get("assertions", [])),
                    "assertion_results": [],
                    "tags": case.get("tags", []),
                }
            else:
                result = evaluate_case(case, payload)

            per_run.append(
                {
                    "run_index": run_index,
                    "case_passed": result["case_passed"],
                    "json_valid": result["json_valid"],
                    "predicted_action": result["predicted_action"],
                    "expected_action": result["expected_action"],
                    "parse_error": result["parse_error"],
                    "assertions_passed": result["assertions_passed"],
                    "assertions_total": result["assertions_total"],
                    "failed_assertions": [
                        item["assertion"] for item in result["assertion_results"] if not item["passed"]
                    ],
                }
            )
            all_passed = all_passed and result["case_passed"]

        run_results.append(
            {
                "id": case_id,
                "task_type": case.get("task_type"),
                "layer": case.get("layer"),
                "tags": case.get("tags", []),
                "all_3_passed": all_passed,
                "runs": per_run,
            }
        )

    return run_results


def summarize(run_results: list[dict[str, Any]], pred_paths: list[Path]) -> dict[str, Any]:
    total_cases = len(run_results)
    all_3_passed = sum(1 for item in run_results if item["all_3_passed"])

    by_task_type: dict[str, dict[str, Any]] = {}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    failed_assertion_patterns: Counter[str] = Counter()

    for item in run_results:
        grouped[str(item["task_type"])].append(item)
        for run in item["runs"]:
            for assertion in run["failed_assertions"]:
                failed_assertion_patterns[assertion] += 1

    for task_type, items in sorted(grouped.items()):
        by_task_type[task_type] = {
            "cases": len(items),
            "all_3_passed": sum(1 for item in items if item["all_3_passed"]),
            "robust_pass_rate": ratio(sum(1 for item in items if item["all_3_passed"]), len(items)),
        }

    return {
        "metric_name": "multi_turn_robustness_3x",
        "n_runs": len(pred_paths),
        "prediction_sources": [str(path) for path in pred_paths],
        "n_multi_turn_cases": total_cases,
        "all_3_passed_cases": all_3_passed,
        "multi_turn_robustness_3x": ratio(all_3_passed, total_cases),
        "by_task_type": by_task_type,
        "failed_assertions": failed_assertion_patterns.most_common(30),
    }


def write_report(path: Path, summary: dict[str, Any], run_results: list[dict[str, Any]]) -> None:
    lines: list[str] = []
    lines.append("# Multi-Turn Robustness Report")
    lines.append("")
    lines.append(f"- metric: `{summary['metric_name']}`")
    lines.append(f"- runs: `{summary['n_runs']}`")
    lines.append(f"- n_multi_turn_cases: `{summary['n_multi_turn_cases']}`")
    lines.append(f"- all_3_passed_cases: `{summary['all_3_passed_cases']}`")
    lines.append(f"- robustness_3x: `{pct(summary['multi_turn_robustness_3x'])}`")
    lines.append("")
    lines.append("## Prediction Sources")
    lines.append("")
    for source in summary["prediction_sources"]:
        lines.append(f"- `{source}`")

    lines.append("")
    lines.append("## By Task Type")
    lines.append("")
    lines.append("| task_type | cases | 3/3 全通过数 | 通过率 |")
    lines.append("|---|---:|---:|---:|")
    for task_type, item in summary["by_task_type"].items():
        lines.append(
            f"| {task_type} | {item['cases']} | {item['all_3_passed']} | {pct(item['robust_pass_rate'])} |"
        )

    lines.append("")
    lines.append("## Failed Assertions")
    lines.append("")
    if summary["failed_assertions"]:
        lines.append("| count | assertion |")
        lines.append("|---:|---|")
        for assertion, count in summary["failed_assertions"]:
            lines.append(f"| {count} | `{assertion}` |")
    else:
        lines.append("No failed assertions.")

    failing = [item for item in run_results if not item["all_3_passed"]]
    lines.append("")
    lines.append("## Failing Cases")
    lines.append("")
    if failing:
        lines.append("| id | task_type | pass pattern |")
        lines.append("|---|---|---|")
        for item in failing[:50]:
            pattern = ",".join("pass" if run["case_passed"] else "fail" for run in item["runs"])
            lines.append(f"| {item['id']} | {item['task_type']} | `{pattern}` |")
    else:
        lines.append("No failing cases.")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate multi-turn robustness across repeated runs.")
    parser.add_argument("--eval", required=True, type=Path, help="Frozen eval JSONL path.")
    parser.add_argument(
        "--pred",
        required=True,
        nargs=3,
        type=Path,
        help="Three prediction JSONL paths from repeated runs with fixed decoding params.",
    )
    parser.add_argument("--out-dir", type=Path, help="Directory for report files.")
    args = parser.parse_args()

    cases = filter_multiturn_cases(load_jsonl(args.eval))
    if not cases:
        raise ValueError("no cases tagged with 多轮 were found")

    prediction_runs = [load_predictions(path) for path in args.pred]
    for run_index, predictions in enumerate(prediction_runs, start=1):
        missing = [case["id"] for case in cases if str(case["id"]) not in predictions]
        if missing:
            raise ValueError(f"run {run_index} missing predictions for {len(missing)} cases, first: {missing[:5]}")

    run_results = evaluate_runs(cases, prediction_runs)
    summary = summarize(run_results, args.pred)

    out_dir = args.out_dir or (Path("eval_runs") / "multi_turn_robustness_3x")
    out_dir.mkdir(parents=True, exist_ok=True)

    write_jsonl(out_dir / "per_case_results.jsonl", run_results)
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_report(out_dir / "report.md", summary, run_results)

    print(f"wrote: {out_dir}")
    print(f"n_multi_turn_cases: {summary['n_multi_turn_cases']}")
    print(f"all_3_passed_cases: {summary['all_3_passed_cases']}")
    print(f"multi_turn_robustness_3x: {pct(summary['multi_turn_robustness_3x'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
