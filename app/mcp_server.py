from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp.server import MCPServer

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

mcp = MCPServer("Reliability Lab")


def _read_json(name: str) -> Any:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


@mcp.tool()
def search_logs(query: str, service: str | None = None, limit: int = 20) -> dict[str, Any]:
    """Search production-like logs. Read-only. Returns matching lines and never changes system state."""
    query_terms = [term.lower() for term in query.split() if term.strip()]
    matches: list[str] = []

    for filename in ("backend.log", "liveops.log"):
        for line in (DATA / filename).read_text(encoding="utf-8").splitlines():
            lowered = line.lower()
            if service and f"service={service.lower()}" not in lowered:
                continue
            if query_terms and not all(term in lowered for term in query_terms):
                continue
            matches.append(line)
            if len(matches) >= max(1, min(limit, 50)):
                break
        if len(matches) >= max(1, min(limit, 50)):
            break

    return {"query": query, "service": service, "matches": matches}


@mcp.tool()
def read_config(service: str) -> dict[str, Any]:
    """Read the non-secret configuration summary for a service. Secret values are never returned."""
    configs = _read_json("config.json")
    config = configs.get(service)
    if config is None:
        return {"service": service, "found": False}
    return {"service": service, "found": True, "config": config}


@mcp.tool()
def check_service_health(service: str) -> dict[str, Any]:
    """Read the latest synthetic health snapshot for a service."""
    health = _read_json("health.json")
    result = health.get(service)
    if result is None:
        return {"service": service, "found": False}
    return {"service": service, "found": True, "health": result}


@mcp.tool()
def list_recent_deployments(service: str | None = None) -> dict[str, Any]:
    """List recent deployments. Read-only."""
    rows = _read_json("deployments.json")
    if service:
        rows = [row for row in rows if row["service"] == service]
    return {"deployments": rows}


if __name__ == "__main__":
    mcp.run()
