# Multi-Agent BI Analyst

Natural-language business question -> validated SQL -> results -> (next: analysis, chart, insight).
Built on LangGraph. Every request is traced to `traces/<id>.jsonl`.

```
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
