#!/usr/bin/env python3
"""Convert LlamaFactory generated predictions to the slot extractor evaluator format."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE_SFT = Path("/data/ZJ/llamafactory-workspace/datasets/slot_extractor_v0/slot_extractor_v0_test.json")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno}: invalid JSON: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{lineno}: row must be an object")
            rows.append(row)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def strip_think_blocks(text: str) -> str:
    return re.sub(r"<think>\s*.*?\s*</think>\s*", "", text, flags=re.DOTALL).strip()


def strip_markdown_fence(text: str) -> str:
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()

    return text.strip()


def extract_first_json_object(text: str) -> str:
    start = text.find("{")
    if start == -1:
        return text.strip()

    depth = 0
    in_string = False
    escaped = False

    for idx, char in enumerate(text[start:], start):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : idx + 1].strip()

    return text[start:].strip()


def sanitize_prediction_text(text: str) -> str:
    cleaned = strip_think_blocks(text)
    cleaned = strip_markdown_fence(cleaned)
    cleaned = extract_first_json_object(cleaned)
    return cleaned.strip()


def convert_predictions(
    raw_path: Path, source_sft_path: Path, output_path: Path, allow_prefix: bool = False
) -> dict[str, Any]:
    raw_rows = load_jsonl(raw_path)
    source_rows = load_json(source_sft_path)
    if not isinstance(source_rows, list):
        raise ValueError(f"{source_sft_path} must contain a JSON array.")

    if len(raw_rows) != len(source_rows):
        if allow_prefix and len(raw_rows) < len(source_rows):
            source_rows = source_rows[: len(raw_rows)]
        else:
            raise ValueError(
                f"row count mismatch: raw predictions={len(raw_rows)} source_sft={len(source_rows)}"
            )

    if len(raw_rows) != len(source_rows):
        raise ValueError(
            f"row count mismatch: raw predictions={len(raw_rows)} source_sft={len(source_rows)}"
        )

    converted: list[dict[str, Any]] = []
    empty_predictions = 0
    sanitized_predictions = 0

    for raw_row, source_row in zip(raw_rows, source_rows):
        if not isinstance(source_row, dict) or "id" not in source_row:
            raise ValueError(f"invalid source row in {source_sft_path}: {source_row!r}")

        predict_text = str(raw_row.get("predict") or "")
        if not predict_text.strip():
            empty_predictions += 1
        sanitized_text = sanitize_prediction_text(predict_text)
        if sanitized_text != predict_text.strip():
            sanitized_predictions += 1

        converted.append(
            {
                "id": str(source_row["id"]),
                "raw_output": sanitized_text,
            }
        )

    write_jsonl(output_path, converted)
    return {
        "raw_prediction_path": str(raw_path),
        "source_sft_path": str(source_sft_path),
        "output_path": str(output_path),
        "count": len(converted),
        "empty_predictions": empty_predictions,
        "sanitized_predictions": sanitized_predictions,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True, help="LlamaFactory generated_predictions.jsonl path.")
    parser.add_argument(
        "--source-sft",
        default=str(DEFAULT_SOURCE_SFT),
        help="Source SFT JSON path used for do_predict.",
    )
    parser.add_argument("--output", required=True, help="Output JSONL path for slot evaluator.")
    parser.add_argument(
        "--allow-prefix",
        action="store_true",
        help="Allow raw predictions to be a prefix of the source SFT rows.",
    )
    args = parser.parse_args()

    summary = convert_predictions(
        Path(args.raw),
        Path(args.source_sft),
        Path(args.output),
        allow_prefix=args.allow_prefix,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
