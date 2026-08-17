"""
Team Routing Matrix — the routing engine's brain.

This is the single source of truth for team ownership boundaries, few-shot
examples, exclusions, and cross-cutting disambiguation rules. It is used to
(a) seed the `teams` DB table and (b) build the classification system prompt.

Per the product plan, this draft needs sign-off from one owner per team
before real traffic is routed on it — treat it as a strong starting point,
not gospel. Edit the ownership_description / examples / exclusions here (and
re-run `python -m app.seed`) to refine it; the golden-set accuracy test in
tests/test_classification_accuracy.py is the objective check that an edit
didn't regress accuracy.
"""
from __future__ import annotations

TEAMS: list[dict] = [
    {
        "name": "IT",
        "slack_channel": "#it-support",
        "jira_project_key": "ITSUP",
        "ownership_description": (
            "End-user hardware, accounts/access, and productivity software — "
            "anything about a PERSON's ability to work, not production systems."
        ),
        "examples": [
            "Can't connect to VPN",
            "Need a new laptop, mine won't boot",
            "MFA app isn't generating codes",
            "Forgot my Windows password",
            "Need Photoshop license",
            "New hire starts Monday, needs accounts provisioned",
            "Printer on 3rd floor is jammed",
            "Zoom keeps crashing on my machine",
            "Need access to the shared drive for Finance",
            "My monitor won't turn on",
            "Can I get admin rights on my laptop to install X?",
            "Email isn't syncing on my phone",
            "Need a loaner laptop for a conference",
            "SSO login loop on the HR portal",
            "Bluetooth headset won't pair",
        ],
        "exclusions": [
            "Company-wide SaaS outages (route to DevOps if internally hosted, "
            "or note it's a 3rd-party vendor outage with no internal fix)",
            "Production database access requests for a live trading system "
            "(route to Ops or DevOps depending on which system)",
            "'The algo library won't import' (route to Algos — it's that "
            "team's dev-environment issue, not a laptop issue)",
        ],
    },
    {
        "name": "DevOps",
        "slack_channel": "#devops-support",
        "jira_project_key": "DEVOPS",
        "ownership_description": (
            "CI/CD, cloud infrastructure, Kubernetes/deployment platforms, "
            "monitoring/alerting, and production infra incidents — the "
            "'how it runs', not the business logic running on it."
        ),
        "examples": [
            "Production deploy failed",
            "CI pipeline stuck on the build step",
            "Need a new AWS S3 bucket for the reports service",
            "Grafana dashboard shows no data since this morning",
            "Kubernetes pod keeps crash-looping",
            "Need to rotate a secret in Vault",
            "ArgoCD app is stuck OutOfSync",
            "Can we get autoscaling on the pricing-api service?",
            "SSL cert expired on api.capitolis.com",
            "Need a new environment for QA testing",
            "Docker image build is failing on main",
            "Database connection pool exhausted, service returning 500s",
            "Need read access to the staging cluster",
            "Terraform apply failing with a state lock error",
            "Alerting is too noisy, need to tune thresholds",
        ],
        "exclusions": [
            "'The trade didn't settle' even though it technically ran on "
            "infra DevOps manages (route to Ops — it's a business-process "
            "incident, not an infra one)",
            "'The pricing model is returning NaN' (route to Algos, even if "
            "the request mentions 'the pipeline')",
            "Laptop/VPN issues even from an engineer (route to IT)",
        ],
    },
    {
        "name": "Ops",
        "slack_channel": "#ops-support",
        "jira_project_key": "OPSUP",
        "ownership_description": (
            "Trading operations, settlements, market data feeds, and "
            "production BUSINESS-PROCESS incidents that are not an "
            "infrastructure fault and not a model/pricing fault."
        ),
        "examples": [
            "Trade didn't settle",
            "Market data feed from Bloomberg looks stale",
            "End-of-day reconciliation shows a break",
            "Client onboarding is stuck at KYC step",
            "Wrong position showing in the risk report",
            "Corporate action wasn't applied to the portfolio",
            "Counterparty confirm hasn't come through",
            "NAV calculation looks off for fund X",
            "Trade booked with wrong currency",
            "Settlement instruction rejected by custodian",
            "Need to reprocess yesterday's batch job for fees",
            "Client statement generation failed overnight",
            "FX rate feed hasn't updated since 9am",
            "Duplicate trade entry in the blotter",
            "Regulatory report didn't submit on time",
        ],
        "exclusions": [
            "'The settlement service is down / throwing 500s' (route to "
            "DevOps — that's an infra fault even though the symptom is "
            "settlement-shaped; ask: is the system erroring, or is the "
            "business outcome wrong despite the system working?)",
            "'The pricing feed values look mathematically wrong' (route to "
            "Algos — a feed being STALE is Ops, a feed being MISCALCULATED "
            "is Algos)",
            "General password/access requests (route to IT)",
        ],
    },
    {
        "name": "Algos",
        "slack_channel": "#algos-support",
        "jira_project_key": "ALGO",
        "ownership_description": (
            "Pricing models, algorithmic trading logic, the quant library, "
            "and backtesting — anything about whether a CALCULATION or "
            "MODEL DECISION is correct."
        ),
        "examples": [
            "Model output looks wrong",
            "Backtest results don't match production for the same date",
            "Pricing model is returning NaN for illiquid bonds",
            "Need a new factor added to the risk model",
            "Quant library version bump broke a downstream calc",
            "Volatility surface looks inverted",
            "Strategy signal fired when it shouldn't have",
            "Need historical tick data pulled for a research request",
            "Model calibration hasn't run since last week",
            "Greeks calculation seems off for the options book",
            "New model needs code review before going to prod",
            "Curve construction is failing to converge",
            "Can we get a sandbox to test a new signal?",
            "Model version in prod doesn't match what was approved",
            "Basis risk calc looks inconsistent across books",
        ],
        "exclusions": [
            "'The model service won't deploy' (route to DevOps — a "
            "deployment/infra fault even though it's 'the model')",
            "'The feed Algos depends on is stale' (route to Ops if it's a "
            "market-data feed issue upstream; Algos only owns what happens "
            "to the data once it's used in a calculation)",
            "General 'the numbers look wrong on my dashboard' (clarify: "
            "dashboard bug is DevOps/IT, underlying number being wrong is "
            "Algos)",
        ],
    },
]

