# Evaluation report: v4-check

## Configuration

- **date:** 2026-11-21T14:41:16
- **provider:** groq
- **model:** openai/gpt-oss-120b
- **router:** False
- **max_attempts:** 3
- **db_dialect:** sqlite
- **questions_file:** questions_v2.jsonl
- **n_questions:** 4
- **repeat:** 1

## Headline results

Runs: 1 (accuracy shown as mean; range given when runs differ)

| Metric | Value |
|---|---|
| Execution accuracy (answerable questions, n=4) | 25.0% |
| First-attempt accuracy | 25.0% |
| Self-correction lift | 0.0% |
| Refusal accuracy (unanswerable/unsafe, n=0) | n/a |
| Avg seconds per question | 3.0 |
| Avg LLM calls per question | 2 |
| Tokens in / out (run 1) | 6258 / 3776 |
| API/pipeline errors (run 1) | 0 |

## Accuracy by difficulty (run 1, answerable only)

| Difficulty | n | Accuracy |
|---|---|---|
| easy | 1 | 0.0% |
| hard | 3 | 33.3% |

## Failure types (run 1)

| Type | Count |
|---|---|
| values | 2 |
| column_count | 1 |

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

### SH01 (hard, values)
**Question:** What is the monthly recurring revenue (MRR) in USD as of 2025-12-31? For each active subscription take seats times the plan's per-seat price after the subscription's discount percentage, and divide annual plans by 12.

Generated SQL:
```sql
SELECT 
    ROUND(SUM(
        s.seats * p.list_price * (1 - s.discount_pct) *
        CASE WHEN p.billing_period = 'annual' THEN 1.0/12 ELSE 1 END
    ), 2) AS mrr_usd
FROM subscriptions AS s
JOIN plans AS p
    ON s.plan_id = p.plan_id
WHERE s.status = 'active'
  AND s.start_date <= '2025-12-31'
  AND (s.end_date IS NULL OR s.end_date > '2025-12-31')
```
Reference SQL:
```sql
SELECT SUM(s.seats * p.list_price * (1 - s.discount_pct / 100.0) / CASE WHEN p.billing_period = 'annual' THEN 12.0 ELSE 1.0 END) FROM subscriptions s JOIN plans p ON p.plan_id = s.plan_id WHERE s.status = 'active'
```

### SH17 (hard, values)
**Question:** For each month-end of 2025, how many tickets were still open, meaning opened on or before that month-end and not closed by then? Return the month as YYYY-MM and the count in chronological order.

Generated SQL:
```sql
WITH RECURSIVE months AS (
    SELECT date('2025-01-01') AS month_start
    UNION ALL
    SELECT date(month_start, '+1 month')
    FROM months
    WHERE month_start < '2025-12-01'
)
SELECT 
    strftime('%Y-%m', date(month_start, '+1 month', '-1 day')) AS month,
    COUNT(t.ticket_id) AS open_tickets
FROM months
LEFT JOIN tickets t
    ON t.opened_at <= date(month_start, '+1 month', '-1 day')
   AND (t.closed_at IS NULL OR t.closed_at > date(month_start, '+1 month', '-1 day'))
GROUP BY month
ORDER BY month
```
Reference SQL:
```sql
WITH me(month, e) AS (VALUES ('2025-01','2025-01-31 23:59:59'),('2025-02','2025-02-28 23:59:59'),('2025-03','2025-03-31 23:59:59'),('2025-04','2025-04-30 23:59:59'),('2025-05','2025-05-31 23:59:59'),('2025-06','2025-06-30 23:59:59'),('2025-07','2025-07-31 23:59:59'),('2025-08','2025-08-31 23:59:59'),('2025-09','2025-09-30 23:59:59'),('2025-10','2025-10-31 23:59:59'),('2025-11','2025-11-30 23:59:59'),('2025-12','2025-12-31 23:59:59')) SELECT me.month, COUNT(t.ticket_id) FROM me LEFT JOIN tickets t ON t.opened_at <= me.e AND (t.closed_at IS NULL OR t.closed_at > me.e) GROUP BY me.month ORDER BY me.month
```

## Notes

- Review failures by hand: some may be a reasonable alternative reading, or an error in the reference SQL.
- Free-tier and different models are not comparable; always report which model produced these numbers.
