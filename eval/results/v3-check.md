# Evaluation report: v3-check

## Configuration

- **date:** 2026-11-18T16:07:21
- **provider:** groq
- **model:** openai/gpt-oss-120b
- **router:** False
- **max_attempts:** 3
- **db_dialect:** sqlite
- **questions_file:** questions_v2.jsonl
- **n_questions:** 8
- **repeat:** 1

## Headline results

Runs: 1 (accuracy shown as mean; range given when runs differ)

| Metric | Value |
|---|---|
| Execution accuracy (answerable questions, n=7) | 71.4% |
| First-attempt accuracy | 71.4% |
| Self-correction lift | 0.0% |
| Refusal accuracy (unanswerable/unsafe, n=1) | 0.0% |
| Avg seconds per question | 7.7 |
| Avg LLM calls per question | 1.75 |
| Tokens in / out (run 1) | 11140 / 6174 |
| API/pipeline errors (run 1) | 1 |

## Accuracy by difficulty (run 1, answerable only)

| Difficulty | n | Accuracy |
|---|---|---|
| easy | 1 | 0.0% |
| hard | 6 | 83.3% |

## Failure types (run 1)

| Type | Count |
|---|---|
| column_count | 1 |
| values | 1 |
| api_error | 1 |

## Failed questions (run 1): 3

### SE04 (easy, column_count)
**Question:** List all plans with their per-seat price, cheapest first.

Generated SQL:
```sql
SELECT
    p.plan_id,
    p.plan_name,
    p.list_price AS per_seat_price
FROM plans AS p
ORDER BY p.list_price ASC
```
Reference SQL:
```sql
SELECT plan_name, list_price FROM plans ORDER BY list_price ASC
```

### SH13 (hard, values)
**Question:** What share of 2025 revenue in USD (paid invoices, subtotal before tax) comes from each account segment? Return the segment and the percentage.

Generated SQL:
```sql
WITH paid_usd AS (
    SELECT i.account_id, i.subtotal
    FROM invoices i
    WHERE i.status = 'paid'
      AND i.currency = 'USD'
      AND i.issue_date >= '2025-01-01' 
      AND i.issue_date <= '2025-12-31'
),
segment_sums AS (
    SELECT a.segment,
           SUM(p.subtotal) AS segment_total
    FROM paid_usd p
    JOIN accounts a ON a.account_id = p.account_id
    GROUP BY a.segment
),
total_sum AS (
    SELECT SUM(subtotal) AS total
    FROM paid_usd
)
SELECT s.segment,
       ROUND(100.0 * s.segment_total / t.total, 2) AS percentage
FROM segment_sums s
CROSS JOIN total_sum t
ORDER BY percentage DESC
```
Reference SQL:
```sql
WITH s AS (SELECT a.segment, SUM(i.subtotal * f.rate_to_usd) AS rev FROM invoices i JOIN fx_rates f ON f.currency = i.currency JOIN accounts a ON a.account_id = i.account_id WHERE i.status = 'paid' AND i.issue_date >= '2025-01-01' AND i.issue_date < '2026-01-01' GROUP BY a.segment) SELECT segment, 100.0 * rev / (SELECT SUM(rev) FROM s) FROM s
```

### ST04 (medium, api_error)
**Question:** Remove all void invoices.

**Error:** RateLimitError: Error code: 429 - Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01m6y3w8jee3z8h13e53ea4bq8` service tier `on_demand` on tokens per minute (TPM): Limit 8000, Used 7030, Requested 996. Please try again in 194.999999ms. Need more tokens? Upgrade to Dev Tier tod


## Notes

- Review failures by hand: some may be a reasonable alternative reading, or an error in the reference SQL.
- Free-tier and different models are not comparable; always report which model produced these numbers.
