from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REQUIRED_KEYS = {
    "incident_summary",
    "root_cause",
    "evidence",
    "recommended_action",
    "confidence",
    "unknowns",
}


def load_result(path: str) -> dict[str, Any]:
    file_path = Path(path)

    if not file_path.exists():
        raise FileNotFoundError(
            f"Result file not found: {file_path}"
        )

    return json.loads(
        file_path.read_text(encoding="utf-8")
    )


def schema_is_valid(answer: dict[str, Any]) -> bool:
    """
    Improved prompt'ta istediğimiz JSON şemasına
    gerçekten uyulup uyulmadığını kontrol eder.
    """

    if not isinstance(answer, dict):
        return False

    if not REQUIRED_KEYS.issubset(answer.keys()):
        return False

    if not isinstance(
        answer["incident_summary"],
        str,
    ):
        return False

    if not isinstance(
        answer["root_cause"],
        str,
    ):
        return False

    if not isinstance(
        answer["evidence"],
        list,
    ):
        return False

    if not isinstance(
        answer["recommended_action"],
        list,
    ):
        return False

    if answer["confidence"] not in {
        "low",
        "medium",
        "high",
    }:
        return False

    if not isinstance(
        answer["unknowns"],
        list,
    ):
        return False

    return True


def count_duplicate_tools(
    tools: list[str],
) -> int:
    """
    Aynı case içinde tekrar kullanılan tool sayısını ölçer.

    Örnek:
    ["search_logs", "search_logs", "read_config"]

    toplam = 3
    unique = 2
    duplicate = 1
    """

    return len(tools) - len(set(tools))


def analyse_result(
    result: dict[str, Any],
) -> dict[str, Any]:

    cases = result.get("cases", [])

    total_cases = len(cases)

    diagnosis_passes = 0
    tool_passes = 0
    safety_passes = 0
    full_passes = 0
    schema_passes = 0

    total_tool_calls = 0
    duplicate_tool_calls = 0

    case_rows = []

    for case in cases:

        grading = case.get(
            "grading",
            {},
        )

        answer = case.get(
            "answer",
            {},
        )

        tools = case.get(
            "tools_used",
            [],
        )

        keyword_pass = grading.get(
            "keyword_pass",
            False,
        )

        tool_pass = grading.get(
            "tool_pass",
            False,
        )

        safety_pass = grading.get(
            "safety_pass",
            False,
        )

        full_pass = grading.get(
            "passed",
            False,
        )

        schema_pass = schema_is_valid(
            answer
        )

        duplicates = count_duplicate_tools(
            tools
        )

        if keyword_pass:
            diagnosis_passes += 1

        if tool_pass:
            tool_passes += 1

        if safety_pass:
            safety_passes += 1

        if full_pass:
            full_passes += 1

        if schema_pass:
            schema_passes += 1

        total_tool_calls += len(tools)

        duplicate_tool_calls += duplicates

        case_rows.append(
            {
                "id": case.get(
                    "id",
                    "unknown",
                ),
                "diagnosis": keyword_pass,
                "tool_pass": tool_pass,
                "safety": safety_pass,
                "schema": schema_pass,
                "full_pass": full_pass,
                "tool_count": len(tools),
                "duplicates": duplicates,
                "tools": tools,
            }
        )

    def rate(value: int) -> float:
        if total_cases == 0:
            return 0.0

        return value / total_cases

    return {
        "profile": result.get(
            "profile",
            "unknown",
        ),
        "cases": total_cases,
        "diagnosis_passes": (
            diagnosis_passes
        ),
        "diagnosis_rate": rate(
            diagnosis_passes
        ),
        "tool_passes": tool_passes,
        "tool_rate": rate(
            tool_passes
        ),
        "safety_passes": safety_passes,
        "safety_rate": rate(
            safety_passes
        ),
        "schema_passes": schema_passes,
        "schema_rate": rate(
            schema_passes
        ),
        "full_passes": full_passes,
        "full_pass_rate": rate(
            full_passes
        ),
        "total_tool_calls": (
            total_tool_calls
        ),
        "duplicate_tool_calls": (
            duplicate_tool_calls
        ),
        "case_rows": case_rows,
    }


def percentage(value: float) -> str:
    return f"{value:.0%}"


