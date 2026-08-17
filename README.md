# Support AI Router

An internal Support AI layer for Capitolis: a single intake point that
listens to support requests, classifies them with an LLM (Claude) into one
of four team queues, and routes them — posting to the team's Slack channel,
creating a Jira ticket, and identifying the on-call person — with a
human-review fallback whenever the model isn't confident.

Full product plan: see `.hermes/plans/2026-08-17_104304-support-ai-routing-bot.md`
in the planning session (or ask for a copy) for the complete phased roadmap,
non-goals, and open risks. This README covers what's built and how to run it.

## The four teams

| Team | Slack | Jira project | Owns |
|---|---|---|---|
| IT | `#it-support` | `ITSUP` | End-user hardware, accounts/access, productivity software |
| DevOps | `#devops-support` | `DEVOPS` | CI/CD, cloud infra, Kubernetes, monitoring, infra incidents |
| Ops | `#ops-support` | `OPSUP` | Trading ops, settlements, market data, business-process incidents |
| Algos | `#algos-support` | `ALGO` | Pricing models, algo logic, quant library, backtesting |

The full routing matrix — 15 examples + explicit exclusions per team, plus
cross-cutting disambiguation rules — lives in `backend/app/routing_matrix.py`
and is the single source of truth for both the seeded `teams` DB table and
the classification system prompt. **This draft needs sign-off from one
owner per team before real traffic is routed on it.**

## Architecture

- **FastAPI backend** (`backend/app/`) + **zero-build Alpine.js/Tailwind
  frontend** (`frontend/`) — same tech approach as the `ask-devops-dashboard`
  project.
- **Classification service** (`app/services/classification_service.py`)
  calls the Anthropic Messages API directly via `httpx` (no SDK), asks for
  structured JSON (`team`, `confidence`, `urgency`, `reasoning`,
  `secondary_team`), and falls back cleanly to human review if the API key
  is unset, the call fails, or the response can't be parsed after one retry.
- **Routing engine** (`app/services/routing_engine.py`) is confidence-gated:
  below `SUPPORTROUTER_CONFIDENCE_THRESHOLD` (default `0.7`), a request goes
  to `pending_review` with **zero** adapter calls — no bad ticket, no wrong
  Slack ping.
- **Pluggable adapters** (`app/adapters/`) — Slack and Jira each have a
  `Protocol` + a `Mock*Adapter` (default, in-memory + JSONL log, no network)
  + a `Real*Adapter` (live API). Select per-process via
  `SUPPORTROUTER_SLACK_MODE` / `SUPPORTROUTER_JIRA_MODE` (`mock` or `real`).
  On-call (`app/adapters/oncall_adapter.py`) reads a simple stored rotation
  table — the real source of truth for v1, until a PagerDuty/Opsgenie
  integration is added later.
- **Audit log** (`app/services/audit.py`) — append-only JSONL, one entry per
  routing decision.
- **SQLite** by default (`data/app.db`); override
  `SUPPORTROUTER_DATABASE_URL` for Postgres later without touching callers.

## Quickstart (local dev)

```bash
cd backend
uv venv .venv --python 3.11
source .venv/bin/activate
uv pip install -r requirements.txt
python -m app.seed          # seeds the 4 teams
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Or via the Makefile: `make dev-up` (from the repo root).

On first run, a local admin account is seeded with a random password
written once to `data/INITIAL_LOGIN_CREDENTIALS.txt` (0600 perms, gitignored
`data/` dir) — log in at `http://localhost:8000/auth/login`, then delete
that file.

Set `ANTHROPIC_API_KEY` (copy `.env.example` to `.env`) to get real LLM
classification; without it, every request routes straight to human review
with a `[LLM unavailable]` note — never a silent guess.

### Docker

```bash
docker compose up -d --build
```

## Testing

```bash
cd backend && source .venv/bin/activate
pytest -v                                   # unit + integration-marked-but-skipped tests
pytest tests/test_classification_accuracy.py -v -m integration -s   # real-API golden-set accuracy (needs ANTHROPIC_API_KEY)
```

The golden-set accuracy test runs all 60 examples from the routing matrix
through the real Claude API and asserts ≥90% overall accuracy with no team
below 85%. This is the objective quality gate for any edit to
`routing_matrix.py` — **last verified run: 100% (60/60)**, see
`backend/tests/golden_set/routing_examples.json` for the full set.

## API

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Public health check |
| GET/POST | `/auth/login`, `/auth/local-login`, `/auth/logout` | Local username/password auth |
| POST | `/api/requests` | Submit a support request; runs classify → route → persist |
| GET | `/api/requests` | List recent requests with their routing outcome |
| GET | `/api/teams` | List the 4 teams and their ownership descriptions |
| GET/POST | `/api/oncall` | Current on-call per team / add a rotation entry |
| GET | `/api/audit` | Tail the audit log |

## What's not built yet (see the full plan for the phased roadmap)

- Real Slack Events API intake (inbound messages) — only outbound posting
  is wired for `RealSlackAdapter`; a `/support` slash command / webhook
  endpoint is Phase 3.
- Real Jira ticket creation is implemented (`RealJiraAdapter`) but untested
  against a live Jira instance — needs real project keys + API token
  (Phase 4).
- Team Routing Matrix editor UI (currently code-only, edit
  `routing_matrix.py` + re-seed).
- Analytics / feedback loop (override-rate tracking, `Feedback` table is
  modeled but not yet wired to a UI).
- PII/data-retention policy for `raw_text` sent to the LLM — flagged as an
  open risk in the plan, needs a decision before real production traffic.
