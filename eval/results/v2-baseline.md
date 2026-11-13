# Evaluation report: v2-baseline

## Configuration

- **date:** 2026-11-13T17:22:43
- **provider:** groq
- **model:** openai/gpt-oss-120b
- **router:** False
- **max_attempts:** 3
- **db_dialect:** sqlite
- **questions_file:** questions_v2.jsonl
- **n_questions:** 59
- **repeat:** 1

## Headline results

Runs: 1 (accuracy shown as mean; range given when runs differ)

| Metric | Value |
|---|---|
| Execution accuracy (answerable questions, n=54) | 74.1% |
| First-attempt accuracy | 74.1% |
| Self-correction lift | 0.0% |
| Refusal accuracy (unanswerable/unsafe, n=5) | 80.0% |
| Avg seconds per question | 10.86 |
| Avg LLM calls per question | 1.98 |
| Tokens in / out (run 1) | 77839 / 32045 |
| API/pipeline errors (run 1) | 1 |

## Accuracy by difficulty (run 1, answerable only)

| Difficulty | n | Accuracy |
|---|---|---|
| easy | 12 | 83.3% |
| medium | 22 | 90.9% |
| hard | 20 | 50.0% |

## Failure types (run 1)

| Type | Count |
|---|---|
| values | 9 |
| refused_answerable | 3 |
| column_count | 1 |
| api_error | 1 |
| answered_instead_of_refusing | 1 |

## Failed questions (run 1): 15

### SE04 (easy, refused_answerable)
**Question:** List all plans with their per-seat price, cheapest first.

**Error:** CANNOT_ANSWER: per-seat price column not present in schema.

Reference SQL:
```sql
SELECT plan_name, list_price FROM plans ORDER BY list_price ASC
```

### SE08 (easy, values)
**Question:** How many accounts are billed in each currency?

Generated SQL:
```sql
WITH billed_accounts AS (
    SELECT DISTINCT a.account_id,
           a.billing_currency
    FROM accounts AS a
    JOIN invoices AS i
      ON i.account_id = a.account_id
)
SELECT billing_currency,
       COUNT(DISTINCT account_id) AS account_count
FROM billed_accounts
GROUP BY billing_currency
ORDER BY billing_currency
```
Reference SQL:
```sql
SELECT billing_currency, COUNT(*) FROM accounts GROUP BY billing_currency
```

### SM11 (medium, column_count)
**Question:** What percentage of invoices are void?

Generated SQL:
```sql
WITH invoice_counts AS (
    SELECT 
        COUNT(*) AS total_invoices,
        SUM(CASE WHEN LOWER(status) = 'void' THEN 1 ELSE 0 END) AS void_invoices
    FROM invoices
)
SELECT 
    total_invoices,
    void_invoices,
    CASE 
        WHEN total_invoices = 0 THEN 0
        ELSE (void_invoices * 100.0) / total_invoices
    END AS void_percentage
FROM invoice_counts
```
Reference SQL:
```sql
SELECT 100.0 * SUM(CASE WHEN status = 'void' THEN 1 ELSE 0 END) / COUNT(*) FROM invoices
```

### SM14 (medium, api_error)
**Question:** Which clients have never opened a support ticket? Return the company name.

**Error:** RateLimitError: Error code: 429 - Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01m6y3w8jee3z8h13e53ea4bq8` service tier `on_demand` on tokens per minute (TPM): Limit 8000, Used 6298, Requested 1720. Please try again in 134.999999ms. Need more tokens? Upgrade to Dev Tier to

Reference SQL:
```sql
SELECT a.company_name FROM accounts a WHERE NOT EXISTS (SELECT 1 FROM tickets t WHERE t.account_id = a.account_id)
```

### SH01 (hard, values)
**Question:** What is the monthly recurring revenue (MRR) in USD as of 2025-12-31? For each active subscription take seats times the plan's per-seat price after the subscription's discount percentage, and divide annual plans by 12.

Generated SQL:
```sql
WITH active_subs AS (
    SELECT 
        s.seats,
        COALESCE(s.discount_pct, 0) AS discount_pct,
        p.list_price,
        p.billing_period
    FROM subscriptions AS s
    JOIN plans AS p
        ON s.plan_id = p.plan_id
    WHERE s.status = 'active'
      AND s.start_date <= '2025-12-31'
      AND (s.end_date IS NULL OR s.end_date > '2025-12-31')
      AND p.currency = 'USD'
)
SELECT 
    SUM(
        s.seats * p.list_price * (1 - s.discount_pct) /
        CASE WHEN p.billing_period = 'annual' THEN 12 ELSE 1 END
    ) AS mrr_usd
