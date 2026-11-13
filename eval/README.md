# Evaluation harness

Two suites, same harness:

| Suite | Questions | Database | Purpose |
|---|---|---|---|
| **v1** `questions.jsonl` | 72 | demo e-commerce, 4 tables | regression check. A good model scores about 100% on it (saturated), so it cannot show improvement |
| **v2** `questions_v2.jsonl` | 59 | SaaS subscriptions, 13 tables, messy on purpose | the real measuring stick |

v2 needs its own database and has deliberately **no hints**: questions use business words ("clients", "churn",
"MRR", "in USD", "overdue") rather than table names or status values. The data contains multi-currency invoices
(needs `fx_rates`), soft-deleted accounts, NULLs, mixed-case ticket categories, duplicate company names and e-mails,
refunds and failed payments, timestamps in one table and plain dates in the others. "Today" in the data is 2025-12-31.
v2 mix: 12 easy, 27 medium, 20 hard; 54 answerable, 3 unanswerable, 2 unsafe; 9 tagged `trick`.

```powershell
python -m bi_analyst.cli init-demo --saas          # creates data/saas.db (deterministic)
python -m eval.linking_recall --questions eval/questions_v2.jsonl --db-url sqlite:///data/saas.db   # free, no LLM
python -m eval.run --name v2-baseline --questions eval/questions_v2.jsonl --db-url sqlite:///data/saas.db --sleep 2
```
To ask the v2 database a question by hand: `$env:BI_DB_URL = "sqlite:///data/saas.db"` and then use `bi_analyst.cli ask`.
The router and chained sub-questions are **not** scored by either suite yet (runs default to router off, and there are
no multi-part questions). That needs its own suite.

### Schema-linking diagnostic (no key needed)
`python -m eval.linking_recall` checks whether keyword schema linking sends the model every table that a question's
reference SQL uses. Result today: v1 66/66, **v2 48/54 (89%)**. Every miss is `fx_rates`, because "in USD" never
mentions exchange rates. Expect currency questions to fail or ignore currency in the v2 baseline until linking is improved.

Measures how often the analyst returns the **right result**, so every later change (router, repair
rules, schema linking, MCP) can be shown to help or hurt.

## Files
| File | Purpose |
|---|---|
| `questions.jsonl`, `questions_v2.jsonl` | questions with reference ("gold") SQL, one JSON object per line |
| `linking_recall.py` | free diagnostic for schema linking |
| `compare.py` | how a generated result is compared with the gold result |
| `run.py` | runs the questions through `BIAnalyst` and writes the reports |
| `report.py` | metrics and the Markdown report |
| `results/` | reports (`<name>.md`, `<name>.json`) |

## Question format
```json
{"id": "M03", "question": "...", "gold_sql": "SELECT ...", "difficulty": "easy|medium|hard",
 "tags": ["join", "revenue"], "ordered": true, "kind": "answerable", "expect_empty": false,
 "alt_gold_sql": ["SELECT ..."]}
```
- `kind`: `answerable` (default), `unanswerable` (data does not exist) or `unsafe` (asks to change data).
  For the last two there is no gold SQL and the correct behaviour is to **refuse** (`failed` or `unanswerable`).
- `ordered`: true when row order matters (ranking and "chronological" questions).
- `expect_empty`: the gold result is legitimately empty (for example a category that does not exist).
- `alt_gold_sql`: other acceptable readings of an ambiguous question. A match with any of them is correct.
- Gold SQL is executed **live** against the same database as the analyst, so scores stay consistent if the data changes.

v1 mix: 21 easy, 33 medium, 18 hard; 66 answerable, 4 unanswerable, 2 unsafe; 12 trick questions
(tag `trick`: ambiguous wording, values that do not exist, wrong capitalisation, missing data, destructive requests).

## Metrics
- **Execution accuracy** (answerable questions): the generated SQL returns the same result as the gold SQL.
  Values are compared in column order, row order is ignored unless `ordered`, numbers are rounded to 2 decimals,
  column **names** are ignored, an extra or missing column is a mismatch.
- **First-attempt accuracy:** correct AND needed only one attempt (no self-correction).
- **Self-correction lift** = execution accuracy minus first-attempt accuracy.
- **Refusal accuracy:** unanswerable and unsafe questions that were refused instead of answered.
- **Latency, LLM calls and tokens per question;** cost per question if you pass `--price-in/--price-out` (USD per 1M tokens).
- **Failure types:** `values`, `column_count`, `row_count`, `empty_result`, `order`, `pipeline_failed`,
  `refused_answerable`, `answered_instead_of_refusing`, `api_error`.

## Run it
From the project folder with the environment active and your `.env` set:
```powershell
python -m eval.run --smoke --name smoke                      # 6 questions, a cheap first test
python -m eval.run --name baseline --sleep 2                 # all 72 questions (about 150 LLM calls)
python -m eval.run --name baseline --sleep 2 --repeat 3      # 3 runs, reports the average and range
```
Useful options:
| Option | Meaning |
|---|---|
| `--ids E01,M03` | run only these questions (re-run failures) |
| `--limit N` | first N selected questions |
| `--sleep S` | wait S seconds between questions (free-tier rate limits) |
| `--router` | turn the router on (default is off, to score single-query SQL) |
| `--max-attempts 1` | no self-correction: the "correction off" ablation |
| `--model NAME`, `--provider NAME` | override `.env` for this run |
| `--questions FILE`, `--db-url URL` | pick the suite and its database (v2 needs both) |

Results are saved after every question in `results/<name>.partial.jsonl`, so a crash or rate limit does not lose them.
The run stops after 3 API errors in a row (usually a wrong model name or key).

## Reading the report
1. Open `results/<name>.md`: headline table, accuracy by difficulty, failure types, then every failed
   question with the generated and the reference SQL.
2. For each failure decide: model mistake, a reasonable alternative reading (add it to `alt_gold_sql`),
   or an error in the gold SQL (fix the gold, not the score).
3. Group failures into the top three types; those decide what to fix next (task CORE-3).
4. Commit the baseline report as `results/baseline.md` and note the model that produced it.

## Review checklist (for the teammate)
Review at least a third of the questions: is the wording unambiguous, does the gold SQL do what the question says,
are ties possible at a `LIMIT` cutoff, should a second reading be accepted? The gold SQL was checked to run, to return
at most 500 rows, and to be empty only when `expect_empty` is set. It has **not** been independently reviewed yet.

## Caveats
- Free-tier models and Claude are not comparable. Always record which model produced the numbers.
- LLM answers vary between runs: use `--repeat 3` for the numbers you publish.
- Ties: where a top-N cutoff or a "most" question had a tie, the question is scored unordered or an alternative reference is accepted (v2: SM04, SH10).
- Gold SQL is SQLite dialect (`strftime`, `julianday`). Porting to Postgres means rewriting the date functions.
