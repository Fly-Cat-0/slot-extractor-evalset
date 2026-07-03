#!/usr/bin/env python3
"""Rule evaluator for the Slot-Extractor evalset.

The evaluator consumes a frozen eval JSONL file with:
  id, task_type, layer, input, expected, assertions, gold_facts, tags

and a prediction JSONL file with one record per id. Prediction records may use
one of these shapes:
  {"id": "...", "output": {...}}
  {"id": "...", "prediction": {...}}
  {"id": "...", "raw_output": "{\"action\":\"ask\",...}"}
  {"id": "...", "action": "...", ...}

For evaluator self-checks, pass --use-expected to judge expected against itself.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ACTION_ALLOWED_KEYS = {
    "ask": {
        "action",
        "missing_info",
        "question",
        "info_complete",
        "project",
        "technician_name",
        "start_time",
        "duration",
        "gender",
    },
    "tool_call": {"action", "tool_name", "arguments"},
    "final": {
        "action",
        "project",
        "technician_name",
        "start_time",
        "duration",
        "gender",
        "info_complete",
        "missing_info",
        "unrelated",
    },
    "unrelated": {"action", "unrelated", "reason"},
    "confirmation": {
        "action",
        "confirmation",
        "change_request",
        "changed_fields",
        "finalize",
        "unrelated",
    },
}

TOOL_ALLOWED_ARGS = {
    "find_technicians": {"technician_name", "project", "start_time", "duration"},
    "get_current_weather": {"location", "time"},
}

UNKNOWN_VALUES = {"未知", "", None}

FIELD_NAMES = {
    "project",
    "technician_name",
    "start_time",
    "duration",
    "gender",
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno} is not valid JSON: {exc}") from exc
            if not isinstance(item, dict):
                raise ValueError(f"{path}:{lineno} must be a JSON object")
            items.append(item)
    return items


def parse_model_output(value: Any) -> tuple[dict[str, Any] | None, str | None]:
    if isinstance(value, dict):
        return value, None
    if value is None:
        return None, "missing prediction"
    if not isinstance(value, str):
        return None, f"prediction is {type(value).__name__}, not object/string"

    text = value.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text).strip()

    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"json parse error: {exc}"
    if not isinstance(parsed, dict):
        return None, "parsed JSON is not an object"
    return parsed, None


def load_predictions(path: Path) -> dict[str, Any]:
    records = load_jsonl(path)
    predictions: dict[str, Any] = {}
    known_keys = [
        "output",
        "prediction",
        "pred",
        "raw_output",
        "model_output",
        "completion",
        "response",
    ]
    for item in records:
        case_id = item.get("id")
        if not case_id:
            raise ValueError(f"prediction record is missing id: {item}")
        payload = None
        for key in known_keys:
            if key in item:
                payload = item[key]
                break
        if payload is None:
            payload = {k: v for k, v in item.items() if k != "id"}
        predictions[str(case_id)] = payload
    return predictions


def parse_literal(raw: str) -> Any:
    text = raw.strip()
    if text == "true":
        return True
    if text == "false":
        return False
    if text == "null":
        return None
    if text == "[]":
        return []
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [part.strip() for part in inner.split(",")]
    return text


def parse_set(raw: str) -> set[str]:
    text = raw.strip()
    if not (text.startswith("{") and text.endswith("}")):
        raise ValueError(f"not a set expression: {raw}")
    inner = text[1:-1].strip()
    if not inner:
        return set()
    return {part.strip() for part in inner.split(",")}


def normalize_for_compare(value: Any, expected: Any) -> Any:
    if isinstance(expected, bool):
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in {"true", "false"}:
            return value.lower() == "true"
    if isinstance(expected, list):
        return value
    if value is None:
        return None
    return str(value)


def get_output_value(output: dict[str, Any], field: str) -> Any:
    if field.startswith("args."):
        args = output.get("arguments")
        if not isinstance(args, dict):
            return None
        return args.get(field.split(".", 1)[1])
    return output.get(field)


def field_exists(output: dict[str, Any], field: str) -> bool:
    if field.startswith("args."):
        args = output.get("arguments")
        return isinstance(args, dict) and field.split(".", 1)[1] in args
    return field in output


def check_no_field_outside_schema(output: dict[str, Any]) -> tuple[bool, str]:
    action = output.get("action")
    if action not in ACTION_ALLOWED_KEYS:
        return False, f"unknown action {action!r}"

    allowed = ACTION_ALLOWED_KEYS[action]
    extra = sorted(set(output.keys()) - allowed)
    if extra:
        return False, f"extra top-level fields: {extra}"

    if action == "tool_call":
        tool_name = output.get("tool_name")
        args = output.get("arguments")
        if not isinstance(args, dict):
            return False, "arguments must be an object for tool_call"
        allowed_args = TOOL_ALLOWED_ARGS.get(tool_name)
        if allowed_args is None:
            return False, f"unknown tool_name {tool_name!r}"
        extra_args = sorted(set(args.keys()) - allowed_args)
        if extra_args:
            return False, f"extra arguments for {tool_name}: {extra_args}"
    return True, ""


def tool_result_technicians(case: dict[str, Any]) -> list[dict[str, Any]]:
    tool_results = case.get("input", {}).get("tool_results", {})
    result = tool_results.get("find_technicians", {}) if isinstance(tool_results, dict) else {}
    if isinstance(result, list):
        return [x for x in result if isinstance(x, dict)]
    technicians = result.get("technicians", []) if isinstance(result, dict) else []
    return [x for x in technicians if isinstance(x, dict)]


def check_tool_result_membership(
    case: dict[str, Any], output: dict[str, Any], assertion: str
) -> tuple[bool, str]:
    match = re.fullmatch(
        r"([A-Za-z_][A-Za-z0-9_]*) in tool_results\.find_technicians\.technicians"
        r"(?:\[(\w+)==([^\]]+)\])?(?:\[\])?\.([A-Za-z_][A-Za-z0-9_]*)",
        assertion,
    )
    if not match:
        return False, "unsupported tool_results membership expression"

    output_field, filter_field, filter_value_raw, candidate_field = match.groups()
    expected_value = output.get(output_field)
    candidates = tool_result_technicians(case)

    if filter_field:
        filter_value = parse_literal(filter_value_raw)
        candidates = [
            item
            for item in candidates
            if normalize_for_compare(item.get(filter_field), filter_value) == filter_value
        ]

    allowed_values = [item.get(candidate_field) for item in candidates]
    passed = expected_value in allowed_values
    detail = "" if passed else f"{expected_value!r} not in {allowed_values!r}"
    return passed, detail


def check_gold_membership(
    case: dict[str, Any], output: dict[str, Any], assertion: str
) -> tuple[bool, str]:
    match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*) in gold_facts\.([A-Za-z_][A-Za-z0-9_]*)", assertion)
    if not match:
        return False, "unsupported gold_facts membership expression"
    field, gold_key = match.groups()
    value = output.get(field)
    allowed_values = case.get("gold_facts", {}).get(gold_key, [])
    passed = value in allowed_values
    detail = "" if passed else f"{value!r} not in gold_facts.{gold_key}: {allowed_values!r}"
    return passed, detail


def check_no_technician_outside_gold_facts(
    case: dict[str, Any], output: dict[str, Any]
) -> tuple[bool, str]:
    gold = case.get("gold_facts", {})
    allowed = set(gold.get("technicians_in_db", []) or [])
    values: list[str] = []

    if output.get("technician_name") not in UNKNOWN_VALUES:
        values.append(str(output.get("technician_name")))
    args = output.get("arguments")
    if isinstance(args, dict) and args.get("technician_name") not in UNKNOWN_VALUES:
        values.append(str(args.get("technician_name")))

    if not allowed:
        return len(values) == 0, f"technician values found while gold set is empty: {values}"

    invalid = sorted({value for value in values if value not in allowed})
    if invalid:
        return False, f"technicians outside gold_facts: {invalid}"
    return True, ""


def dimension_for_assertion(assertion: str) -> str:
    if assertion == "no_field_outside_schema":
        return "instruction_schema"
    if assertion.startswith("action =="):
        return "intent_action"
    if assertion.startswith("tool_name") or assertion.startswith("args.") or "keys(arguments)" in assertion:
        return "tool_call"
    if assertion.startswith("confirmation") or assertion.startswith("change_request"):
        return "intent_action"
    if assertion.startswith("changed_fields") or assertion.startswith("set(changed_fields)"):
        return "intent_action"
    if assertion.startswith("finalize") or assertion.startswith("unrelated =="):
        return "intent_action"
    if "tool_results.find_technicians" in assertion or "gold_facts" in assertion:
        return "hallucination"
    if assertion == "no_technician_outside_gold_facts":
        return "hallucination"
    if assertion in {"not_exists(weather)", "not_exists(temperature)", "not_exists(suggestion)"}:
        return "hallucination"
    if assertion.startswith("not_exists("):
        return "restraint_constraint"
    if assertion.startswith("set(missing_info)") or assertion.startswith("missing_info"):
        return "restraint_constraint"
    if assertion.startswith("info_complete") or assertion.startswith("question contains"):
        return "restraint_constraint"
    left = assertion.split("==", 1)[0].split("!=", 1)[0].strip()
    if left in FIELD_NAMES:
        return "field_extraction"
    return "other"


def evaluate_assertion(
    case: dict[str, Any], output: dict[str, Any], assertion: str
) -> tuple[bool, str, str]:
    dimension = dimension_for_assertion(assertion)

    if assertion == "no_field_outside_schema":
        passed, detail = check_no_field_outside_schema(output)
        return passed, detail, dimension

    if assertion == "no_technician_outside_gold_facts":
        passed, detail = check_no_technician_outside_gold_facts(case, output)
        return passed, detail, dimension

    if " in tool_results.find_technicians." in assertion:
        passed, detail = check_tool_result_membership(case, output, assertion)
        return passed, detail, dimension

    if " in gold_facts." in assertion:
        passed, detail = check_gold_membership(case, output, assertion)
        return passed, detail, dimension

    match = re.fullmatch(r"not_exists\(([^)]+)\)", assertion)
    if match:
        field = match.group(1)
        passed = not field_exists(output, field)
        detail = "" if passed else f"{field!r} exists with value {get_output_value(output, field)!r}"
        return passed, detail, dimension

    match = re.fullmatch(r"question contains (.+)", assertion)
    if match:
        needle = match.group(1).strip()
        question = output.get("question")
        passed = isinstance(question, str) and needle in question
        detail = "" if passed else f"question {question!r} does not contain {needle!r}"
        return passed, detail, dimension

    match = re.fullmatch(r"set\(keys\(arguments\)\) == (\{.*\})", assertion)
    if match:
        expected_set = parse_set(match.group(1))
        args = output.get("arguments")
        actual_set = set(args.keys()) if isinstance(args, dict) else set()
        passed = actual_set == expected_set
        detail = "" if passed else f"keys(arguments) {sorted(actual_set)} != {sorted(expected_set)}"
        return passed, detail, dimension

    match = re.fullmatch(r"set\(([^)]+)\) == (\{.*\})", assertion)
    if match:
        field, expected_raw = match.groups()
        expected_set = parse_set(expected_raw)
        actual = get_output_value(output, field)
        actual_set = {str(x) for x in actual} if isinstance(actual, list) else set()
        passed = actual_set == expected_set
        detail = "" if passed else f"set({field}) {sorted(actual_set)} != {sorted(expected_set)}"
        return passed, detail, dimension

    match = re.fullmatch(r"(.+?)\s*==\s*(.+)", assertion)
    if match:
        field, expected_raw = match.groups()
        field = field.strip()
        expected = parse_literal(expected_raw)
        actual = get_output_value(output, field)
        actual_norm = normalize_for_compare(actual, expected)
        passed = actual_norm == expected
        detail = "" if passed else f"{field} actual {actual!r} != expected {expected!r}"
        return passed, detail, dimension

    match = re.fullmatch(r"(.+?)\s*!=\s*(.+)", assertion)
    if match:
        field, expected_raw = match.groups()
        field = field.strip()
        forbidden = parse_literal(expected_raw)
        actual = get_output_value(output, field)
        actual_norm = normalize_for_compare(actual, forbidden)
        passed = actual_norm != forbidden
        detail = "" if passed else f"{field} actual {actual!r} must not equal {forbidden!r}"
        return passed, detail, dimension

    return False, f"unsupported assertion: {assertion}", dimension


def evaluate_case(case: dict[str, Any], payload: Any) -> dict[str, Any]:
    output, parse_error = parse_model_output(payload)
    assertion_results: list[dict[str, Any]] = []

    if output is None:
        for assertion in case.get("assertions", []):
            assertion_results.append(
                {
                    "assertion": assertion,
                    "dimension": dimension_for_assertion(assertion),
                    "passed": False,
                    "detail": parse_error,
                }
            )
        return {
            "id": case.get("id"),
            "task_type": case.get("task_type"),
            "layer": case.get("layer"),
            "json_valid": False,
            "parse_error": parse_error,
            "predicted_action": None,
            "expected_action": case.get("expected", {}).get("action"),
            "case_passed": False,
            "assertions_passed": 0,
            "assertions_total": len(case.get("assertions", [])),
            "assertion_results": assertion_results,
            "tags": case.get("tags", []),
        }

    for assertion in case.get("assertions", []):
        passed, detail, dimension = evaluate_assertion(case, output, assertion)
        assertion_results.append(
            {
                "assertion": assertion,
                "dimension": dimension,
                "passed": passed,
                "detail": detail,
            }
        )

    passed_count = sum(1 for item in assertion_results if item["passed"])
    total_count = len(assertion_results)

    return {
        "id": case.get("id"),
        "task_type": case.get("task_type"),
        "layer": case.get("layer"),
        "json_valid": True,
        "parse_error": None,
        "predicted_action": output.get("action"),
        "expected_action": case.get("expected", {}).get("action"),
        "case_passed": passed_count == total_count,
        "assertions_passed": passed_count,
        "assertions_total": total_count,
        "assertion_results": assertion_results,
        "tags": case.get("tags", []),
    }


def ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def pct(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.1f}%"


def get_case_assertion_map(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["assertion"]: item for item in result["assertion_results"]}


def get_aligned_quality_dimensions(results: list[dict[str, Any]]) -> dict[str, Any]:
    instruction_passed = 0
    tool_call_total = 0
    tool_call_passed = 0
    field_counts: dict[str, Counter[str]] = defaultdict(Counter)
    intent_total = 0
    intent_passed = 0
    intent_by_action: dict[str, Counter[str]] = defaultdict(Counter)
    restraint_total = 0
    restraint_passed = 0

    for result in results:
        assertion_map = get_case_assertion_map(result)

        # 指令 / 规则遵循 = JSON 可解析 + schema 合规 + 无越界字段
        schema_assertion = assertion_map.get("no_field_outside_schema")
        if result["json_valid"] and schema_assertion and schema_assertion["passed"]:
            instruction_passed += 1

        # 工具调用准确性 = action == tool_call + tool_name + args.* + keys(arguments) 全通过
        if result["expected_action"] == "tool_call":
            tool_call_total += 1
            relevant = [
                item
                for item in result["assertion_results"]
                if item["assertion"] == "action == tool_call" or item["dimension"] == "tool_call"
            ]
            if relevant and all(item["passed"] for item in relevant):
                tool_call_passed += 1

        # 意图判定准确性 = 主 action 分类准确率
        expected_action = result["expected_action"]
        predicted_action = result["predicted_action"]
        intent_total += 1
        intent_by_action[str(expected_action)]["total"] += 1
        if predicted_action == expected_action:
            intent_passed += 1
            intent_by_action[str(expected_action)]["passed"] += 1

        # 克制与约束遵守 = 核心 restraint 断言全部通过（排除问句措辞类）
        core_restraint_items = [
            item
            for item in result["assertion_results"]
            if item["dimension"] == "restraint_constraint" and not item["assertion"].startswith("question contains ")
        ]
        if core_restraint_items:
            restraint_total += 1
            if all(item["passed"] for item in core_restraint_items):
                restraint_passed += 1

        # 字段抽取准确性 = 各字段断言逐项统计，并给出按字段拆分
        for item in result["assertion_results"]:
            if item["dimension"] != "field_extraction":
                continue
            match = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s*(==|!=)", item["assertion"])
            if not match:
                continue
            field_name = match.group(1)
            if field_name not in FIELD_NAMES:
                continue
            field_counts[field_name]["total"] += 1
            if item["passed"]:
                field_counts[field_name]["passed"] += 1

    field_by_name: dict[str, dict[str, Any]] = {}
    total_field_passed = 0
    total_field_total = 0
    for field_name in sorted(field_counts):
        passed = field_counts[field_name]["passed"]
        total = field_counts[field_name]["total"]
        total_field_passed += passed
        total_field_total += total
        field_by_name[field_name] = {
            "passed": passed,
            "total": total,
            "pass_rate": ratio(passed, total),
        }

    return {
        "instruction_rule_following": {
            "passed": instruction_passed,
            "total": len(results),
            "pass_rate": ratio(instruction_passed, len(results)),
        },
        "tool_call_accuracy": {
            "passed": tool_call_passed,
            "total": tool_call_total,
            "pass_rate": ratio(tool_call_passed, tool_call_total),
        },
        "field_extraction_accuracy": {
            "passed": total_field_passed,
            "total": total_field_total,
            "pass_rate": ratio(total_field_passed, total_field_total),
            "by_field": field_by_name,
        },
        "intent_accuracy": {
            "passed": intent_passed,
            "total": intent_total,
            "pass_rate": ratio(intent_passed, intent_total),
            "by_action": {
                action: {
                    "passed": counts["passed"],
                    "total": counts["total"],
                    "pass_rate": ratio(counts["passed"], counts["total"]),
                }
                for action, counts in sorted(intent_by_action.items())
            },
        },
        "restraint_constraint_following": {
            "passed": restraint_passed,
            "total": restraint_total,
            "pass_rate": ratio(restraint_passed, restraint_total),
        },
    }


def get_hallucination_breakdown(results: list[dict[str, Any]]) -> dict[str, Any]:
    entity_total = 0
    entity_passed = 0
    external_total = 0
    external_passed = 0

    for result in results:
        for item in result["assertion_results"]:
            assertion = item["assertion"]
            if item["dimension"] != "hallucination":
                continue

            if (
                "gold_facts" in assertion
                or "tool_results.find_technicians" in assertion
                or assertion == "no_technician_outside_gold_facts"
            ):
                entity_total += 1
                if item["passed"]:
                    entity_passed += 1
                continue

            if assertion in {"not_exists(weather)", "not_exists(temperature)", "not_exists(suggestion)"}:
                external_total += 1
                if item["passed"]:
                    external_passed += 1

    entity_rate = None if entity_total == 0 else 1 - (entity_passed / entity_total)
    external_rate = None if external_total == 0 else 1 - (external_passed / external_total)

    return {
        "entity_hallucination": {
            "passed": entity_passed,
            "total": entity_total,
            "hallucination_rate": entity_rate,
        },
        "external_fact_hallucination": {
            "passed": external_passed,
            "total": external_total,
            "hallucination_rate": external_rate,
        },
    }


def summarize(results: list[dict[str, Any]], eval_path: Path, pred_label: str) -> dict[str, Any]:
    n = len(results)
    json_valid = sum(1 for item in results if item["json_valid"])
    case_passed = sum(1 for item in results if item["case_passed"])
    assertions_passed = sum(item["assertions_passed"] for item in results)
    assertions_total = sum(item["assertions_total"] for item in results)

    by_dimension: dict[str, dict[str, Any]] = {}
    dim_counts: dict[str, Counter[str]] = defaultdict(Counter)
    failed_assertions: Counter[str] = Counter()

    for result in results:
        for assertion in result["assertion_results"]:
            dimension = assertion["dimension"]
            dim_counts[dimension]["total"] += 1
            if assertion["passed"]:
                dim_counts[dimension]["passed"] += 1
            else:
                failed_assertions[assertion["assertion"]] += 1

    for dimension, counts in sorted(dim_counts.items()):
        total = counts["total"]
        passed = counts["passed"]
        by_dimension[dimension] = {
            "passed": passed,
            "total": total,
            "pass_rate": ratio(passed, total),
        }

    by_task_type: dict[str, dict[str, Any]] = {}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        grouped[str(result["task_type"])].append(result)
    for task_type, items in sorted(grouped.items()):
        total_assertions = sum(item["assertions_total"] for item in items)
        passed_assertions = sum(item["assertions_passed"] for item in items)
        by_task_type[task_type] = {
            "cases": len(items),
            "case_passed": sum(1 for item in items if item["case_passed"]),
            "case_pass_rate": ratio(sum(1 for item in items if item["case_passed"]), len(items)),
            "assertion_pass_rate": ratio(passed_assertions, total_assertions),
        }

    by_tag: dict[str, dict[str, Any]] = {}
    tag_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        for tag in result.get("tags", []):
            tag_groups[str(tag)].append(result)
    for tag, items in sorted(tag_groups.items()):
        by_tag[tag] = {
            "cases": len(items),
            "case_pass_rate": ratio(sum(1 for item in items if item["case_passed"]), len(items)),
        }

    hallucination = by_dimension.get("hallucination")
    hallucination_rate = None
    if hallucination and hallucination["total"]:
        hallucination_rate = 1 - hallucination["pass_rate"]

    aligned_quality_dimensions = get_aligned_quality_dimensions(results)
    hallucination_breakdown = get_hallucination_breakdown(results)

    return {
        "eval_path": str(eval_path),
        "prediction_source": pred_label,
        "n_cases": n,
        "json_valid_rate": ratio(json_valid, n),
        "case_pass_rate": ratio(case_passed, n),
        "assertion_pass_rate": ratio(assertions_passed, assertions_total),
        "assertions_passed": assertions_passed,
        "assertions_total": assertions_total,
        "dimension_scores": by_dimension,
        "aligned_quality_dimensions": aligned_quality_dimensions,
        "hallucination_rate": hallucination_rate,
        "hallucination_breakdown": hallucination_breakdown,
        "by_task_type": by_task_type,
        "by_tag": by_tag,
        "failed_assertions": failed_assertions.most_common(30),
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_report(path: Path, summary: dict[str, Any], results: list[dict[str, Any]]) -> None:
    dim = summary["dimension_scores"]
    aligned = summary["aligned_quality_dimensions"]
    field_breakdown = aligned["field_extraction_accuracy"]["by_field"]
    hallucination_breakdown = summary.get("hallucination_breakdown", {})
    field_note = " | ".join(
        f"{field} {pct(item['pass_rate'])}" for field, item in field_breakdown.items()
    )

    score_rows = [
        ("JSON 合法率", pct(summary["json_valid_rate"]), "json.loads 成功"),
        ("整例通过率", pct(summary["case_pass_rate"]), "该 case 所有规则均通过"),
        ("规则断言通过率", pct(summary["assertion_pass_rate"]), "所有 assertions 的平均通过率"),
        (
            "指令 / 规则遵循",
            pct(aligned["instruction_rule_following"]["pass_rate"]),
            "JSON合法 + schema合规 + 越界字段=0",
        ),
        (
            "工具调用准确性",
            pct(aligned["tool_call_accuracy"]["pass_rate"]),
            "action + tool_name + 参数 全中才算对",
        ),
        (
            "字段抽取准确性",
            pct(aligned["field_extraction_accuracy"]["pass_rate"]),
            field_note or "按字段逐项统计",
        ),
        (
            "意图判定准确性",
            pct(aligned["intent_accuracy"]["pass_rate"]),
            "主 action 分类准确率",
        ),
        (
            "克制与约束遵守",
            pct(aligned["restraint_constraint_following"]["pass_rate"]),
            "不该调时克制 + 不硬猜 + 边界约束",
        ),
        ("幻觉率", pct(summary["hallucination_rate"]), "越低越好：gold_facts / tool_results 越界"),
    ]

    lines: list[str] = []
    lines.append("# Slot-Extractor Evaluator Report")
    lines.append("")
    lines.append(f"- evalset: `{summary['eval_path']}`")
    lines.append(f"- predictions: `{summary['prediction_source']}`")
    lines.append(f"- n: `{summary['n_cases']}`")
    lines.append("")
    lines.append("## Scorecard")
    lines.append("")
    lines.append("| 维度 | 分数 | 说明 |")
    lines.append("|---|---:|---|")
    for name, value, note in score_rows:
        lines.append(f"| {name} | {value} | {note} |")

    entity_h = hallucination_breakdown.get("entity_hallucination", {})
    external_h = hallucination_breakdown.get("external_fact_hallucination", {})
    if entity_h or external_h:
        lines.append("")
        lines.append("## Hallucination Breakdown")
        lines.append("")
        lines.append("| 类型 | 幻觉率 | 通过/总数 | 说明 |")
        lines.append("|---|---:|---:|---|")
        if entity_h:
            lines.append(
                f"| entity_hallucination | {pct(entity_h.get('hallucination_rate'))} | "
                f"{entity_h.get('passed', 0)}/{entity_h.get('total', 0)} | "
                "技师 / 候选 / tool_results / gold_facts 越界 |"
            )
        if external_h:
            lines.append(
                f"| external_fact_hallucination | {pct(external_h.get('hallucination_rate'))} | "
                f"{external_h.get('passed', 0)}/{external_h.get('total', 0)} | "
                "weather / temperature / suggestion 外部事实越界 |"
            )

    lines.append("")
    lines.append("## By Task Type")
    lines.append("")
    lines.append("| task_type | cases | 整例通过率 | 断言通过率 |")
    lines.append("|---|---:|---:|---:|")
    for task_type, item in summary["by_task_type"].items():
        lines.append(
            f"| {task_type} | {item['cases']} | {pct(item['case_pass_rate'])} | {pct(item['assertion_pass_rate'])} |"
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

    failing_cases = [result for result in results if not result["case_passed"]]
    lines.append("")
    lines.append("## Failing Cases")
    lines.append("")
    if failing_cases:
        lines.append("| id | task_type | failed dimensions | failed assertions |")
        lines.append("|---|---|---|---|")
        for result in failing_cases[:50]:
            failed = [a for a in result["assertion_results"] if not a["passed"]]
            dimensions = sorted({a["dimension"] for a in failed})
            assertions = "; ".join(a["assertion"] for a in failed[:6])
            if len(failed) > 6:
                assertions += f"; ... +{len(failed) - 6}"
            lines.append(
                f"| {result['id']} | {result['task_type']} | {', '.join(dimensions)} | `{assertions}` |"
            )
    else:
        lines.append("No failing cases.")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Slot-Extractor predictions with rule assertions.")
    parser.add_argument("--eval", required=True, type=Path, help="Frozen eval JSONL path.")
    parser.add_argument("--pred", type=Path, help="Prediction JSONL path.")
    parser.add_argument("--use-expected", action="store_true", help="Use eval expected as prediction for self-check.")
    parser.add_argument("--out-dir", type=Path, help="Directory for report files.")
    args = parser.parse_args()

    if not args.use_expected and not args.pred:
        parser.error("provide --pred or --use-expected")

    cases = load_jsonl(args.eval)
    predictions = {}
    pred_label = "expected self-check"
    if args.use_expected:
        predictions = {str(case["id"]): case["expected"] for case in cases}
    else:
        predictions = load_predictions(args.pred)
        pred_label = str(args.pred)

    missing = [case["id"] for case in cases if str(case["id"]) not in predictions]
    if missing:
        raise ValueError(f"missing predictions for {len(missing)} cases, first: {missing[:5]}")

    results = [evaluate_case(case, predictions[str(case["id"])]) for case in cases]
    summary = summarize(results, args.eval, pred_label)

    if args.out_dir:
        out_dir = args.out_dir
    else:
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = Path("output") / "eval_runs" / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    write_jsonl(out_dir / "per_case_results.jsonl", results)
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_report(out_dir / "report.md", summary, results)

    print(f"wrote: {out_dir}")
    print(f"cases: {summary['n_cases']}")
    print(f"json_valid_rate: {pct(summary['json_valid_rate'])}")
    print(f"case_pass_rate: {pct(summary['case_pass_rate'])}")
    print(f"assertion_pass_rate: {pct(summary['assertion_pass_rate'])}")
    print(f"hallucination_rate: {pct(summary['hallucination_rate'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