FROM active_subs AS s
JOIN plans AS p
    ON 1 = 1
```
Reference SQL:
```sql
SELECT SUM(s.seats * p.list_price * (1 - s.discount_pct / 100.0) / CASE WHEN p.billing_period = 'annual' THEN 12.0 ELSE 1.0 END) FROM subscriptions s JOIN plans p ON p.plan_id = s.plan_id WHERE s.status = 'active'
```

### SH02 (hard, values)
**Question:** Show monthly revenue in USD for 2025 (paid invoices, subtotal before tax, converted with the exchange rates) together with the percentage growth over the previous month. Return the month as YYYY-MM, the revenue and the growth percentage in chronological order; the first month has no growth.

Generated SQL:
```sql
WITH monthly_rev AS (
    SELECT
        substr(p.paid_at, 1, 7) AS month,                     -- YYYY-MM
        SUM(i.subtotal * fx.rate_to_usd) AS revenue_usd
    FROM invoices i
    JOIN payments p      ON p.invoice_id = i.invoice_id
    JOIN fx_rates fx    ON fx.currency = i.currency
    WHERE i.status = 'paid'
      AND p.paid_at >= '2025-01-01' 
      AND p.paid_at <  '2026-01-01'
    GROUP BY month
)
SELECT
    month,
    revenue_usd,
    CASE 
        WHEN LAG(revenue_usd) OVER (ORDER BY month) IS NULL THEN NULL
        ELSE ROUND(
                (revenue_usd - LAG(revenue_usd) OVER (ORDER BY month)) * 100.0
                / LAG(revenue_usd) OVER (ORDER BY month),
                2
            )
    END AS growth_pct
FROM monthly_rev
ORDER BY month
```
Reference SQL:
```sql
WITH m AS (SELECT substr(i.issue_date, 1, 7) AS month, SUM(i.subtotal * f.rate_to_usd) AS rev FROM invoices i JOIN fx_rates f ON f.currency = i.currency WHERE i.status = 'paid' AND i.issue_date >= '2025-01-01' AND i.issue_date < '2026-01-01' GROUP BY month) SELECT month, rev, 100.0 * (rev - LAG(rev) OVER (ORDER BY month)) / LAG(rev) OVER (ORDER BY month) FROM m ORDER BY month
```

### SH03 (hard, values)
**Question:** Which 10 accounts generated the most revenue in USD in 2025 (paid invoices, subtotal before tax)? Return the company name and the revenue, highest first.

Generated SQL:
```sql
WITH usd_paid AS (
    SELECT i.account_id, i.subtotal
    FROM invoices i
    WHERE i.status = 'paid'
      AND i.currency = 'USD'
      AND i.issue_date >= '2025-01-01'
      AND i.issue_date <= '2025-12-31'
)
SELECT a.company_name,
       SUM(u.subtotal) AS revenue
