"""Builds a small, deterministic e-commerce database for demos and tests."""
from __future__ import annotations

import datetime as dt
import random
import sqlite3
from pathlib import Path

REGIONS = ["North America", "Europe", "Asia", "South America"]
CATEGORIES = {"Electronics": (50, 900), "Home": (10, 300), "Books": (5, 40), "Clothing": (15, 150)}


def create_demo_db(path: str = "data/demo.db", seed: int = 7) -> str:
    rnd = random.Random(seed)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).unlink(missing_ok=True)
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE customers (
            customer_id INTEGER PRIMARY KEY, name TEXT, region TEXT, signup_date TEXT);
        CREATE TABLE products (
            product_id INTEGER PRIMARY KEY, name TEXT, category TEXT, unit_price REAL);
        CREATE TABLE orders (
            order_id INTEGER PRIMARY KEY, customer_id INTEGER, order_date TEXT, status TEXT,
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id));
        CREATE TABLE order_items (
            item_id INTEGER PRIMARY KEY, order_id INTEGER, product_id INTEGER,
            quantity INTEGER, unit_price REAL,
            FOREIGN KEY (order_id) REFERENCES orders(order_id),
            FOREIGN KEY (product_id) REFERENCES products(product_id));
        """
    )
    for i in range(1, 201):
        d = dt.date(2023, 1, 1) + dt.timedelta(days=rnd.randint(0, 700))
        con.execute("INSERT INTO customers VALUES (?,?,?,?)", (i, f"Customer {i}", rnd.choice(REGIONS), d.isoformat()))
    pid = 0
    for cat, (lo, hi) in CATEGORIES.items():
        for n in range(1, 9):
            pid += 1
            con.execute("INSERT INTO products VALUES (?,?,?,?)",
                        (pid, f"{cat} Item {n}", cat, round(rnd.uniform(lo, hi), 2)))
    item_id = 0
    for oid in range(1, 1501):
        d = dt.date(2024, 1, 1) + dt.timedelta(days=rnd.randint(0, 600))
        status = rnd.choices(["completed", "cancelled", "refunded"], [85, 8, 7])[0]
        con.execute("INSERT INTO orders VALUES (?,?,?,?)", (oid, rnd.randint(1, 200), d.isoformat(), status))
        for _ in range(rnd.randint(1, 4)):
            item_id += 1
            p = rnd.randint(1, pid)
            price = con.execute("SELECT unit_price FROM products WHERE product_id=?", (p,)).fetchone()[0]
            con.execute("INSERT INTO order_items VALUES (?,?,?,?,?)", (item_id, oid, p, rnd.randint(1, 5), price))
    con.commit()
    con.close()
    return path


# =====================================================================================
# Harder suite: a SaaS subscription business (13 tables, messy on purpose).
# Messiness: multi-currency invoices (need fx_rates), soft-deleted accounts, NULLs
# (csat, closed_at, industry, end_date), mixed-case ticket categories, duplicate company
# names and contact e-mails, timestamps in one table vs dates elsewhere, a second
# subscription after an upgrade. "Today" for the data is 2025-12-31.
# =====================================================================================
def _add_months(d: dt.date, n: int) -> dt.date:
    m = d.month - 1 + n
    return dt.date(d.year + m // 12, m % 12 + 1, min(d.day, 28))


def create_saas_db(path: str = "data/saas.db", seed: int = 11) -> str:
    rnd = random.Random(seed)
    END = dt.date(2025, 12, 31)
    day = dt.timedelta
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).unlink(missing_ok=True)
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE regions (region_id INTEGER PRIMARY KEY, name TEXT, country_group TEXT);
        CREATE TABLE sales_reps (rep_id INTEGER PRIMARY KEY, full_name TEXT, team TEXT, hire_date TEXT,
            manager_id INTEGER, FOREIGN KEY (manager_id) REFERENCES sales_reps(rep_id));
        CREATE TABLE plans (plan_id INTEGER PRIMARY KEY, plan_name TEXT, tier TEXT, billing_period TEXT,
            list_price REAL, currency TEXT);
        CREATE TABLE fx_rates (currency TEXT PRIMARY KEY, rate_to_usd REAL);
        CREATE TABLE accounts (account_id INTEGER PRIMARY KEY, company_name TEXT, region_id INTEGER,
            industry TEXT, segment TEXT, status TEXT, signup_date TEXT, churned_at TEXT, deleted_at TEXT,
            sales_rep_id INTEGER, billing_currency TEXT,
            FOREIGN KEY (region_id) REFERENCES regions(region_id),
            FOREIGN KEY (sales_rep_id) REFERENCES sales_reps(rep_id));
        CREATE TABLE contacts (contact_id INTEGER PRIMARY KEY, account_id INTEGER, full_name TEXT, email TEXT,
            is_primary INTEGER, created_at TEXT, FOREIGN KEY (account_id) REFERENCES accounts(account_id));
        CREATE TABLE subscriptions (subscription_id INTEGER PRIMARY KEY, account_id INTEGER, plan_id INTEGER,
            start_date TEXT, end_date TEXT, status TEXT, seats INTEGER, discount_pct REAL,
            FOREIGN KEY (account_id) REFERENCES accounts(account_id), FOREIGN KEY (plan_id) REFERENCES plans(plan_id));
        CREATE TABLE invoices (invoice_id INTEGER PRIMARY KEY, subscription_id INTEGER, account_id INTEGER,
            issue_date TEXT, due_date TEXT, subtotal REAL, tax REAL, total REAL, currency TEXT, status TEXT,
            FOREIGN KEY (subscription_id) REFERENCES subscriptions(subscription_id),
            FOREIGN KEY (account_id) REFERENCES accounts(account_id));
        CREATE TABLE invoice_items (item_id INTEGER PRIMARY KEY, invoice_id INTEGER, description TEXT,
            quantity INTEGER, unit_price REAL, FOREIGN KEY (invoice_id) REFERENCES invoices(invoice_id));
        CREATE TABLE payments (payment_id INTEGER PRIMARY KEY, invoice_id INTEGER, paid_at TEXT, amount REAL,
            method TEXT, status TEXT, FOREIGN KEY (invoice_id) REFERENCES invoices(invoice_id));
        CREATE TABLE refunds (refund_id INTEGER PRIMARY KEY, payment_id INTEGER, refunded_at TEXT, amount REAL,
            reason TEXT, FOREIGN KEY (payment_id) REFERENCES payments(payment_id));
        CREATE TABLE tickets (ticket_id INTEGER PRIMARY KEY, account_id INTEGER, opened_at TEXT, closed_at TEXT,
            priority TEXT, category TEXT, csat_score INTEGER, FOREIGN KEY (account_id) REFERENCES accounts(account_id));
        CREATE TABLE usage_events (event_id INTEGER PRIMARY KEY, account_id INTEGER, event_date TEXT,
            feature TEXT, units INTEGER, FOREIGN KEY (account_id) REFERENCES accounts(account_id));
        """
    )
    regions = [(1, "North America", "AMER"), (2, "Latin America", "AMER"), (3, "Europe", "EMEA"),
               (4, "Middle East and Africa", "EMEA"), (5, "Asia Pacific", "APAC")]
    con.executemany("INSERT INTO regions VALUES (?,?,?)", regions)
    teams = ["Inbound", "Outbound", "Enterprise"]
    for i in range(1, 13):
        hire = dt.date(2019, 1, 1) + day(days=rnd.randint(0, 2000))
        con.execute("INSERT INTO sales_reps VALUES (?,?,?,?,?)",
                    (i, f"Rep {i:02d}", teams[(i - 1) % 3], hire.isoformat(), None if i <= 3 else ((i - 4) % 3) + 1))
    plans = [(1, "Starter Monthly", "Starter", "monthly", 9.0), (2, "Starter Annual", "Starter", "annual", 90.0),
             (3, "Pro Monthly", "Pro", "monthly", 19.0), (4, "Pro Annual", "Pro", "annual", 190.0),
             (5, "Enterprise Monthly", "Enterprise", "monthly", 45.0), (6, "Enterprise Annual", "Enterprise", "annual", 450.0)]
    con.executemany("INSERT INTO plans VALUES (?,?,?,?,?,'USD')", plans)
    plan_of = {(t, p): pid for pid, _, t, p, _ in plans}
    price_of = {pid: price for pid, _, _, _, price in plans}
    fx = {"USD": 1.0, "EUR": 1.08, "GBP": 1.27}
    con.executemany("INSERT INTO fx_rates VALUES (?,?)", list(fx.items()))

    industries = ["Software", "Retail", "Finance", "Healthcare", "Education", "Logistics", "Media", "Manufacturing"]
    tiers = ["Starter"] * 45 + ["Pro"] * 35 + ["Enterprise"] * 20
    seg_of = {"Starter": "SMB", "Pro": "Mid-Market", "Enterprise": "Enterprise"}
    seat_range = {"Starter": (1, 10), "Pro": (5, 50), "Enterprise": (50, 300)}
    accounts, subs = [], []
    sub_id = 0
    dup_names = {7: "Acme Corp", 58: "Acme Corp", 101: "Acme Corp", 12: "Globex Ltd", 90: "Globex Ltd"}
    for aid in range(1, 151):
        region = rnd.choices([1, 2, 3, 4, 5], [35, 10, 30, 8, 17])[0]
        cur = {1: "USD", 2: "USD", 3: rnd.choice(["EUR", "EUR", "GBP"]), 4: rnd.choice(["USD", "EUR"]), 5: "USD"}[region]
        tier = rnd.choice(tiers)
        signup = dt.date(2024, 1, 1) + day(days=rnd.randint(0, 669))
        status = rnd.choices(["active", "churned", "trial"], [55, 33, 12])[0]
        churned_at, last_sub = None, None
        if status != "trial":
            start = signup + day(days=rnd.randint(0, 14))
            lo, hi = seat_range[tier]
            period = rnd.choices(["monthly", "annual"], [65, 35])[0]
            cur_tier, seats, disc = tier, rnd.randint(lo, hi), rnd.choice([0, 0, 10, 20])
            if rnd.random() < 0.2 and (END - start).days > 200:        # upgrade: second subscription
                first_end = start + day(days=rnd.randint(120, min(300, (END - start).days - 60)))
                sub_id += 1
                subs.append([sub_id, aid, plan_of[(cur_tier, period)], start, first_end, "cancelled", seats, disc])
                nxt = {"Starter": "Pro", "Pro": "Enterprise", "Enterprise": "Enterprise"}[cur_tier]
                cur_tier, start = nxt, first_end
                lo, hi = seat_range[cur_tier]
                seats, period = rnd.randint(lo, hi), rnd.choices(["monthly", "annual"], [65, 35])[0]
            if status == "churned" and (END - start).days < 60:
                status = "active"
            end = None
            sstatus = "active"
            if status == "churned":
                end = min(start + day(days=rnd.randint(60, 420)), END)
                sstatus, churned_at = "cancelled", end
            elif rnd.random() < 0.03:
                sstatus = "paused"
            sub_id += 1
            last_sub = [sub_id, aid, plan_of[(cur_tier, period)], start, end, sstatus, seats, disc]
            subs.append(last_sub)
        deleted = (signup + day(days=rnd.randint(30, 300))) if rnd.random() < 0.05 else None
        if deleted and deleted > END:
            deleted = None
        accounts.append((aid, dup_names.get(aid, f"Company {aid:03d}"), region, rnd.choice(industries) if rnd.random() > 0.1 else None,
                         seg_of[tier], status, signup.isoformat(), churned_at.isoformat() if churned_at else None,
                         deleted.isoformat() if deleted else None, rnd.randint(1, 12), cur))
    con.executemany("INSERT INTO accounts VALUES (?,?,?,?,?,?,?,?,?,?,?)", accounts)
    acct = {a[0]: a for a in accounts}
    live = [a[0] for a in accounts if a[5] != "trial"]

    # contacts (some people appear at two accounts -> duplicate e-mails)
    cid = 0
    shared = {}
    for aid in range(1, 151):
        for k in range(rnd.randint(1, 3)):
            cid += 1
            email = f"person{aid}.{k}@company{aid}.com"
            if aid in (20, 21, 70, 71, 120) and k == 0:
                email = f"shared.contact{aid // 20}@partner.com"
            con.execute("INSERT INTO contacts VALUES (?,?,?,?,?,?)",
                        (cid, aid, f"Contact {cid}", email, 1 if k == 0 else 0, acct[aid][6]))

    # subscriptions, invoices, items, payments, refunds
    inv_id = item_id = pay_id = ref_id = 0
    methods = ["card"] * 6 + ["wire"] * 3 + ["paypal"]
    for s in subs:
        sid, aid, pid, start, end, sstatus, seats, disc = s
        con.execute("INSERT INTO subscriptions VALUES (?,?,?,?,?,?,?,?)",
                    (sid, aid, pid, start.isoformat(), end.isoformat() if end else None, sstatus, seats, disc))
        cur = acct[aid][10]
        rate = fx[cur]
        period = "annual" if pid in (2, 4, 6) else "monthly"
        stop = end if end else END
        if sstatus == "paused":
            stop = END - day(days=60)
        n = 0
        while True:
            issue = _add_months(start, n * (12 if period == "annual" else 1))
            if issue >= stop or issue > END:
                break
            n += 1
            inv_id += 1
            items = [("Subscription seats", seats, round(price_of[pid] * (1 - disc / 100) / rate, 2))]
            if rnd.random() < 0.2:
                items.append(("Premium support", 1, round(200 / rate, 2)))
            subtotal = round(sum(round(q * u, 2) for _, q, u in items), 2)
            tax = round(subtotal * (0.2 if cur in ("EUR", "GBP") else 0.0), 2)
            if issue >= dt.date(2025, 12, 1):
                st = rnd.choice(["open", "open", "draft", "paid"])
            else:
                st = rnd.choices(["paid", "void", "open"], [88, 5, 7])[0]
            con.execute("INSERT INTO invoices VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (inv_id, sid, aid, issue.isoformat(), (issue + day(days=14)).isoformat(), subtotal, tax,
                         round(subtotal + tax, 2), cur, st))
            for desc, q, u in items:
                item_id += 1
                con.execute("INSERT INTO invoice_items VALUES (?,?,?,?,?)", (item_id, inv_id, desc, q, u))
            if st == "paid":
                total = round(subtotal + tax, 2)
                paid_day = issue + day(days=rnd.randint(0, 14))
                if rnd.random() < 0.05:                                   # failed attempt, then success
                    pay_id += 1
                    con.execute("INSERT INTO payments VALUES (?,?,?,?,?,?)",
                                (pay_id, inv_id, paid_day.isoformat(), total, rnd.choice(methods), "failed"))
                    paid_day += day(days=rnd.randint(1, 5))
                pay_id += 1
                full = rnd.random() < 0.4
                refund = rnd.random() < 0.05 and paid_day + day(days=3) <= END
                pstatus = "refunded" if (refund and full) else "succeeded"
                con.execute("INSERT INTO payments VALUES (?,?,?,?,?,?)",
                            (pay_id, inv_id, paid_day.isoformat(), total, rnd.choice(methods), pstatus))
                if refund:
                    ref_id += 1
                    rdate = min(paid_day + day(days=rnd.randint(3, 60)), END)
                    amount = total if full else round(total * rnd.choice([0.25, 0.5]), 2)
                    con.execute("INSERT INTO refunds VALUES (?,?,?,?,?)",
                                (ref_id, pay_id, rdate.isoformat(), amount,
                                 rnd.choice(["duplicate charge", "customer request", "service issue", "billing error"])))

    # tickets (timestamps, NULLs, mixed-case categories)
    cats = ["billing"] * 3 + ["Billing"] * 2 + ["BILLING"] + ["technical"] * 4 + ["Technical"] * 2 + ["how-to"] * 2 + ["How-To"] + ["feature request"] * 2
    for tid in range(1, 601):
        aid = rnd.choice(live)
        lo = dt.date.fromisoformat(acct[aid][6])
        opened = dt.datetime.combine(lo + day(days=rnd.randint(0, max(0, (END - lo).days))), dt.time(rnd.randint(0, 23), rnd.randint(0, 59), rnd.randint(0, 59)))
        closed = None if rnd.random() < 0.08 else opened + dt.timedelta(hours=rnd.randint(1, 240))
        csat = rnd.choices([1, 2, 3, 4, 5], [5, 8, 17, 35, 35])[0] if (closed and rnd.random() < 0.6) else None
        con.execute("INSERT INTO tickets VALUES (?,?,?,?,?,?,?)",
                    (tid, aid, opened.strftime("%Y-%m-%d %H:%M:%S"), closed.strftime("%Y-%m-%d %H:%M:%S") if closed else None,
                     rnd.choices(["low", "medium", "high", "urgent"], [30, 40, 22, 8])[0], rnd.choice(cats), csat))

    # usage events
    feats = ["dashboards", "api", "exports", "alerts", "sso"]
    for eid in range(1, 6001):
        aid = rnd.choice(live)
        lo = dt.date.fromisoformat(acct[aid][6])
        hi = dt.date.fromisoformat(acct[aid][7]) if acct[aid][7] else END
        d = lo + day(days=rnd.randint(0, max(0, (hi - lo).days)))
        con.execute("INSERT INTO usage_events VALUES (?,?,?,?,?)", (eid, aid, d.isoformat(), rnd.choice(feats), rnd.randint(1, 500)))
    con.commit()
    con.close()
    return path
