# Multi-Agent BI Analyst

Natural-language business question -> validated SQL -> results -> (next: analysis, chart, insight).
Built on LangGraph. Every request is traced to `traces/<id>.jsonl`.

```
router -> simple:     [plan -> schema_link -> write_sql -> validate -> execute -> check_results]
       -> multi_step: the same pipeline once per sub-question (max 4)

single-question pipeline:
plan -> schema_link -> write_sql -> validate -> execute -> check_results -> END
                          ^            |           |
                          +-- correct -+-----------+   (max 3 attempts, then `fail`)
```

## Quick start
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env            # then edit .env: pick a provider (Anthropic or a FREE one) and add its key
python -m bi_analyst.cli init-demo
python -m bi_analyst.cli ask "What is revenue by product category for completed orders?"
uvicorn bi_analyst.api:app --reload   # POST /ask, GET /schema
pytest                                # runs offline with a scripted FakeLLM
```

## What exists now (Phases 1-2 + start of 3)
| Piece | File | Notes |
|---|---|---|
| Planner agent | `agents/planner.py` | short plan, resolves ambiguity |
| Schema linking | `agents/schema_agent.py` | lexical + FK expansion; swap for embeddings |
| SQL writer | `agents/sql_writer.py` | schema + plan + failed-attempt context |
| SQL validator | `agents/validator.py` | sqlglot parse, read-only, table/column check, `EXPLAIN` |
| Corrector | `agents/corrector.py` | classifies error type -> targeted repair hint |
| Executor | `db.py` | read-only conn, timeout, row cap |
| Result checks | `agents/data_validator.py` | empty / all-NULL / negative / >100% |
| Tracing | `tracing.py` | JSONL per request |

Design choices: no module-level globals (concurrency-safe); `llm.complete(..., agent=...)`
so each agent can later use a different model; DB layer via SQLAlchemy (Postgres = change `BI_DB_URL`).

## Next steps
1. **Eval harness** (`eval/`): 50+ questions with gold SQL, execution-accuracy, correction lift, ablations.
2. **Analyst / viz / insight agents**: pandas stats -> Vega-Lite/Plotly spec -> grounded narrative.
3. **MCP layer**: expose db / schema / metrics / chart as MCP servers; add a tool-selector node.
4. **Better data validation**: join-explosion detection, LLM answer-relevance check.
5. **Embedding-based schema linking** and a metrics/semantic layer (see WrenAI).

## Choosing an LLM provider (including free options)
Set these in `.env` (loaded automatically) or as environment variables:

| Provider | `BI_PROVIDER` | Key variable | Example `BI_MODEL` (verify in provider console) |
|---|---|---|---|
| Anthropic (paid) | `anthropic` | `ANTHROPIC_API_KEY` | `claude-sonnet-5-5` |
| Groq (free tier) | `groq` | `BI_API_KEY` | `llama-3.3-70b-versatile` |
| Google Gemini (free tier) | `gemini` | `BI_API_KEY` | `gemini-2.5-flash` |
| OpenRouter (free models) | `openrouter` | `BI_API_KEY` | a model id ending in `:free` |
| Ollama (local, no key) | `ollama` | none | `llama3.1` |
| Any OpenAI-compatible API | `openai_compat` | `BI_API_KEY` + `BI_BASE_URL` | provider's model id |

Free tiers have rate and daily limits and free models are usually weaker at SQL than
frontier models, so accuracy numbers from a free model are not comparable with Claude's.

## Router (multi-part questions)
`agents/router.py` makes one LLM call per question and returns `route` = `simple` or `multi_step`
plus self-contained `sub_questions`. Multi-step questions run the full pipeline once per
sub-question; each appears in the trace as a `sub_question` marker.

- **Dependent steps:** sub-questions run in order. Each later one is given a compact preview of the
  earlier results (first 10 rows, length-capped), so it can build on them, for example "the category
  with the highest revenue in the previous step". Its SQL must still be one SELECT over the real
  tables; earlier results are context for choosing filters, not tables. A failed earlier step is
  reported to later steps as failed, and they still run.
- **Result for `multi_step`:** `sub_results` holds every sub-question's SQL and rows. The top-level
  `sql`, `columns`, `rows` mirror the **primary** result (`primary_index`, 1-based): the last
  sub-question that succeeded. For a chained question that is the final answer; for independent
  questions it is just one of several tables, so read `sub_results`. `status` is `success`,
  `partial` or `failed`.
- Any bad router output falls back to the simple path.
- Turn it off (saves one LLM call per question): `BI_ENABLE_ROUTER=0` in `.env`.

## Evaluation
`eval/` scores the analyst on two suites (v1: 72 questions on the demo DB; v2: 59 harder questions on a 13-table SaaS DB, `init-demo --saas`) with reference SQL (execution accuracy, first-attempt accuracy,
self-correction lift, refusal accuracy, latency, tokens). Start with `python -m eval.run --smoke`, then
`python -m eval.run --name baseline --sleep 2`. Full guide: `eval/README.md`.

## Other behaviours
- **CANNOT_ANSWER:** if the schema has no column or table for the question (for example "average customer
  age"), the SQL writer replies `CANNOT_ANSWER: <reason>` instead of guessing. The run ends immediately with
  `status: unanswerable` and the reason in `error`.
- **Usage accounting:** every result has `usage` (`total` and `by_agent`: calls, input/output tokens, seconds).
  The CLI prints a summary line.
- **`BI_MAX_TOKENS`** (default 4096): maximum tokens per LLM answer. Reasoning models need room to think; raise
  it if answers come back empty or cut off.