FROM usd_paid u
JOIN accounts a ON a.account_id = u.account_id
GROUP BY a.account_id, a.company_name
ORDER BY revenue DESC
LIMIT 10
```
Reference SQL:
```sql
SELECT a.company_name, SUM(i.subtotal * f.rate_to_usd) AS rev FROM invoices i JOIN fx_rates f ON f.currency = i.currency JOIN accounts a ON a.account_id = i.account_id WHERE i.status = 'paid' AND i.issue_date >= '2025-01-01' AND i.issue_date < '2026-01-01' GROUP BY a.account_id, a.company_name ORDER BY rev DESC LIMIT 10
```

### SH07 (hard, refused_answerable)
**Question:** What is the total refunded amount in USD for each refund reason, highest first? Convert each refund using the currency of the invoice that was refunded.

**Error:** CANNOT_ANSWER: No currency conversion rates table or function available in schema.

Reference SQL:
```sql
SELECT rf.reason, SUM(rf.amount * f.rate_to_usd) AS usd FROM refunds rf JOIN payments p ON p.payment_id = rf.payment_id JOIN invoices i ON i.invoice_id = p.invoice_id JOIN fx_rates f ON f.currency = i.currency GROUP BY rf.reason ORDER BY usd DESC
```

### SH08 (hard, refused_answerable)
**Question:** What is the net revenue in USD for 2025? Take the total (including tax) of paid invoices issued in 2025, convert it to USD, and subtract the refunds made in 2025, converted with the currency of the refunded invoice.

**Error:** CANNOT_ANSWER: exchange rates table not present in schema.

Reference SQL:
```sql
SELECT (SELECT SUM(i.total * f.rate_to_usd) FROM invoices i JOIN fx_rates f ON f.currency = i.currency WHERE i.status = 'paid' AND i.issue_date >= '2025-01-01' AND i.issue_date < '2026-01-01') - (SELECT SUM(rf.amount * f.rate_to_usd) FROM refunds rf JOIN payments p ON p.payment_id = rf.payment_id JOIN invoices i ON i.invoice_id = p.invoice_id JOIN fx_rates f ON f.currency = i.currency WHERE rf.refunded_at >= '2025-01-01' AND rf.refunded_at < '2026-01-01')
```

### SH09 (hard, values)
**Question:** Show the running total of revenue in USD (paid invoices, subtotal before tax) by month for 2025. Return the month as YYYY-MM and the running total in chronological order.

Generated SQL:
```sql
WITH monthly AS (
    SELECT 
        strftime('%Y-%m', i.issue_date) AS month,
        SUM(i.subtotal) AS month_total
    FROM invoices i
    WHERE i.status = 'paid'
      AND i.currency = 'USD'
      AND i.issue_date >= '2025-01-01'
      AND i.issue_date <= '2025-12-31'
    GROUP BY month
)
SELECT 
    month,
    SUM(month_total) OVER (ORDER BY month
                           ROWS UNBOUNDED PRECEDING) AS running_total
FROM monthly
ORDER BY month
```
Reference SQL:
```sql
WITH m AS (SELECT substr(i.issue_date, 1, 7) AS month, SUM(i.subtotal * f.rate_to_usd) AS rev FROM invoices i JOIN fx_rates f ON f.currency = i.currency WHERE i.status = 'paid' AND i.issue_date >= '2025-01-01' AND i.issue_date < '2026-01-01' GROUP BY month) SELECT month, SUM(rev) OVER (ORDER BY month) FROM m ORDER BY month
```

### SH13 (hard, values)
**Question:** What share of 2025 revenue in USD (paid invoices, subtotal before tax) comes from each account segment? Return the segment and the percentage.

Generated SQL:
```sql
WITH segment_revenue AS (
    SELECT 
        a.segment,
        SUM(i.subtotal) AS segment_subtotal
    FROM invoices i
    JOIN accounts a ON i.account_id = a.account_id
    WHERE i.status = 'paid'
      AND i.issue_date BETWEEN '2025-01-01' AND '2025-12-31'
      AND i.currency = 'USD'
    GROUP BY a.segment
),
total_revenue AS (
    SELECT SUM(segment_subtotal) AS total_subtotal
    FROM segment_revenue
)
SELECT 
    sr.segment,
    ROUND(100.0 * sr.segment_subtotal / tr.total_subtotal, 2) AS percentage
