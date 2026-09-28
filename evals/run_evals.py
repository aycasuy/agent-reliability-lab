from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.agent import diagnose

ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "evals" / "cases.json"
RESULTS_DIR = ROOT / "evals" / "results"


def _flatten_answer(answer: dict[str, Any]) -> str:
    return json.dumps(answer, ensure_ascii=False).lower()


def grade(case: dict[str, Any], answer: dict[str, Any], tools_used: list[str]) -> dict[str, Any]:
    flattened = _flatten_answer(answer)

    keyword_hits = [kw for kw in case.get("expected_keywords", []) if kw.lower() in flattened]
    keyword_pass = len(keyword_hits) == len(case.get("expected_keywords", []))

    required_tools = case.get("required_tools", [])
    tool_pass = all(tool in tools_used for tool in required_tools)

    forbidden = case.get("forbidden_answer_phrases", [])
    forbidden_hits = [phrase for phrase in forbidden if phrase.lower() in flattened]
    safety_pass = not forbidden_hits

    passed = keyword_pass and tool_pass and safety_pass
    return {
        "passed": passed,
        "keyword_pass": keyword_pass,
        "tool_pass": tool_pass,
        "safety_pass": safety_pass,
        "keyword_hits": keyword_hits,
        "missing_tools": [tool for tool in required_tools if tool not in tools_used],
        "forbidden_hits": forbidden_hits,
    }


async def run(profile: str, limit: int | None = None) -> dict[str, Any]:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    if limit:
        cases = cases[:limit]

    rows = []
    for case in cases:
        try:
            run_result = await diagnose(case["incident"], profile=profile)
            grading = grade(case, run_result.answer, run_result.tools_used)
            rows.append({
                "id": case["id"],
                "incident": case["incident"],
                "answer": run_result.answer,
                "tools_used": run_result.tools_used,
                "grading": grading,
            })
            mark = "PASS" if grading["passed"] else "FAIL"
            print(f"[{mark}] {case['id']} | tools={run_result.tools_used}")
        except Exception as exc:
            rows.append({
                "id": case["id"],
                "incident": case["incident"],
                "error": str(exc),
                "tools_used": [],
                "grading": {"passed": False},
            })
            print(f"[ERROR] {case['id']} | {exc}")

    passed = sum(1 for row in rows if row["grading"].get("passed"))
    total = len(rows)
    return {
        "profile": profile,
        "model": "from OPENAI_MODEL",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "passed": passed,
        "total": total,
        "pass_rate": passed / total if total else 0,
        "cases": rows,
    }


def write_markdown(result: dict[str, Any], path: Path) -> None:
    lines = [
        f"# Eval Results — {result['profile']}",
        "",
        f"- Passed: **{result['passed']} / {result['total']}**",
        f"- Pass rate: **{result['pass_rate']:.0%}**",
        f"- Generated: `{result['generated_at']}`",
        "",
        "| Case | Result | Tools used |",
        "|---|---:|---|",
    ]
    for row in result["cases"]:
        result_text = "PASS" if row["grading"].get("passed") else "FAIL"
        tools = ", ".join(row.get("tools_used", [])) or "—"
        lines.append(f"| {row['id']} | {result_text} | {tools} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=["baseline", "improved"], default="improved")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    result = await run(args.profile, args.limit)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = RESULTS_DIR / f"{args.profile}-{stamp}.json"
    md_path = RESULTS_DIR / f"{args.profile}-{stamp}.md"

    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(result, md_path)

    print()
    print(f"Pass rate: {result['passed']}/{result['total']} ({result['pass_rate']:.0%})")
    print(f"JSON: {json_path}")
    print(f"Markdown: {md_path}")


if __name__ == "__main__":
    asyncio.run(_main())
