# Agent Reliability Lab

A small incident-diagnosis agent built to explore **MCP tools, agent reliability, tracing, and eval-driven prompt improvement**.

The project intentionally uses read-only production-like tools and a repeatable eval suite. The goal is not to build a generic chatbot; it is to show how an agent workflow can be measured, debugged, and improved.

## What it demonstrates

- An MCP server exposing read-only operational tools
- An LLM agent that discovers and calls MCP tools
- Tool-call tracing for every run
- A baseline prompt and a reliability-focused improved prompt
- 10 repeatable eval cases covering:
  - root-cause accuracy
  - required tool usage
  - insufficient-evidence behavior
  - non-destructive behavior
  - secret-handling behavior
- JSON and Markdown eval reports
- A simple baseline-vs-improved comparison script

## Architecture

```text
User incident
    |
    v
OpenAI Responses API
    |
    | function/tool call
    v
MCP Client
    |
    v
MCPServer
  ├─ search_logs()
  ├─ read_config()
  ├─ check_service_health()
  └─ list_recent_deployments()
    |
    v
Synthetic logs/config/health/deployment data
```

The MCP client and server run in-memory for this lab, but the calls still go through the MCP protocol layer. That keeps the project small while preserving the same tool boundary that could later be moved to stdio or HTTP.

## Example incident

> Players cannot join multiplayer rooms after this morning's room-service deployment.

The agent should investigate logs/config rather than guessing. The synthetic evidence contains a missing `SUPABASE_SERVICE_KEY`; the tool never exposes a secret value.

Expected style of output:

```json
{
  "incident_summary": "Room joins are failing after the deployment.",
  "root_cause": "room-service is missing the required SUPABASE_SERVICE_KEY environment variable",
  "evidence": [
    "room-service logs report AUTH_INIT_FAILED because SUPABASE_SERVICE_KEY is missing",
    "the config summary lists the key as required but not present"
  ],
  "recommended_action": [
    "restore the secret through the deployment secret manager",
    "redeploy or restart the affected service through the normal release process",
    "verify room-join success rate after recovery"
  ],
  "confidence": "high",
  "unknowns": []
}
```

## Setup

Requires Python 3.10+.

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
```

macOS/Linux:

```bash
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Add your API key to `.env`:

```text
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5.6-luna
```

## Run one incident

```bash
python -m app.agent "Players cannot join multiplayer rooms after today's room-service deployment."
```

Try the weaker baseline prompt:

```bash
python -m app.agent "Players cannot join multiplayer rooms after today's room-service deployment." --profile baseline
```

## Run the eval suite

Run baseline:

```bash
python -m evals.run_evals --profile baseline
```

Run improved:

```bash
python -m evals.run_evals --profile improved
```

Each run writes machine-readable JSON and a Markdown summary under `evals/results/`.

Compare two saved runs:

```bash
python -m evals.compare \
  evals/results/baseline-YYYYMMDD-HHMMSS.json \
  evals/results/improved-YYYYMMDD-HHMMSS.json
```

Do **not** put made-up pass rates in this README. Run both profiles and publish the real numbers.

## Tests

```bash
pytest
```

The tests exercise the MCP protocol in-memory rather than calling the underlying Python functions directly.

## Why two prompts?

The baseline prompt is deliberately underspecified. The improved prompt adds explicit reliability rules:

- evidence before conclusions
- minimum necessary tool use
- no fabricated remediation
- no secret disclosure
- explicit uncertainty when evidence is insufficient
- consistent JSON output

The eval suite is the proof mechanism. A prompt change is only considered an improvement if the saved evaluation results support it.

## Safety choices

This lab deliberately exposes **read-only** operational tools. There is no tool for restart, deploy, delete, credential rotation, or arbitrary shell execution.

That is intentional: an investigation agent should first prove that it can retrieve evidence reliably before it is given write access.

## Next steps

- Add a trace viewer with per-tool latency and token usage
- Add an LLM-as-judge grader alongside deterministic graders
- Add regression thresholds to CI
- Run the MCP server over stdio or Streamable HTTP
- Add a second skill, e.g. release-risk review or bug-triage
- Replace synthetic data with a safe local observability stack

## Project note

The incidents and operational data in this repository are synthetic. No production credentials or private company data are included.
