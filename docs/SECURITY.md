---
title: Security
layout: default
nav_order: 17
---

# Security

## Threat model

This system reads a confidential dataset, calls an external model API, and
exposes an interface that accepts free text. Four things can go wrong.

| Threat | Where it lands | Control |
| --- | --- | --- |
| Confidential data leaks | The competition dataset in a public repository | Excluded from version control, documented, and the exclusion is the default |
| Credentials leak | API key in a commit, a log or an image layer | Read from the environment, never logged, never written to an artefact |
| Prompt injection | Instruction-shaped text reaching the model through a tool result | Detected, neutralised, and wrapped in a data envelope |
| The warehouse is modified | Model-generated SQL | Statement allowlist, keyword denylist, and a read-only connection |

---

## Data confidentiality

The Cardiac workbook and the case PDF are licensed material.

`.gitignore` excludes `data/raw/*` with an explicit allowlist for the README
and `.gitkeep`, so adding a file to that directory does not accidentally stage
it. The derived warehouse and parquet mirror are also excluded, because they
contain the same data in a different shape.

Before the first push:

```bash
git status --porcelain          # must not list anything under data/raw
git ls-files data/              # must show only README.md and .gitkeep files
```

If the workbook has already been committed, removing it in a later commit is
not enough. The history has to be rewritten with `git filter-repo` or the
repository recreated.

---

## Credentials

Read from the environment, optionally via `.env`, which is excluded from
version control. `.env.example` ships with every variable named and every value
blank.

The API key is never written to a log line. The structured logger records the
provider name and model identifier, never the credential. `cardiac-agent
doctor` reports `credentials: found` rather than any part of the key.

The Anthropic SDK is constructed with no arguments, so it also resolves an
`ant auth login` profile if one exists, which avoids a static key on a
developer machine entirely.

---

## Prompt injection

Everything the agent reads through a tool is data, not instruction. The signal
corpus is trusted because it is in this repository, but the boundary is
enforced in code rather than assumed, for two concrete reasons: the corpus is
designed to be extended, and `sql_query` returns free text from the warehouse
that originated outside our control.

`guardrails/injection.py` scans retrieved text for instruction-shaped patterns
(instruction overrides, role assertions, fake system tags, requests to reveal
the prompt or skip citation), replaces any match with a visible
`[filtered: instruction-like content]` marker, and wraps the result in a
`<retrieved_data source=...>` envelope so the model can see what it is looking
at.

Matches are replaced rather than deleted, so a tampering attempt stays visible
in the trace instead of disappearing silently.

The scope guard catches override attempts in the user's own question before any
tool runs, and refuses without echoing the system prompt.

---

## SQL safety

`sql_query` is the escape hatch for questions the purpose-built tools do not
cover. It is guarded three ways, and each would be sufficient alone:

1. The statement must begin with `SELECT` or `WITH`.
2. A denylist rejects `INSERT`, `UPDATE`, `DELETE`, `DROP`, `CREATE`, `ALTER`,
   `ATTACH`, `COPY`, `EXPORT`, `INSTALL`, `LOAD`, `PRAGMA` and others.
3. Multiple statements are rejected, so `SELECT 1; DROP TABLE x` cannot get
   through on a technicality.
4. The connection itself is opened `read_only=True`, so a bypass of the first
   three still cannot write.

Results are capped at 200 rows and the query is wrapped in an outer `LIMIT`, so
a model cannot exhaust memory by selecting everything.

The test suite parameterises six mutating statements and asserts each is
rejected.

---

## API surface

`CARDIAC_API_KEY` is unset by default, which leaves the API open. That is
correct for localhost and wrong for anything else. When set, `/agent` and
`/analytics` require a matching `X-API-Key` header. `/health` stays open so a
load balancer can probe it.

CORS defaults to `http://localhost:8501`, the Streamlit console, and only
`GET` and `POST` are allowed. Credentials are not allowed on cross-origin
requests.

Request bodies are validated by Pydantic at the boundary, so a malformed
request returns 422 rather than failing somewhere inside the scoring engine.
Question length is capped at 2,000 characters.

Errors return a message, never a stack trace.

---

## Model interaction

**No user data is sent anywhere except the model provider**, and only the
question plus the evidence the tools produced. The dataset itself is never
uploaded; the model sees summarised tool results.

**Refusals are handled explicitly.** A provider may return `stop_reason:
"refusal"` with a normal 200 response and an empty content array. The client
checks that before reading content, and the agent falls back to the
deterministic renderer rather than crashing.

**A provider failure is not a system failure.** Any exception from the model
call is caught, logged with its type, and the run continues deterministically.
The reason is recorded in the trace under `warnings`.

---

## What this system does not do

- It does not write to the warehouse at runtime. The only writer is
  `cardiac-agent build`.
- It does not execute model-generated code. There is no code-execution tool.
- It does not fetch URLs at runtime. The signal corpus is static files on disk,
  reviewed before they are committed.
- It does not persist user questions beyond the process. Conversation memory is
  in-process and bounded, and stores intent and space labels rather than
  figures.
- It does not have user accounts, roles or per-user data.

---

## Reporting

For a competition submission, raise anything found as an issue on the
repository. For a production deployment this section would name a security
contact and a disclosure window.