TEAM_NAMES = [t["name"] for t in TEAMS]

CROSS_CUTTING_RULES = """\
Cross-cutting routing rules (apply these to every request, in order):
1. Ask "what kind of wrong is it?": infra/system erroring -> DevOps;
   business outcome wrong but the system ran fine -> Ops; a
   calculation/model output wrong -> Algos; a person can't do their job ->
   IT. This is the single most useful disambiguation heuristic.
2. Multi-team requests: if a request plausibly spans two teams, route to
   the team that owns the ROOT CAUSE, not the symptom location, and put
   the other team in secondary_team.
3. Confidence: be honest about uncertainty. A generic or ambiguous request
   should get a LOWER confidence score, not a forced guess.
4. If the request is about something none of the four teams own (e.g. HR,
   Legal, Facilities), still pick the closest team but set confidence below
   0.5 so it routes to human review instead of auto-routing incorrectly.
"""


def build_system_prompt(teams: list[dict] | None = None) -> str:
    teams = teams or TEAMS
    team_blocks = []
    for t in teams:
        examples = "\n".join(f"  - {e}" for e in t["examples"])
        exclusions = "\n".join(f"  - {e}" for e in t.get("exclusions", []))
        team_blocks.append(
            f"### {t['name']}\n"
            f"Owns: {t['ownership_description']}\n"
            f"Example requests routed here:\n{examples}\n"
            f"Explicitly NOT this team (common mistakes):\n{exclusions}\n"
        )
    teams_text = "\n".join(team_blocks)
    team_names = ", ".join(t["name"] for t in teams)

    return f"""\
You are the classification engine for an internal Support AI Router at a \
fintech company (Capitolis). Your job: read one incoming support request \
and decide which team should own it.

The teams are: {team_names}.

{teams_text}

{CROSS_CUTTING_RULES}

Respond with ONLY a single JSON object, no prose before or after it, no \
markdown code fences. The JSON object must have exactly these fields:
{{
  "team": one of [{team_names}],
  "confidence": a number between 0.0 and 1.0,
  "urgency": one of ["low", "medium", "high"],
  "reasoning": a one-to-two sentence explanation,
  "secondary_team": one of [{team_names}] or null
}}
"""