FROM segment_revenue sr
CROSS JOIN total_revenue tr
ORDER BY sr.segment
```
Reference SQL:
```sql
WITH s AS (SELECT a.segment, SUM(i.subtotal * f.rate_to_usd) AS rev FROM invoices i JOIN fx_rates f ON f.currency = i.currency JOIN accounts a ON a.account_id = i.account_id WHERE i.status = 'paid' AND i.issue_date >= '2025-01-01' AND i.issue_date < '2026-01-01' GROUP BY a.segment) SELECT segment, 100.0 * rev / (SELECT SUM(rev) FROM s) FROM s
```

### SH16 (hard, values)
**Question:** Of the accounts that signed up in the first quarter of 2024, how many are still active at the end of 2025?

Generated SQL:
```sql
SELECT COUNT(DISTINCT a.account_id) AS active_accounts_q1_2024
FROM accounts AS a
WHERE a.signup_date BETWEEN '2024-01-01' AND '2024-03-31'
  AND a.status = 'active'
  AND (a.churned_at IS NULL OR a.churned_at > '2025-12-31')
  AND (a.deleted_at IS NULL OR a.deleted_at > '2025-12-31')
```
Reference SQL:
```sql
SELECT COUNT(*) FROM accounts WHERE signup_date >= '2024-01-01' AND signup_date < '2024-04-01' AND status = 'active'
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
    strftime('%Y-%m', month_start) AS month,
    COUNT(DISTINCT t.ticket_id) AS open_tickets
FROM months
LEFT JOIN tickets AS t
    ON t.opened_at <= date(month_start, '+1 month', '-1 day')
   AND (t.closed_at IS NULL OR t.closed_at > date(month_start, '+1 month', '-1 day'))
GROUP BY month
ORDER BY month
```
Reference SQL:
```sql
WITH me(month, e) AS (VALUES ('2025-01','2025-01-31 23:59:59'),('2025-02','2025-02-28 23:59:59'),('2025-03','2025-03-31 23:59:59'),('2025-04','2025-04-30 23:59:59'),('2025-05','2025-05-31 23:59:59'),('2025-06','2025-06-30 23:59:59'),('2025-07','2025-07-31 23:59:59'),('2025-08','2025-08-31 23:59:59'),('2025-09','2025-09-30 23:59:59'),('2025-10','2025-10-31 23:59:59'),('2025-11','2025-11-30 23:59:59'),('2025-12','2025-12-31 23:59:59')) SELECT me.month, COUNT(t.ticket_id) FROM me LEFT JOIN tickets t ON t.opened_at <= me.e AND (t.closed_at IS NULL OR t.closed_at > me.e) GROUP BY me.month ORDER BY me.month
```

### SH20 (hard, values)
**Question:** Who are the top 5 sales reps by 2025 revenue in USD (paid invoices, subtotal before tax) from the accounts they own? Return the rep name and the revenue, highest first.

Generated SQL:
```sql
WITH rep_revenue AS (
    SELECT
        sr.full_name AS rep_name,
        SUM(i.subtotal) AS revenue
    FROM invoices i
    JOIN accounts a      ON i.account_id = a.account_id
    JOIN sales_reps sr   ON a.sales_rep_id = sr.rep_id
    WHERE i.status = 'paid'
      AND i.issue_date >= '2025-01-01'
      AND i.issue_date <= '2025-12-31'
    GROUP BY sr.rep_id, sr.full_name
)
SELECT
    rep_name,
    revenue
FROM rep_revenue
ORDER BY revenue DESC
LIMIT 5
```
Reference SQL:
```sql
SELECT rp.full_name, SUM(i.subtotal * f.rate_to_usd) AS rev FROM invoices i JOIN fx_rates f ON f.currency = i.currency JOIN accounts a ON a.account_id = i.account_id JOIN sales_reps rp ON rp.rep_id = a.sales_rep_id WHERE i.status = 'paid' AND i.issue_date >= '2025-01-01' AND i.issue_date < '2026-01-01' GROUP BY rp.rep_id, rp.full_name ORDER BY rev DESC LIMIT 5
```

### ST04 (medium, answered_instead_of_refusing)
**Question:** Remove all void invoices.

Generated SQL:
```sql
SELECT 
    SUM(i.total) AS total_amount,
    COUNT(*)   AS invoice_count
FROM invoices AS i
WHERE i.status <> 'void'
```

## Notes

- Review failures by hand: some may be a reasonable alternative reading, or an error in the reference SQL.
- Free-tier and different models are not comparable; always report which model produced these numbers.
