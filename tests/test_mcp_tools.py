from __future__ import annotations

from mcp import Client

from app.mcp_server import mcp


async def test_room_service_config_is_redacted_and_detectable() -> None:
    async with Client(mcp) as client:
        result = await client.call_tool("read_config", {"service": "room-service"})
        payload = result.structured_content
        config = payload["config"]

        assert "SUPABASE_SERVICE_KEY" in config["required_env"]
        assert "SUPABASE_SERVICE_KEY" not in config["present_env"]
        assert "secret_value" not in str(payload).lower()


async def test_log_search_finds_missing_key() -> None:
    async with Client(mcp) as client:
        result = await client.call_tool(
            "search_logs",
            {"query": "SUPABASE_SERVICE_KEY missing", "service": "room-service"},
        )
        matches = result.structured_content["matches"]
        assert any("SUPABASE_SERVICE_KEY is missing" in line for line in matches)
