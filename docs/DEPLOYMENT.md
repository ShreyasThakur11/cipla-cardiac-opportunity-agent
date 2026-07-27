---
title: Deployment
layout: default
nav_order: 16
---

# Deployment

Three targets: a laptop for the presentation, a container for a shared demo,
and a cloud service if it needs to outlive the competition.

---

## Local, for the presentation

The configuration that matters most, because it is the one that has to work in
a room with a panel in it.

```bash
pip install -r requirements.txt && pip install -e .
cardiac-agent build
cardiac-agent doctor
streamlit run src/cardiac_agent/ui/streamlit_app.py
```

Before presenting:

1. Run `cardiac-agent doctor` and confirm every check passes.
2. Open the console once so the analysis context is cached. The first load
   takes about two seconds; every later interaction is instant.
3. Ask one question in the Ask tab to warm the agent.
4. **Decide whether to present with or without a model.** Without one, every
   number is identical and the prose is templated. That removes the network
   from the demonstration entirely, which is worth considering if the venue
   connection is unknown.

If a model is configured and the network fails mid-demonstration, the agent
falls back to the deterministic renderer and records the reason in the trace.
The demonstration continues.

---

## Docker

```bash
docker compose up --build
```

API on `http://localhost:8000`, console on `http://localhost:8501`. The `data/`
directory is bind-mounted, so place the workbook in `data/raw/` before starting
and the warehouse survives restarts.

Build the warehouse inside the container:

```bash
docker compose run --rm api cardiac-agent build
```

The image installs the package and runs as a non-root user. Model credentials
come from the environment and are never baked in.

---

## Cloud

The service is stateless apart from the warehouse file, which makes most
platforms straightforward.

### Container platforms

Cloud Run, App Runner, Azure Container Apps and similar work without change.
Two things to handle:

**The warehouse.** Either bake it into the image at build time, which is
simplest and correct since the data is static for the competition, or mount a
volume and run `cardiac-agent build` on first start.

**Startup time.** The analysis context takes about two seconds to build, and it
is built during FastAPI startup rather than on the first request. Set the
readiness probe against `/health`, which reports `degraded` with a specific
reason until the context is ready.

```dockerfile
# Baking the warehouse in, if the data may ship with the image
COPY data/raw/cardiac_dataset.xlsx data/raw/
RUN cardiac-agent build
```

Do not do that for anything public. The dataset is licensed material.

### Environment

```bash
CARDIAC_LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=...              # from a secret manager, never an image layer
CARDIAC_API_KEY=...                # requires X-API-Key on /agent and /analytics
CARDIAC_CORS_ORIGINS=https://your-console.example.com
CARDIAC_LOG_LEVEL=INFO
CARDIAC_API_HOST=0.0.0.0
CARDIAC_API_PORT=8000
```

`CARDIAC_API_KEY` is unset by default, which leaves the API open. Set it for
anything reachable beyond localhost.

### Sizing

One CPU and 1 GB of memory is enough. The context is about 150 MB resident and
the workload is bursty rather than sustained. Scale horizontally if needed;
each instance builds its own context at startup and there is no shared state to
coordinate.

---

## Operations

**Health.** `GET /health` returns `ok` or `degraded` with the reason, plus the
number of spaces scored, signals loaded, whether a model is available, and the
market total. A degraded response almost always means the warehouse is missing.

**Logs.** JSON, one object per line, with a `trace_id` correlating every line
from one agent run. Ship to whatever aggregator is available and query on
`trace_id` to reconstruct a run.

Events worth alerting on:

| Event | Meaning |
| --- | --- |
| `api.startup.warehouse_missing` | Service started without data; every request will 503 |
| `agent.tool.failed` | A tool raised something other than a validation error |
| `llm.rate_limited` | Provider throttling |
| `guardrail.scope.override_attempt` | Someone tried to override the instructions |
| `guardrail.numeric_grounding` with `passed=false` | A draft failed verification |

The last one is expected occasionally. A sustained rise means the model has
started inventing figures, and the deterministic fallback is carrying the load.

**Cost.** Only the model costs money. A question uses roughly 15,000 to 40,000
input tokens depending on how much evidence the planner gathers, and 1,000 to
3,000 output. The system prompt is marked for prompt caching, which matters
because it is re-sent on every turn of the tool loop. Setting
`CARDIAC_LLM_PROVIDER=none` reduces cost to zero without changing any number.

**Rebuilding.** If the organisers reissue the dataset:

```bash
cardiac-agent build --force
# restart the service; the context is cached per process
```

The build records a SHA-256 of the new file, so any result stays traceable to
its input.

---

## What is deliberately absent

**No database service.** DuckDB is a file. Adding Postgres would add an
operational dependency to a system whose entire dataset fits in 60 MB and never
changes during a run.

**No vector database.** Fourteen documents. See
[ARCHITECTURE.md](ARCHITECTURE.html).

**No authentication beyond a shared secret.** This is a competition submission,
not a multi-tenant product. `CARDIAC_API_KEY` is enough to stop casual access;
anything more would need real identity management.

**No background workers or queues.** The longest operation is four seconds.
