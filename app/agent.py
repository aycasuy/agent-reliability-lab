from __future__ import annotations

import argparse
import asyncio
import json
import os
from typing import Any

from dotenv import load_dotenv
from mcp import Client as MCPClient
from openai import OpenAI, RateLimitError, InternalServerError

from app.mcp_server import mcp
from app.prompts import PROMPTS
from app.schemas import AgentRun


def _tool_schema(tool: Any) -> dict[str, Any]:
    """
    MCP tool şemasını Gemini'nin OpenAI-compatible
    function calling formatına dönüştürür.
    """
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.input_schema,
        },
    }


def _mcp_result_to_jsonable(result: Any) -> Any:
    """
    MCP tool sonucunu Gemini'ye geri gönderebileceğimiz
    JSON uyumlu bir yapıya dönüştürür.
    """
    structured = getattr(
        result,
        "structured_content",
        None,
    )

    if structured is not None:
        return structured

    content = getattr(
        result,
        "content",
        None,
    ) or []

    text_parts: list[str] = []

    for item in content:
        text_value = getattr(
            item,
            "text",
            None,
        )

        if text_value is not None:
            text_parts.append(text_value)

    if text_parts:
        joined = "\n".join(text_parts)

        try:
            return json.loads(joined)

        except json.JSONDecodeError:
            return joined

    return None


def _parse_json_answer(
    text: str,
) -> dict[str, Any]:
    """
    Agent'ın final cevabının beklediğimiz JSON formatında
    olup olmadığını kontrol eder.
    """

    cleaned = text.strip()

    # Model bazen ```json ... ``` şeklinde dönebilir.
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")

        if cleaned.startswith("json"):
            cleaned = cleaned[4:].lstrip()

    try:
        parsed = json.loads(cleaned)

    except json.JSONDecodeError as exc:
        raise ValueError(
            "Agent did not return valid JSON.\n"
            f"Raw output:\n{text}"
        ) from exc

    required = {
        "incident_summary",
        "root_cause",
        "evidence",
        "recommended_action",
        "confidence",
        "unknowns",
    }

    missing = sorted(
        required - set(parsed)
    )

    if missing:
        raise ValueError(
            "Agent JSON is missing required keys: "
            f"{missing}"
        )

    return parsed


async def _call_gemini_with_retry(
    client: OpenAI,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
) -> Any:

    max_attempts = 6

    for attempt in range(max_attempts):

        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
            )

            return response

        # 429 - Free tier RPM limiti
        except RateLimitError:

            if attempt == max_attempts - 1:
                raise

            retry_seconds = 65

            print(
                f"[429] Rate limit reached. "
                f"Retrying in {retry_seconds}s..."
            )

            await asyncio.sleep(retry_seconds)

        # 503 - Gemini tarafında model yoğunluğu
        except InternalServerError:

            if attempt == max_attempts - 1:
                raise

            retry_seconds = min(
                2 ** (attempt + 1),
                30,
            )

            print(
                f"[503] Gemini is busy. "
                f"Retrying in {retry_seconds}s..."
            )

            await asyncio.sleep(retry_seconds)

    raise RuntimeError(
        "Gemini request failed after retries."
    )