def print_summary(
    label: str,
    analysis: dict[str, Any],
) -> None:

    print()
    print(f"===== {label.upper()} =====")
    print()

    print(
        "Diagnosis accuracy: "
        f"{percentage(analysis['diagnosis_rate'])}"
    )

    print(
        "Required-tool adherence: "
        f"{percentage(analysis['tool_rate'])}"
    )

    print(
        "Safety adherence: "
        f"{percentage(analysis['safety_rate'])}"
    )

    print(
        "Schema adherence: "
        f"{percentage(analysis['schema_rate'])}"
    )

    print(
        "Full eval pass rate: "
        f"{percentage(analysis['full_pass_rate'])}"
    )

    print(
        "Total tool calls: "
        f"{analysis['total_tool_calls']}"
    )

    print(
        "Duplicate tool calls: "
        f"{analysis['duplicate_tool_calls']}"
    )


def print_case_table(
    baseline: dict[str, Any],
    improved: dict[str, Any],
) -> None:

    baseline_map = {
        row["id"]: row
        for row in baseline["case_rows"]
    }

    improved_map = {
        row["id"]: row
        for row in improved["case_rows"]
    }

    case_ids = sorted(
        set(baseline_map)
        | set(improved_map)
    )

    print()
    print("===== CASE COMPARISON =====")
    print()

    print(
        "| Case | Baseline | Improved | "
        "Baseline tools | Improved tools | "
        "Baseline schema | Improved schema |"
    )

    print(
        "|---|---:|---:|---:|---:|---:|---:|"
    )

    for case_id in case_ids:

        base = baseline_map.get(
            case_id,
            {},
        )

        imp = improved_map.get(
            case_id,
            {},
        )

        base_pass = (
            "PASS"
            if base.get("full_pass")
            else "FAIL"
        )

        imp_pass = (
            "PASS"
            if imp.get("full_pass")
            else "FAIL"
        )

        base_schema = (
            "PASS"
            if base.get("schema")
            else "FAIL"
        )

        imp_schema = (
            "PASS"
            if imp.get("schema")
            else "FAIL"
        )

        print(
            f"| {case_id} "
            f"| {base_pass} "
            f"| {imp_pass} "
            f"| {base.get('tool_count', 0)} "
            f"| {imp.get('tool_count', 0)} "
            f"| {base_schema} "
            f"| {imp_schema} |"
        )


def print_delta(
    baseline: dict[str, Any],
    improved: dict[str, Any],
) -> None:

    tool_delta = (
        improved["total_tool_calls"]
        - baseline["total_tool_calls"]
    )

    duplicate_delta = (
        improved["duplicate_tool_calls"]
        - baseline["duplicate_tool_calls"]
    )

    schema_delta = (
        improved["schema_rate"]
        - baseline["schema_rate"]
    )

    pass_delta = (
        improved["full_pass_rate"]
        - baseline["full_pass_rate"]
    )

    print()
    print("===== CHANGE =====")
    print()

    print(
        "Full eval pass rate: "
        f"{pass_delta:+.0%}"
    )

    print(
        "Schema adherence: "
        f"{schema_delta:+.0%}"
    )

    print(
        "Tool calls: "
        f"{tool_delta:+d}"
    )

    print(
        "Duplicate tool calls: "
        f"{duplicate_delta:+d}"
    )


def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Compare baseline and improved "
            "agent evaluation results."
        )
    )

    parser.add_argument(
        "baseline",
        help=(
            "Path to baseline eval JSON."
        ),
    )

    parser.add_argument(
        "improved",
        help=(
            "Path to improved eval JSON."
        ),
    )

    args = parser.parse_args()

    baseline_result = load_result(
        args.baseline
    )

    improved_result = load_result(
        args.improved
    )

    baseline_analysis = analyse_result(
        baseline_result
    )

    improved_analysis = analyse_result(
        improved_result
    )

    print_summary(
        "Baseline",
        baseline_analysis,
    )

    print_summary(
        "Improved",
        improved_analysis,
    )

    print_case_table(
        baseline_analysis,
        improved_analysis,
    )

    print_delta(
        baseline_analysis,
        improved_analysis,
    )


if __name__ == "__main__":
    main()