async def diagnose(
    incident: str,
    profile: str = "improved",
) -> AgentRun:
    """
    Incident açıklamasını alır.

    Gemini:
      1. MCP tool listesini görür.
      2. Gereken tool'ları seçer.
      3. MCP üzerinden tool'ları çalıştırır.
      4. Tool sonuçlarını inceler.
      5. Final diagnosis JSON'unu üretir.
    """

    load_dotenv()

    api_key = os.environ.get(
        "GEMINI_API_KEY"
    )

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. "
            "Add it to your .env file."
        )

    model = os.environ.get(
        "GEMINI_MODEL",
        "gemini-3.8-flash",
    )

    if profile not in PROMPTS:
        raise ValueError(
            f"Unknown profile: {profile}"
        )

    # Gemini'nin OpenAI-compatible endpoint'i.
    client = OpenAI(
        api_key=api_key,
        base_url=(
            "https://generativelanguage.googleapis.com/"
            "v1beta/openai/"
        ),
    )

    # Agent'ın hangi MCP tool'larını kullandığını
    # kaydetmek için.
    tool_trace: list[str] = []

    # MCP client'ı in-memory MCP server'a bağlanıyor.
    async with MCPClient(mcp) as mc:

        # Server'daki tool'ları getir.
        tool_list = await mc.list_tools()

        tools = [
            _tool_schema(tool)
            for tool in tool_list.tools
        ]

        # İlk conversation history.
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": PROMPTS[profile],
            },
            {
                "role": "user",
                "content": incident,
            },
        ]

        # Agent'ın sonsuz tool-call döngüsüne
        # girmemesi için maksimum 8 tur.
        for _ in range(8):

            response = await _call_gemini_with_retry(
                client=client,
                model=model,
                messages=messages,
                tools=tools,
            )

            message = (
                response
                .choices[0]
                .message
            )

            # -------------------------------------------------
            # TOOL CALL YOKSA:
            # Agent final cevaba ulaşmış demektir.
            # -------------------------------------------------

            if not message.tool_calls:

                raw_text = (
                    message.content or ""
                )

                answer = _parse_json_answer(
                    raw_text
                )

                return AgentRun(
                    answer=answer,
                    tools_used=tool_trace,
                    raw_text=raw_text,
                )

            # -------------------------------------------------
            # TOOL CALL VARSA:
            #
            # Gemini'nin döndürdüğü tool-call objesini
            # mümkün olduğunca AYNEN history'ye ekliyoruz.
            #
            # Özellikle Gemini 3.x modellerinde
            # thought_signature kaybolmamalı.
            # -------------------------------------------------

            tool_calls_for_history = []

            for call in message.tool_calls:

                call_data = call.model_dump(
                    exclude_none=True
                )

                tool_calls_for_history.append(
                    call_data
                )

            messages.append(
                {
                    "role": "assistant",
                    "content": message.content,
                    "tool_calls": (
                        tool_calls_for_history
                    ),
                }
            )

            # -------------------------------------------------
            # Gemini'nin istediği MCP tool'larını çalıştır.
            # -------------------------------------------------

            for call in message.tool_calls:

                tool_name = (
                    call.function.name
                )

                raw_arguments = (
                    call.function.arguments
                    or "{}"
                )

                try:
                    arguments = json.loads(
                        raw_arguments
                    )

                except json.JSONDecodeError:
                    arguments = {}

                print(
                    f"[tool] {tool_name} "
                    f"{arguments}"
                )

                # Tool MCP üzerinden çağrılıyor.
                result = await mc.call_tool(
                    tool_name,
                    arguments,
                )

                # Trace'e kaydet.
                tool_trace.append(
                    tool_name
                )

                tool_result = (
                    _mcp_result_to_jsonable(
                        result
                    )
                )

                # Tool sonucunu Gemini conversation
                # history'sine ekle.
                messages.append(
                    {
                        "role": "tool",
                        "name": tool_name,
                        "tool_call_id": call.id,
                        "content": json.dumps(
                            tool_result,
                            ensure_ascii=False,
                        ),
                    }
                )

    raise RuntimeError(
        "Agent exceeded maximum "
        "tool-call loop."
    )


async def _main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "MCP-based incident "
            "diagnosis agent."
        )
    )

    parser.add_argument(
        "incident",
        help=(
            "Incident description "
            "for the agent to diagnose."
        ),
    )

    parser.add_argument(
        "--profile",
        choices=sorted(PROMPTS),
        default="improved",
        help=(
            "Prompt profile to use."
        ),
    )

    args = parser.parse_args()

    run = await diagnose(
        incident=args.incident,
        profile=args.profile,
    )

    print()
    print("===== AGENT RESULT =====")
    print()

    print(
        json.dumps(
            {
                "answer": run.answer,
                "tools_used": (
                    run.tools_used
                ),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    asyncio.run(_main())